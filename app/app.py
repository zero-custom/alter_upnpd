import logging
import os
import signal
import threading
import socket
from flask import Flask, Response, jsonify
from jinja2 import Template

from config import Config
from gost_client import GostClient
from upnp_soap import UPnPSOAPHandler
from ssdp_responder import SSDPResponder
import stun_client

logger = logging.getLogger("alter_upnpd")

VERSION = Config.VERSION

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024

gost_client = GostClient(Config.GOST_API_URL)
soap_handler = UPnPSOAPHandler(gost_client)

XML_DIR = os.path.join(os.path.dirname(__file__), "xml")
TEMPLATE_CACHE = {}
TEMPLATE_CACHE_LOCK = threading.Lock()

_shutdown_event: threading.Event | None = None
_ssdp_thread: threading.Thread | None = None
_lease_thread: threading.Thread | None = None

def setup_logging() -> None:

    if logging.getLogger().hasHandlers():
        return
    logging.basicConfig(
        level=logging.DEBUG if Config.DEBUG else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

_LOCAL_IP_CACHE: str | None = None

def get_local_ip() -> str:
    global _LOCAL_IP_CACHE
    if _LOCAL_IP_CACHE is not None:
        return _LOCAL_IP_CACHE
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.settimeout(0.1)
            s.connect(('10.255.255.255', 1))
            _LOCAL_IP_CACHE = s.getsockname()[0]
    except Exception:
        _LOCAL_IP_CACHE = '127.0.0.1'
    return _LOCAL_IP_CACHE

def get_local_port() -> int:
    return Config.LISTEN_PORT

def get_location() -> str:
    return f"http://{get_local_ip()}:{get_local_port()}/rootDesc.xml"

_TEMPLATE_VARS = {
    "rootDesc.xml": lambda: {
        "LOCAL_IP": get_local_ip(),
        "LOCAL_PORT": get_local_port(),
    },
}

def render_xml(template_name: str) -> str:
    filepath = os.path.join(XML_DIR, template_name)
    if not os.path.exists(filepath):
        return "404 Not Found"

    mtime = os.path.getmtime(filepath)

    with TEMPLATE_CACHE_LOCK:
        cached = TEMPLATE_CACHE.get(template_name)
        if cached and cached["mtime"] == mtime:
            template = cached["template"]
        else:
            with open(filepath, "r") as f:
                template = Template(f.read())
            TEMPLATE_CACHE[template_name] = {"template": template, "mtime": mtime}
            logger.info("Loaded template: %s (mtime=%s)", template_name, mtime)

    context_fn = _TEMPLATE_VARS.get(template_name)
    context = context_fn() if context_fn else {}
    return template.render(**context)

@app.route("/rootDesc.xml")
def root_desc():
    return Response(render_xml("rootDesc.xml"), content_type="text/xml; charset=utf-8")

@app.route("/L3F.xml")
def l3f():
    return Response(render_xml("L3F.xml"), content_type="text/xml; charset=utf-8")

@app.route("/WANCfg.xml")
def wan_cfg():
    return Response(render_xml("WANCfg.xml"), content_type="text/xml; charset=utf-8")

@app.route("/WANIPCn.xml")
def wan_ipcn():
    return Response(render_xml("WANIPCn.xml"), content_type="text/xml; charset=utf-8")

@app.route("/ctl/L3F", methods=["POST"])
def ctl_l3f():
    return soap_handler.handle_l3forwarding()

@app.route("/ctl/CmnIfCfg", methods=["POST"])
def ctl_cmn_if_cfg():
    return soap_handler.handle_wancommonifconfig()

@app.route("/ctl/IPConn", methods=["POST"])
@app.route("/ctl/WANIPCn", methods=["POST"])
def ctl_wan_ipcn():
    return soap_handler.handle_wanipconnection()

@app.route("/ctl/WANPPPCn", methods=["POST"])
def ctl_wan_pppcn():
    return soap_handler.handle_wanipconnection()

@app.route("/<path:filename>")
def static_files(filename):
    if filename.endswith(".xml"):
        return Response(render_xml(filename), content_type="text/xml; charset=utf-8")
    return "Not Found", 404

@app.route("/")
def index():
    return f"alter_upnpd UPnP IGD - Port: {get_local_ip()}:{get_local_port()}"

@app.route("/health")
def health():
    gost_ok = gost_client.is_available()

    if gost_ok:
        mappings = gost_client.get_port_mappings()
        mappings_count = len(mappings)
        status = "healthy"
    else:
        mappings_count = 0
        status = "degraded"
        logger.warning("GOST API unreachable, health check degraded")

    return jsonify({
        "status": status,
        "version": VERSION,
        "local_ip": get_local_ip(),
        "local_port": get_local_port(),
        "gost_api": gost_client.base_url,
        "gost_connected": gost_ok,
        "port_mappings_count": mappings_count,
    })

def run_ssdp(shutdown_event):
    import asyncio
    responder = SSDPResponder(get_location(), notify_interval=Config.SSDP_NOTIFY_INTERVAL)
    asyncio.run(responder.start(shutdown_event))

def run_lease_cleanup(shutdown_event):
    while not shutdown_event.is_set():
        expired = gost_client.get_expired_services()
        for entry in expired:
            logger.info(
                "Lease expired: %s/%s, cleaning up",
                entry["protocol"], entry["external_port"],
            )
            try:
                gost_client.delete_port_mapping(entry["external_port"], entry["protocol"])
            except Exception as e:
                logger.warning("Lease cleanup failed for %s: %s", entry["service_name"], e)
        shutdown_event.wait(Config.LEASE_CLEANUP_INTERVAL)

def init_background_services() -> threading.Event:

    global _shutdown_event, _ssdp_thread, _lease_thread

    logger.info("Starting alter_upnpd v%s on http://%s:%s", VERSION, get_local_ip(), get_local_port())
    logger.info("Device location: %s", get_location())
    logger.info("GOST API URL: %s", gost_client.base_url)
    if Config.ACL_ENABLED:
        logger.info("ACL enabled, allowed subnets: %s", Config.ACL_ALLOWED_SUBNETS)
    logger.info("Lease duration: %ds (capped at 604800), cleanup interval: %ds",
                Config.LEASE_DURATION, Config.LEASE_CLEANUP_INTERVAL)

    if Config.STUN:
        stun_client.init()

    _shutdown_event = threading.Event()

    _ssdp_thread = threading.Thread(target=run_ssdp, args=(_shutdown_event,), name="ssdp")
    _ssdp_thread.start()

    _lease_thread = threading.Thread(target=run_lease_cleanup, args=(_shutdown_event,), name="lease-cleanup")
    _lease_thread.daemon = True
    _lease_thread.start()

    return _shutdown_event

def shutdown_background_services() -> None:

    global _shutdown_event, _ssdp_thread
    if _shutdown_event:
        _shutdown_event.set()
        logger.info("Shutting down, sending SSDP byebye...")
        if _ssdp_thread:
            _ssdp_thread.join(timeout=Config.SHUTDOWN_TIMEOUT)

def main():
    setup_logging()

    def handle_signal(sig, frame):
        if _shutdown_event:
            _shutdown_event.set()
        raise KeyboardInterrupt()

    signal.signal(signal.SIGTERM, handle_signal)

    init_background_services()

    try:
        app.run(host="0.0.0.0", port=get_local_port(), threaded=True)
    except KeyboardInterrupt:
        pass
    finally:
        shutdown_background_services()

if __name__ == "__main__":
    main()

application = app
