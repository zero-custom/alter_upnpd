import asyncio
import datetime
import fcntl
import logging
import os
import socket
import struct
import time
from ssdp import aio, messages, network

from config import Config

logger = logging.getLogger("alter_upnpd.ssdp")

USN = "uuid:ed8d683a-91ea-402b-9c25-d0a48f23e9d7"

MCAST_GROUP = "239.255.255.250"
SSDP_PORT = 1900

# ── UPnP device lifecycle identifiers ──
BOOT_ID = int(time.time())  # increment per boot, use timestamp as unique boot ID
CONFIG_ID = 1               # static — no runtime config changes

def _upnp_date() -> str:
    """RFC 1123 date string for SSDP DATE header."""
    return datetime.datetime.now(datetime.UTC).strftime("%a, %d %b %Y %H:%M:%S GMT")

def _headers(headers: dict) -> list:

    return list(headers.items())

class SSDPResponder:
    def __init__(self, location: str, notify_interval: int = 180):
        self.location = location
        self.notify_interval = notify_interval

    @staticmethod
    def _make_multicast_socket(bind_ip: str) -> socket.socket:

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        except OSError:
            pass
        sock.bind(("", SSDP_PORT))
        mreq = struct.pack("4s4s", socket.inet_aton(MCAST_GROUP),
                           socket.inet_aton(bind_ip))
        try:
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
        except OSError as e:
            logger.warning("Cannot join multicast group on %s: %s", bind_ip, e)
        sock.setblocking(False)
        return sock

    def get_ipv4_interfaces(self):
        interfaces = []
        try:
            ifaces = [d for d in os.listdir('/sys/class/net/') if d != 'lo']
        except FileNotFoundError:
            return interfaces
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        for iface in ifaces:
            try:
                ifr = struct.pack('16sH48x', iface.encode()[:15], socket.AF_INET)
                result = fcntl.ioctl(sock.fileno(), 0x8921, ifr)
                addr = result[20:24]
                ip = socket.inet_ntoa(addr)
                if not ip.startswith('127.'):
                    interfaces.append(ip)
            except (IOError, OSError):
                continue
        sock.close()
        return interfaces

    async def start(self, shutdown_event=None):
        loop = asyncio.get_event_loop()
        transports = []

        bind_ips = self.get_ipv4_interfaces()
        if not bind_ips:
            bind_ips = ["0.0.0.0"]

        for ip in bind_ips:
            try:
                sock = self._make_multicast_socket(ip)
                transport, protocol = await loop.create_datagram_endpoint(
                    lambda: SSDPHandler(self.location),
                    sock=sock,
                )
                transports.append(transport)
                logger.info(
                    "SSDP responder started on %s:%d (multicast joined)",
                    ip, SSDP_PORT,
                )
            except PermissionError:
                logger.warning(
                    "Cannot bind to port %d on %s – need CAP_NET_BIND_SERVICE or root. SSDP muted.",
                    SSDP_PORT, ip,
                )
            except Exception as e:
                logger.error("Failed to start SSDP on %s: %s", ip, e)

        for transport in transports:
            self._send_alive(transport)

        last_alive = time.monotonic()
        try:
            while True:
                if shutdown_event and shutdown_event.is_set():
                    break
                await asyncio.sleep(1)
                if time.monotonic() - last_alive >= self.notify_interval:
                    last_alive = time.monotonic()
                    for transport in transports:
                        self._send_alive(transport)
        finally:
            logger.info("Sending ssdp:byebye...")
            for transport in transports:
                self._send_byebye(transport)
            await asyncio.sleep(0.3)
            for transport in transports:
                transport.close()

    def _notify_headers(self, nt: str, usn: str, nts: str) -> list:
        return _headers({
            "HOST": f"{network.MULTICAST_ADDRESS_IPV4}:{network.PORT}",
            "NT": nt,
            "NTS": nts,
            "USN": usn,
            "LOCATION": self.location,
            "CACHE-CONTROL": f"max-age={Config.SSDP_CACHE_CONTROL}",
            "SERVER": Config.SERVER_ID,
            "BOOTID.UPNP.ORG": str(BOOT_ID),
            "CONFIGID.UPNP.ORG": str(CONFIG_ID),
        })

    def _send_alive(self, transport):
        notify = messages.SSDPRequest("NOTIFY")
        notify.headers = self._notify_headers(
            "upnp:rootdevice", f"{USN}::upnp:rootdevice", "ssdp:alive",
        )
        try:
            notify.sendto(transport, (network.MULTICAST_ADDRESS_IPV4, network.PORT))
            self._send_alive_services(transport)
            logger.debug("Sent NOTIFY alive for rootdevice")
        except Exception as e:
            logger.error("Failed to send NOTIFY: %s", e)

    def _send_alive_services(self, transport):
        services = [
            ("urn:schemas-upnp-org:device:InternetGatewayDevice:1",
             f"{USN}::urn:schemas-upnp-org:device:InternetGatewayDevice:1"),
            ("urn:schemas-upnp-org:device:WANDevice:1",
             f"{USN}::urn:schemas-upnp-org:device:WANDevice:1"),
            ("urn:schemas-upnp-org:device:WANConnectionDevice:1",
             f"{USN}::urn:schemas-upnp-org:device:WANConnectionDevice:1"),
            ("urn:schemas-upnp-org:service:Layer3Forwarding:1",
             f"{USN}::urn:schemas-upnp-org:service:Layer3Forwarding:1"),
            ("urn:schemas-upnp-org:service:WANCommonInterfaceConfig:1",
             f"{USN}::urn:schemas-upnp-org:service:WANCommonInterfaceConfig:1"),
            ("urn:schemas-upnp-org:service:WANIPConnection:1",
             f"{USN}::urn:schemas-upnp-org:service:WANIPConnection:1"),
            ("urn:schemas-upnp-org:service:WANPPPConnection:1",
             f"{USN}::urn:schemas-upnp-org:service:WANPPPConnection:1"),
        ]
        for nt, usn in services:
            notify = messages.SSDPRequest("NOTIFY")
            notify.headers = self._notify_headers(nt, usn, "ssdp:alive")
            notify.sendto(transport, (network.MULTICAST_ADDRESS_IPV4, network.PORT))

    def _send_byebye(self, transport):
        services = [
            ("upnp:rootdevice", f"{USN}::upnp:rootdevice"),
            ("urn:schemas-upnp-org:device:InternetGatewayDevice:1",
             f"{USN}::urn:schemas-upnp-org:device:InternetGatewayDevice:1"),
            ("urn:schemas-upnp-org:device:WANDevice:1",
             f"{USN}::urn:schemas-upnp-org:device:WANDevice:1"),
            ("urn:schemas-upnp-org:device:WANConnectionDevice:1",
             f"{USN}::urn:schemas-upnp-org:device:WANConnectionDevice:1"),
            ("urn:schemas-upnp-org:service:Layer3Forwarding:1",
             f"{USN}::urn:schemas-upnp-org:service:Layer3Forwarding:1"),
            ("urn:schemas-upnp-org:service:WANCommonInterfaceConfig:1",
             f"{USN}::urn:schemas-upnp-org:service:WANCommonInterfaceConfig:1"),
            ("urn:schemas-upnp-org:service:WANIPConnection:1",
             f"{USN}::urn:schemas-upnp-org:service:WANIPConnection:1"),
            ("urn:schemas-upnp-org:service:WANPPPConnection:1",
             f"{USN}::urn:schemas-upnp-org:service:WANPPPConnection:1"),
        ]
        for nt, usn in services:
            notify = messages.SSDPRequest("NOTIFY")
            notify.headers = self._notify_headers(nt, usn, "ssdp:byebye")
            try:
                notify.sendto(transport, (network.MULTICAST_ADDRESS_IPV4, network.PORT))
            except Exception as e:
                logger.error("Failed to send byebye: %s", e)

