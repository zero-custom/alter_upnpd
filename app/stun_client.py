import logging
import threading
import time

import py3stun

from config import StunConfig

logger = logging.getLogger("alter_upnpd.stun")


class StunClient:
    def __init__(
        self,
        stun_server: str = "stun.l.google.com:19302",
        retries: int = StunConfig.RETRIES,
        refresh_interval: int = StunConfig.REFRESH_INTERVAL,
        fallback_wan_ip: str = StunConfig.FALLBACK_WAN_IP,
    ):
        self._stun_server = stun_server
        self._retries = retries
        self._refresh_interval = refresh_interval
        self._fallback_wan_ip = fallback_wan_ip
        self._wan_ip = fallback_wan_ip
        self._lock = threading.Lock()
        self._started = False

    def start(self) -> None:
        if self._started:
            return
        self._started = True
        threading.Thread(target=self._refresh_loop, daemon=True).start()

    def get_wan_ip(self) -> str:
        with self._lock:
            return self._wan_ip

    def reset_cache(self) -> None:
        with self._lock:
            self._wan_ip = self._fallback_wan_ip
        self._started = False

    def _refresh(self) -> None:
        stun_host, stun_port_str = self._stun_server.rsplit(":", 1)
        stun_port = int(stun_port_str)

        for attempt in range(self._retries):
            try:
                nat_type, ext_ip, ext_port = py3stun.get_ip_info(
                    source_ip="0.0.0.0",
                    source_port=0,
                    stun_host=stun_host,
                    stun_port=stun_port,
                )
            except Exception as e:
                logger.warning("STUN exception (attempt %d/%d): %s",
                               attempt + 1, self._retries, e)
                continue

            if ext_ip:
                with self._lock:
                    self._wan_ip = ext_ip
                logger.info("STUN OK: WAN IP = %s (type=%s, port=%s)",
                            ext_ip, nat_type, ext_port)
                return
            else:
                logger.warning("STUN no response (attempt %d/%d): type=%s",
                               attempt + 1, self._retries, nat_type)

        logger.warning("STUN FAILED: %s:%s — using fallback %s",
                       stun_host, stun_port, self._wan_ip)

    def _refresh_loop(self) -> None:
        self._refresh()
        while True:
            time.sleep(self._refresh_interval)
            logger.info("STUN refresh (interval=%ds)", self._refresh_interval)
            self._refresh()
