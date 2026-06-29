import logging

logger = logging.getLogger("alter_upnpd.upstream")


class UpstreamClient:
    def __init__(self, upstream_igd_url: str = ""):
        self._igd_url = upstream_igd_url
        self._upnp = None

    def add_port_mapping(
        self,
        external_port: int,
        protocol: str,
        description: str = "",
        lease_duration: int = 0,
        remote_host: str = "",
        upstream_internal_host: str = "",
    ) -> None:
        if self._upnp is None:
            self._ensure_upnp()
        if self._upnp is None:
            return

        internal_host = upstream_internal_host or ""

        try:
            self._upnp.addportmapping(
                external_port,
                protocol,
                internal_host,
                external_port,
                description,
                remote_host,
                lease_duration,
            )
            logger.debug("Upstream AddPortMapping OK: %s/%s  internal_host=%s",
                          protocol, external_port, internal_host)
        except Exception as e:
            logger.warning("Upstream AddPortMapping failed: %s/%s  %s",
                            protocol, external_port, e)

    def delete_port_mapping(
        self,
        external_port: int,
        protocol: str,
        remote_host: str = "",
    ) -> None:
        if self._upnp is None:
            self._ensure_upnp()
        if self._upnp is None:
            return

        try:
            self._upnp.deleteportmapping(external_port, protocol, remote_host)
            logger.debug("Upstream DeletePortMapping OK: %s/%s", protocol, external_port)
        except Exception as e:
            logger.warning("Upstream DeletePortMapping failed: %s/%s  %s",
                            protocol, external_port, e)

    def _ensure_upnp(self) -> None:
        if self._upnp is not None:
            return
        if not self._igd_url:
            return
        import miniupnpc

        try:
            u = miniupnpc.UPnP()
            u.discoverdelay = 0
            u.selectigd(self._igd_url)
            logger.info("Upstream IGD ready: lanaddr=%s  wanaddr=%s",
                         u.lanaddr, u.wanaddr or "(n/a)")
            self._upnp = u
        except Exception as e:
            logger.warning("Upstream IGD discovery failed: %s", e)
