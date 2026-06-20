import logging

from config import Config

logger = logging.getLogger("alter_upnpd.upstream")

_upnp = None


def add_port_mapping(
    external_port: int,
    protocol: str,
    description: str = "",
    lease_duration: int = 0,
    remote_host: str = "",
) -> None:
    if _upnp is None:
        _ensure_upnp()
    if _upnp is None:
        return

    internal_host = Config.UPSTREAM_INTERNAL_HOST or ""

    try:
        _upnp.addportmapping(
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
    external_port: int,
    protocol: str,
    remote_host: str = "",
) -> None:
    if _upnp is None:
        _ensure_upnp()
    if _upnp is None:
        return

    try:
        _upnp.deleteportmapping(external_port, protocol, remote_host)
        logger.debug("Upstream DeletePortMapping OK: %s/%s", protocol, external_port)
    except Exception as e:
        logger.warning("Upstream DeletePortMapping failed: %s/%s  %s",
                        protocol, external_port, e)


def _ensure_upnp() -> None:
    global _upnp
    if _upnp is not None:
        return
    import miniupnpc

    try:
        u = miniupnpc.UPnP()
        u.discoverdelay = 0
        u.selectigd(Config.UPSTREAM_IGD_URL)
        logger.info("Upstream IGD ready: lanaddr=%s  wanaddr=%s",
                     u.lanaddr, u.wanaddr or "(n/a)")
        _upnp = u
    except Exception as e:
        logger.warning("Upstream IGD discovery failed: %s", e)