class SSDPHandler(aio.SimpleServiceDiscoveryProtocol):
    def __init__(self, location: str):
        super().__init__()
        self.location = location
        self.transport = None

    def connection_made(self, transport):
        self.transport = transport
        super().connection_made(transport)

    def response_received(self, response, addr):
        pass

    _ST_USN_MAP = {
        "upnp:rootdevice": f"{USN}::upnp:rootdevice",
        "urn:schemas-upnp-org:device:InternetGatewayDevice:1":
            f"{USN}::urn:schemas-upnp-org:device:InternetGatewayDevice:1",
        "urn:schemas-upnp-org:device:WANDevice:1":
            f"{USN}::urn:schemas-upnp-org:device:WANDevice:1",
        "urn:schemas-upnp-org:device:WANConnectionDevice:1":
            f"{USN}::urn:schemas-upnp-org:device:WANConnectionDevice:1",
        "urn:schemas-upnp-org:service:WANIPConnection:1":
            f"{USN}::urn:schemas-upnp-org:service:WANIPConnection:1",
        "urn:schemas-upnp-org:service:WANPPPConnection:1":
            f"{USN}::urn:schemas-upnp-org:service:WANPPPConnection:1",
        "urn:schemas-upnp-org:service:WANCommonInterfaceConfig:1":
            f"{USN}::urn:schemas-upnp-org:service:WANCommonInterfaceConfig:1",
        "urn:schemas-upnp-org:service:Layer3Forwarding:1":
            f"{USN}::urn:schemas-upnp-org:service:Layer3Forwarding:1",
    }

    def request_received(self, request, addr):
        headers = dict(request.headers)
        st = headers.get("ST", "")
        if st in self._ST_USN_MAP or st == "ssdp:all":
            logger.debug("M-SEARCH received ST=%s from %s", st, addr)
            self._send_search_response(st, addr)

    def _make_search_response(self, st: str, usn: str) -> messages.SSDPResponse:
        response = messages.SSDPResponse(200, "OK")
        response.headers = _headers({
            "CACHE-CONTROL": f"max-age={Config.SSDP_CACHE_CONTROL}",
            "DATE": _upnp_date(),
            "LOCATION": self.location,
            "SERVER": Config.SERVER_ID,
            "ST": st,
            "USN": usn,
            "EXT": "",
            "BOOTID.UPNP.ORG": str(BOOT_ID),
            "CONFIGID.UPNP.ORG": str(CONFIG_ID),
        })
        return response

    def _send_search_response(self, st: str, addr: tuple):
        try:
            if st == "ssdp:all":
                for entry_st, entry_usn in self._ST_USN_MAP.items():
                    resp = self._make_search_response(entry_st, entry_usn)
                    resp.sendto(self.transport, addr)
                logger.debug("Sent %d M-SEARCH responses for ssdp:all to %s",
                             len(self._ST_USN_MAP), addr)
            else:
                usn = self._ST_USN_MAP.get(st, USN)
                resp = self._make_search_response(st, usn)
                resp.sendto(self.transport, addr)
                logger.debug("Sent M-SEARCH response to %s for ST=%s", addr, st)
        except Exception as e:
            logger.error("Failed to respond to M-SEARCH: %s", e)
