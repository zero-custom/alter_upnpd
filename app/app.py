import logging
import os
import signal
import socket

from flask import Flask, Response, jsonify, send_from_directory

from app_health import HealthService
from config import AppConfig, EnvConfig, load_env_config
from gost_client import GostClient
from lifecycle import AppLifecycle
from stun_client import StunClient
from template import TemplateRenderer
from upstream_client import UpstreamClient
from upnp_soap import UPnPSOAPHandler
import webui

from pywebio.platform.flask import webio_view
from pywebio import STATIC_PATH as PW_STATIC
from webui import main as webui_main
from static_bp import static_bp

logger = logging.getLogger("alter_upnpd")

cfg: EnvConfig = load_env_config()

VERSION = AppConfig.VERSION

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024

XML_DIR = os.path.join(os.path.dirname(__file__), "xml")

def setup_logging() -> None:

    if logging.getLogger().hasHandlers():
        return
    logging.basicConfig(
        level=logging.DEBUG if cfg.debug else logging.INFO,
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
    return cfg.listen_port

def get_location() -> str:
    return f"http://{get_local_ip()}:{get_local_port()}/rootDesc.xml"

gost_client = GostClient(
    base_url=cfg.gost_api_url,
    username=cfg.gost_api_username,
    password=cfg.gost_api_password,
    metrics_url=cfg.gost_metrics_url,
)
upstream = UpstreamClient(
    upstream_igd_url=cfg.upstream_igd_url,
    upstream_internal_host=cfg.upstream_internal_host,
)

stun_client = StunClient(stun_server=cfg.stun_server) if cfg.stun else None

soap_handler = UPnPSOAPHandler(
    gost_client=gost_client,
    upstream_client=upstream,
    acl_enabled=cfg.acl_enabled,
    secure_mode=cfg.secure_mode,
    acl_allowed_subnets=cfg.acl_allowed_subnets,
    lease_duration=cfg.lease_duration,
    stun_client=stun_client,
    upstream_igd_url=cfg.upstream_igd_url,
    upstream_internal_host=cfg.upstream_internal_host,
)
webui.init(
    gost_client=gost_client,
    refresh_interval=cfg.gost_webui_refresh_interval,
    history_points=cfg.gost_webui_history_points,
    window_seconds=cfg.gost_webui_window_seconds,
)

template = TemplateRenderer(XML_DIR)
template.set_var("rootDesc.xml", lambda: {
    "LOCAL_IP": get_local_ip(),
    "LOCAL_PORT": get_local_port(),
})

health_service = HealthService(
    gost_client=gost_client,
    version=VERSION,
    get_local_ip=get_local_ip,
    get_local_port=get_local_port,
)

lifecycle = AppLifecycle(
    gost_client=gost_client,
    get_location_fn=get_location,
    ssdp_notify_interval=cfg.ssdp_notify_interval,
    lease_cleanup_interval=cfg.lease_cleanup_interval,
    acl_enabled=cfg.acl_enabled,
    acl_allowed_subnets=cfg.acl_allowed_subnets,
    version=VERSION,
    stun_client=stun_client,
    upstream_client=upstream,
)

render_xml = template.render
init_background_services = lifecycle.start
shutdown_background_services = lifecycle.stop

app.add_url_rule(
    "/", "webui", webio_view(webui_main, cdn=False),
    methods=["GET", "POST", "OPTIONS"],
)
app.register_blueprint(static_bp)

@app.route("/rootDesc.xml")
def root_desc():
    return Response(template.render("rootDesc.xml"), content_type="text/xml; charset=utf-8")

@app.route("/L3F.xml")
def l3f():
    return Response(template.render("L3F.xml"), content_type="text/xml; charset=utf-8")

@app.route("/WANCfg.xml")
def wan_cfg():
    return Response(template.render("WANCfg.xml"), content_type="text/xml; charset=utf-8")

@app.route("/WANIPCn.xml")
def wan_ipcn():
    return Response(template.render("WANIPCn.xml"), content_type="text/xml; charset=utf-8")

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
        return Response(template.render(filename), content_type="text/xml; charset=utf-8")
    pw_path = os.path.join(PW_STATIC, filename)
    if os.path.exists(pw_path):
        return send_from_directory(PW_STATIC, filename)
    return "Not Found", 404

@app.route("/health")
def health():
    return jsonify(health_service.check())

def main():
    setup_logging()

    def handle_signal(sig, frame):
        if lifecycle.shutdown_event:
            lifecycle.shutdown_event.set()
        raise KeyboardInterrupt()

    signal.signal(signal.SIGTERM, handle_signal)

    lifecycle.start()

    try:
        app.run(host="0.0.0.0", port=get_local_port(), threaded=True)
    except KeyboardInterrupt:
        pass
    finally:
        lifecycle.stop()

if __name__ == "__main__":
    main()

application = app
