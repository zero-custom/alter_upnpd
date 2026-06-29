import ipaddress
import logging
from typing import List, Optional

logger = logging.getLogger("alter_upnpd.acl")


class ACLEnforcer:
    def __init__(
        self,
        enabled: bool = True,
        secure_mode: bool = True,
        allowed_subnets: str = "192.168.0.0/16,10.0.0.0/8,172.16.0.0/12",
    ):
        self._enabled = enabled
        self._secure_mode = secure_mode
        self._allowed_networks = self._parse_subnets(allowed_subnets)

    @staticmethod
    def _parse_subnets(subnets_str: str) -> List[ipaddress.IPv4Network]:
        return [
            ipaddress.ip_network(s.strip(), strict=False)
            for s in subnets_str.split(",")
            if s.strip()
        ]

    def check_request(self, remote_ip: str) -> Optional[str]:
        if not self._enabled:
            return None
        try:
            addr = ipaddress.ip_address(remote_ip)
            if any(addr in net for net in self._allowed_networks):
                return None
        except ValueError:
            logger.warning("Invalid client IP for ACL: %s", remote_ip)
        return f"Forbidden: IP {remote_ip} not in allowed subnets"

    def check_port_mapping(
        self,
        remote_ip: str,
        internal_client: str,
        existing_client: Optional[str] = None,
    ) -> Optional[str]:
        if not self._secure_mode:
            return None

        # Prevent client from mapping to a different IP
        if internal_client and internal_client != remote_ip:
            return f"SECURE: client {remote_ip} cannot map to {internal_client}"

        # Prevent client from deleting another client's mapping
        if existing_client is not None and existing_client != remote_ip:
            return f"SECURE: client {remote_ip} cannot delete mapping owned by {existing_client}"

        return None
