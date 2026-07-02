import logging
import threading
from typing import Callable, Optional

from config import AppConfig
from gost_client import GostClient
from stun_client import StunClient

logger = logging.getLogger("alter_upnpd.lifecycle")


class AppLifecycle:
    def __init__(
        self,
        gost_client: GostClient,
        get_location_fn: Callable[[], str],
        ssdp_notify_interval: int,
        lease_cleanup_interval: int,
        acl_enabled: bool,
        acl_allowed_subnets: str,
        version: str,
        stun_client: StunClient | None = None,
        shutdown_timeout: int = AppConfig.SHUTDOWN_TIMEOUT,
    ):
        self._gost = gost_client
        self._get_location = get_location_fn
        self._ssdp_notify_interval = ssdp_notify_interval
        self._lease_cleanup_interval = lease_cleanup_interval
        self._acl_enabled = acl_enabled
        self._acl_allowed_subnets = acl_allowed_subnets
        self._version = version
        self._stun_client = stun_client
        self._shutdown_timeout = shutdown_timeout

        self._shutdown_event: Optional[threading.Event] = None
        self._ssdp_thread: Optional[threading.Thread] = None
        self._lease_thread: Optional[threading.Thread] = None

    @property
    def shutdown_event(self) -> Optional[threading.Event]:
        return self._shutdown_event

    def start(self) -> threading.Event:
        location = self._get_location()
        logger.info(
            "Starting alter_upnpd v%s on http://%s:%s",
            self._version, self._gost.base_url, location,
        )
        logger.info("Device location: %s", location)
        logger.info("GOST API URL: %s", self._gost.base_url)
        if self._acl_enabled:
            logger.info("ACL enabled, allowed subnets: %s", self._acl_allowed_subnets)
        logger.info(
            "Lease cleanup interval: %ds",
            self._lease_cleanup_interval,
        )

        if self._stun_client:
            self._stun_client.start()
            if not self._stun_client.wait_ready(timeout=10):
                logger.warning("STUN initial resolution timed out after 10s — "
                               "using fallback WAN IP until next refresh")

        self._shutdown_event = threading.Event()

        self._ssdp_thread = threading.Thread(
            target=self._run_ssdp,
            args=(self._shutdown_event,),
            name="ssdp",
        )
        self._ssdp_thread.start()

        self._lease_thread = threading.Thread(
            target=self._run_lease_cleanup,
            args=(self._shutdown_event,),
            name="lease-cleanup",
        )
        self._lease_thread.daemon = True
        self._lease_thread.start()

        return self._shutdown_event

    def stop(self) -> None:
        if self._shutdown_event:
            self._shutdown_event.set()
            logger.info("Shutting down, sending SSDP byebye...")
            if self._ssdp_thread:
                self._ssdp_thread.join(timeout=self._shutdown_timeout)

    def _run_ssdp(self, shutdown_event: threading.Event) -> None:
        import asyncio  # avoid top-level import in non-async module

        from ssdp_responder import SSDPResponder

        responder = SSDPResponder(
            self._get_location(),
            notify_interval=self._ssdp_notify_interval,
        )
        asyncio.run(responder.start(shutdown_event))

    def _run_lease_cleanup(self, shutdown_event: threading.Event) -> None:
        while not shutdown_event.is_set():
            expired = self._gost.get_expired_services()
            for entry in expired:
                logger.info(
                    "Lease expired: %s/%s, cleaning up",
                    entry["protocol"],
                    entry["external_port"],
                )
                try:
                    self._gost.delete_port_mapping(
                        entry["external_port"], entry["protocol"]
                    )
                except Exception as e:
                    logger.warning(
                        "Lease cleanup failed for %s: %s",
                        entry["service_name"],
                        e,
                    )
            shutdown_event.wait(self._lease_cleanup_interval)
