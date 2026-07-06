import logging

logger = logging.getLogger("alter_upnpd.upstream")


class UpstreamClient:
    def __init__(self, upstream_igd_url: str = "",
                 upstream_internal_host: str = ""):
        self._igd_url = upstream_igd_url
        self._upstream_internal_host = upstream_internal_host
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

    def _ensure_upnp_connected(self) -> bool:
        if self._upnp is not None:
            try:
                self._upnp.getportmappingnumberofentries()
                return True
            except Exception:
                logger.info("Upstream IGD connection stale, reconnecting...")
                self._upnp = None

        self._ensure_upnp()
        return self._upnp is not None

    def list_mappings(self) -> list[dict]:
        if not self._ensure_upnp_connected():
            return []

        mappings: list[dict] = []
        i = 0
        while True:
            try:
                p = self._upnp.getgenericportmapping(i)
            except Exception as e:
                logger.warning("Upstream enumeration error at index %d: %s", i, e)
                break
            if p is None:
                break
            # C extension returns: (ePort, proto, (intClient, iPort), desc, enabled, rHost, dur)
            ext_port, proto, (int_client, int_port), desc, enabled, r_host, lease = p
            mappings.append({
                "external_port": ext_port,
                "protocol": proto,
                "internal_client": int_client,
                "internal_port": int_port,
                "description": desc,
                "enabled": enabled,
                "remote_host": r_host,
                "lease_duration": lease,
            })
            i += 1
        return mappings

    def reconcile(self, gost_mappings: list[dict]) -> tuple[int, int]:
        if not self._ensure_upnp_connected():
            return 0, 0
        if not gost_mappings:
            return 0, 0

        restored = 0
        failed = 0
        internal_host = self._upstream_internal_host or ""

        for gm in gost_mappings:
            ext_port = gm["external_port"]
            proto = gm["protocol"].upper()

            try:
                p = self._upnp.getspecificportmapping(ext_port, proto)
            except Exception as e:
                logger.warning("Reconcile check failed %s/%s: %s", proto, ext_port, e)
                failed += 1
                continue

            if p is not None:
                continue

            try:
                self._upnp.addportmapping(
                    ext_port,
                    proto,
                    internal_host,
                    ext_port,
                    gm.get("description", ""),
                    gm.get("remote_host", ""),
                    gm.get("lease_duration", 0),
                )
                logger.info("Reconcile restored %s/%s (upstream host=%s)",
                            proto, ext_port, internal_host)
                restored += 1
            except Exception as e:
                logger.warning("Reconcile restore failed %s/%s: %s",
                               proto, ext_port, e)
                failed += 1

        return restored, failed
