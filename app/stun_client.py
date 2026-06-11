import logging
import threading
import time

import py3stun

from config import Config

logger = logging.getLogger("alter_upnpd.stun")

_wan_ip = Config.FALLBACK_WAN_IP
_started = False
_lock = threading.Lock()

def _refresh():
    global _wan_ip
    stun_host, stun_port_str = Config.STUN_SERVER.rsplit(":", 1)
    stun_port = int(stun_port_str)

    for attempt in range(Config.STUN_RETRIES):
        try:
            nat_type, ext_ip, ext_port = py3stun.get_ip_info(
                source_ip="0.0.0.0",
                source_port=0,
                stun_host=stun_host,
                stun_port=stun_port,
            )
        except Exception as e:
            logger.warning("STUN exception (attempt %d/%d): %s",
                           attempt + 1, Config.STUN_RETRIES, e)
            continue

        if ext_ip:
            with _lock:
                _wan_ip = ext_ip
            logger.info("STUN OK: WAN IP = %s (type=%s, port=%s)",
                        ext_ip, nat_type, ext_port)
            return
        else:
            logger.warning("STUN no response (attempt %d/%d): type=%s",
                           attempt + 1, Config.STUN_RETRIES, nat_type)

    logger.warning("STUN FAILED: %s:%s — using fallback %s",
                   stun_host, stun_port, _wan_ip)

def _refresh_loop():
    _refresh()
    while True:
        time.sleep(Config.STUN_REFRESH_INTERVAL)
        logger.info("STUN refresh (interval=%ds)", Config.STUN_REFRESH_INTERVAL)
        _refresh()

def init():

    global _started
    if _started:
        return
    _started = True
    threading.Thread(target=_refresh_loop, daemon=True).start()

def get_wan_ip():
    with _lock:
        return _wan_ip

def reset_cache():
    global _wan_ip, _started
    with _lock:
        _wan_ip = Config.FALLBACK_WAN_IP
    _started = False
