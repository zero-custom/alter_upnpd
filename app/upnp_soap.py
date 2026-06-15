import ipaddress
import logging
import time

from flask import request, Response
from lxml import etree
from config import Config
from gost_client import GostClient, GostConnectionError, GostApiError
import stun_client
import upstream_client

logger = logging.getLogger("alter_upnpd.upnp_soap")

NS = {
    "s": "http://schemas.xmlsoap.org/soap/envelope/",
    "u": "urn:schemas-upnp-org:service:WANIPConnection:1",
    "p": "urn:schemas-upnp-org:service:WANPPPConnection:1",
}

SOAP_ACTIONS = {}
CIC_ACTIONS = {}
L3F_ACTIONS = {}

PORT_MIN = 1
PORT_MAX = 65535
MAX_SOAP_BODY = 100 * 1024

_ALLOWED_NETWORKS = [
    ipaddress.ip_network(s.strip(), strict=False)
    for s in Config.ACL_ALLOWED_SUBNETS.split(",")
    if s.strip()
]

def soap_action(action_name):
    def decorator(func):
        SOAP_ACTIONS[action_name] = func
        return func
    return decorator

def cic_action(action_name):
    def decorator(func):
        CIC_ACTIONS[action_name] = func
        return func
    return decorator

def l3f_action(action_name):
    def decorator(func):
        L3F_ACTIONS[action_name] = func
        return func
    return decorator

def _parse_action_from_header(header_value: str) -> str | None:
    if not header_value:
        return None
    stripped = header_value.strip().strip('"')
    if "#" in stripped:
        return stripped.split("#")[-1]
    return stripped if stripped else None

class UPnPSOAPHandler:
    def __init__(self, gost_client: GostClient):
        self.gost = gost_client
        self._start_time = time.time()
        self._current_service_urn = None

    def parse_soap_body(self, xml_data: str) -> dict:
        if len(xml_data) > MAX_SOAP_BODY:
            logger.warning("SOAP body too large: %d bytes", len(xml_data))
            return {}
        try:
            parser = etree.XMLParser(resolve_entities=False, no_network=True)
            root = etree.fromstring(xml_data.encode(), parser)
            body = root.find(".//s:Body", namespaces=NS)
            if body is None:
                return {}

            action = body[0].tag.split("}")[-1] if "}" in body[0].tag else body[0].tag

            params = {}
            for elem in body[0]:
                tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
                params[tag] = elem.text or ""

            return {"action": action, "params": params}
        except Exception as e:
            logger.error("Failed to parse SOAP body: %s", e)
            return {}

    def build_soap_response(self, action_name: str, return_values: dict = None,
                            service_urn: str = None) -> str:
        ns = (service_urn or self._current_service_urn
              or "urn:schemas-upnp-org:service:WANIPConnection:1")

        root = etree.Element("{http://schemas.xmlsoap.org/soap/envelope/}Envelope")
        root.set("{http://schemas.xmlsoap.org/soap/encoding/}encodingStyle", "http://schemas.xmlsoap.org/soap/encoding/")

        body = etree.SubElement(root, "{http://schemas.xmlsoap.org/soap/envelope/}Body")

        response_name = f"{{{ns}}}{action_name}Response"
        response = etree.SubElement(body, response_name)

        if return_values:
            for key, value in return_values.items():
                elem = etree.SubElement(response, f"{{{ns}}}{key}")
                if value is not None:
                    elem.text = str(value)

        return '<?xml version="1.0" encoding="utf-8"?>\n' + etree.tostring(root, encoding="unicode")

    @staticmethod
    def _upnp_error_detail(error_code: int, error_description: str) -> etree.Element:

        detail = etree.Element("detail")
        upnp_error = etree.SubElement(
            detail,
            "{urn:schemas-upnp-org:control-1-0}UPnPError",
        )
        ec = etree.SubElement(upnp_error, "errorCode")
        ec.text = str(error_code)
        ed = etree.SubElement(upnp_error, "errorDescription")
        ed.text = error_description
        return detail

    def build_fault_response(self, fault_string: str,
                             error_code: int | None = None) -> str:

        ns_s = "http://schemas.xmlsoap.org/soap/envelope/"
        root = etree.Element(f"{{{ns_s}}}Envelope")
        root.set(
            "{http://schemas.xmlsoap.org/soap/encoding/}encodingStyle",
            "http://schemas.xmlsoap.org/soap/encoding/",
        )

        body = etree.SubElement(root, f"{{{ns_s}}}Body")
        fault = etree.SubElement(body, f"{{{ns_s}}}Fault")

        code = etree.SubElement(fault, "faultcode")
        string = etree.SubElement(fault, "faultstring")

        if error_code is not None:
            code.text = f"{{{ns_s}}}Client"
            string.text = "UPnPError"
            fault.append(self._upnp_error_detail(error_code, fault_string))
        else:
            code.text = "s:Client"
            string.text = fault_string

        return '<?xml version="1.0" encoding="utf-8"?>\n' + etree.tostring(root, encoding="unicode")

    @staticmethod
    def _extract_service_urn(soapaction_header: str) -> str | None:
        stripped = soapaction_header.strip().strip('"')
        if "#" in stripped:
            return stripped.split("#")[0]
        return None

    def _validate_port(self, port: int) -> bool:
        return PORT_MIN <= port <= PORT_MAX

    def _handle_service_request(self, action_registry: dict, default_urn: str) -> Response:
        if Config.ACL_ENABLED:
            client_ip = request.remote_addr or "0.0.0.0"
            if not self._is_ip_allowed(client_ip):
                logger.warning("ACL blocked request from %s", client_ip)
                resp = self.build_fault_response("Forbidden")
                return Response(resp, status=403, mimetype="text/xml; charset=utf-8")

        content = request.get_data(as_text=True)
        parsed = self.parse_soap_body(content)
        soap_action_header = request.headers.get("SOAPAction", "")

        service_urn = self._extract_service_urn(soap_action_header) or default_urn
        self._current_service_urn = service_urn

        action = _parse_action_from_header(soap_action_header)
        if not action or action not in action_registry:
            action = parsed.get("action", "")

        params = parsed.get("params", {})

        handler = action_registry.get(action)
        if handler:
            logger.info("Handling SOAP action: %s on %s from %s",
                        action, service_urn, request.remote_addr)
            return handler(self, params)

        logger.warning("Unknown SOAP action: %s on %s", action, service_urn)
        resp = self.build_fault_response("Unknown action")
        return Response(resp, mimetype="text/xml; charset=utf-8")

    def handle_wanipconnection(self) -> Response:
        return self._handle_service_request(SOAP_ACTIONS,
                                            "urn:schemas-upnp-org:service:WANIPConnection:1")

    @staticmethod
    def _is_ip_allowed(client_ip: str) -> bool:
        try:
            addr = ipaddress.ip_address(client_ip)
            return any(addr in net for net in _ALLOWED_NETWORKS)
        except ValueError:
            logger.warning("Invalid client IP for ACL: %s", client_ip)
            return False

    @soap_action("AddPortMapping")
    def _handle_add_port_mapping(self, params: dict) -> Response:
        external_port_str = params.get("NewExternalPort", "")
        protocol = params.get("NewProtocol", "TCP")
        internal_client = params.get("NewInternalClient", "") or request.remote_addr or ""
        internal_port_str = params.get("NewInternalPort", "")
        description = params.get("NewPortMappingDescription",
                                  f"UPnP {protocol} {external_port_str}")
        remote_host = params.get("NewRemoteHost", "")
        enabled = params.get("NewEnabled", "1")

        try:
            external_port = int(external_port_str)
            internal_port = int(internal_port_str)
        except ValueError:
            logger.warning("Invalid port number: external=%r internal=%r", external_port_str, internal_port_str)
            resp = self.build_fault_response("Invalid port number", error_code=402)
            return Response(resp, mimetype="text/xml; charset=utf-8")

        if not self._validate_port(external_port) or not self._validate_port(internal_port):
            logger.warning(
                "Port out of range (%d-%d): external=%d internal=%d",
                PORT_MIN, PORT_MAX, external_port, internal_port,
            )
            resp = self.build_fault_response("Port out of range (1-65535)", error_code=715)
            return Response(resp, mimetype="text/xml; charset=utf-8")

        # ── Security Mode: prevent client from mapping to a different IP ──
        if Config.SECURE_MODE and internal_client != request.remote_addr:
            logger.warning(
                "SECURE: client %s tried to add mapping to %s",
                request.remote_addr, internal_client,
            )
            resp = self.build_fault_response("ConflictInMappingEntry", error_code=718)
            return Response(resp, mimetype="text/xml; charset=utf-8")

        existing = self.gost.get_port_mapping_by_port(external_port, protocol)
        if existing and existing.get("internal_client", "") != internal_client:
            logger.warning(
                "Conflict: port %s/%s already mapped to different client %s",
                protocol, external_port, existing.get("internal_client", ""),
            )
            resp = self.build_fault_response("ConflictInMappingEntry", error_code=718)
            return Response(resp, mimetype="text/xml; charset=utf-8")

        lease_duration_str = params.get("NewLeaseDuration", "")
        try:
            lease_duration = int(lease_duration_str)
        except ValueError:
            lease_duration = 0
        if lease_duration == 0:
            lease_duration = Config.LEASE_DURATION
        if lease_duration <= 0 or lease_duration > 604800:
            lease_duration = 604800

        # ── Same-client overwrite: update metadata in-place (no delete+recreate) ──
        if existing:
            logger.info("Renewing mapping: %s/%s (same client)", protocol, external_port)
            try:
                self.gost.update_port_mapping(
                    external_port=external_port,
                    internal_port=internal_port,
                    internal_client=internal_client,
                    protocol=protocol.lower(),
                    description=description,
                    remote_host=remote_host,
                    enabled=enabled == "1",
                    lease_duration=lease_duration,
                )
                logger.info(
                    "AddPortMapping renewed: %s/%s -> %s:%s (%s)",
                    protocol, external_port, internal_client, internal_port, description,
                )
                if Config.UPSTREAM_IGD_URL:
                    upstream_client.add_port_mapping(
                        external_port=external_port,
                        protocol=protocol,
                        description=description,
                        lease_duration=lease_duration,
                        remote_host=remote_host,
                    )
                resp = self.build_soap_response("AddPortMapping", {})
                return Response(resp, mimetype="text/xml; charset=utf-8")
            except (GostConnectionError, GostApiError) as e:
                logger.error("AddPortMapping renew failed: %s", e)
                resp = self.build_fault_response(str(e))
                return Response(resp, mimetype="text/xml; charset=utf-8")

        try:
            self.gost.add_port_mapping(
                external_port=external_port,
                internal_port=internal_port,
                internal_client=internal_client,
                protocol=protocol.lower(),
                description=description,
                remote_host=remote_host,
                enabled=enabled == "1",
                lease_duration=lease_duration,
            )
            logger.info(
                "AddPortMapping success: %s/%s -> %s:%s (%s)",
                protocol, external_port, internal_client, internal_port, description,
            )
            if Config.UPSTREAM_IGD_URL:
                upstream_client.add_port_mapping(
                    external_port=external_port,
                    protocol=protocol,
                    description=description,
                    lease_duration=lease_duration,
                    remote_host=remote_host,
                )
            resp = self.build_soap_response("AddPortMapping", {})
            return Response(resp, mimetype="text/xml; charset=utf-8")
        except GostConnectionError as e:
            logger.error("AddPortMapping failed (GOST unreachable): %s", e)
            resp = self.build_fault_response("Service unavailable", error_code=501)
            return Response(resp, mimetype="text/xml; charset=utf-8")
        except GostApiError as e:
            logger.error("AddPortMapping failed (GOST error): %s", e)
            resp = self.build_fault_response(str(e))
            return Response(resp, mimetype="text/xml; charset=utf-8")

    @soap_action("DeletePortMapping")
    def _handle_delete_port_mapping(self, params: dict) -> Response:
        external_port_str = params.get("NewExternalPort", "")
        protocol = params.get("NewProtocol", "TCP")

        try:
            external_port = int(external_port_str)
        except ValueError:
            logger.warning("Invalid port number: %r", external_port_str)
            resp = self.build_fault_response("Invalid port number", error_code=402)
            return Response(resp, mimetype="text/xml; charset=utf-8")

        if not self._validate_port(external_port):
            logger.warning("Port out of range (%d-%d): external=%d", PORT_MIN, PORT_MAX, external_port)
            resp = self.build_fault_response("Port out of range (1-65535)", error_code=715)
            return Response(resp, mimetype="text/xml; charset=utf-8")

        if Config.SECURE_MODE:
            existing = self.gost.get_port_mapping_by_port(external_port, protocol)
            if existing and existing.get("internal_client", "") != request.remote_addr:
                logger.warning(
                    "SECURE: client %s tried to delete %s/%s owned by %s",
                    request.remote_addr, protocol, external_port,
                    existing.get("internal_client", ""),
                )
                resp = self.build_fault_response("NoSuchEntryInArray", error_code=714)
                return Response(resp, mimetype="text/xml; charset=utf-8")

        try:
            self.gost.delete_port_mapping(external_port, protocol=protocol.lower())
            logger.info("DeletePortMapping success: %s/%s", protocol, external_port)
            if Config.UPSTREAM_IGD_URL:
                upstream_client.delete_port_mapping(
                    external_port=external_port,
                    protocol=protocol,
                )
            resp = self.build_soap_response("DeletePortMapping", {})
            return Response(resp, mimetype="text/xml; charset=utf-8")
        except (GostConnectionError, GostApiError) as e:
            logger.warning("DeletePortMapping failed: %s", e)
            resp = self.build_fault_response(str(e))
            return Response(resp, mimetype="text/xml; charset=utf-8")

    @soap_action("GetGenericPortMappingEntry")
    def _handle_get_port_mapping_entry(self, params: dict) -> Response:
        index = params.get("NewPortMappingIndex", "0")

        try:
            index = int(index)
        except ValueError:
            resp = self.build_fault_response("Invalid index", error_code=402)
            return Response(resp, mimetype="text/xml; charset=utf-8")

        mapping = self.gost.get_port_mapping_by_index(index)

        if mapping:
            resp = self.build_soap_response("GetGenericPortMappingEntry", {
                "NewRemoteHost": mapping.get("remote_host", ""),
                "NewExternalPort": mapping.get("external_port", 0),
                "NewProtocol": mapping.get("protocol", "TCP"),
                "NewInternalPort": mapping.get("internal_port", 0),
                "NewInternalClient": mapping.get("internal_client", ""),
                "NewEnabled": "1" if mapping.get("enabled", True) else "0",
                "NewPortMappingDescription": mapping.get("description", ""),
                "NewLeaseDuration": mapping.get("lease_duration_remaining", 0),
            })
            return Response(resp, mimetype="text/xml; charset=utf-8")
        else:
            resp = self.build_fault_response("SpecifiedArrayIndexInvalid", error_code=713)
            return Response(resp, mimetype="text/xml; charset=utf-8")

    @soap_action("GetSpecificPortMappingEntry")
    def _handle_get_specific_port_mapping(self, params: dict) -> Response:
        external_port_str = params.get("NewExternalPort", "")
        protocol = params.get("NewProtocol", "TCP").upper()
        remote_host = params.get("NewRemoteHost", "")

        try:
            external_port = int(external_port_str)
        except ValueError:
            resp = self.build_fault_response("Invalid port", error_code=402)
            return Response(resp, mimetype="text/xml; charset=utf-8")

        mappings = self.gost.get_port_mappings()
        logger.info(
            "GetSpecificPortMappingEntry: ext=%s proto=%s host=%s  mappings_count=%d",
            external_port, protocol, remote_host, len(mappings),
        )
        for m in mappings:
            if m.get("external_port") == external_port and m.get("protocol", "").upper() == protocol:
                if remote_host and m.get("remote_host") != remote_host:
                    continue
                logger.info("GetSpecificPortMappingEntry: found mapping %s", m.get("description"))
                resp = self.build_soap_response("GetSpecificPortMappingEntry", {
                    "NewRemoteHost": m.get("remote_host", ""),
                    "NewExternalPort": m.get("external_port", 0),
                    "NewProtocol": m.get("protocol", "TCP"),
                    "NewInternalPort": m.get("internal_port", 0),
                    "NewInternalClient": m.get("internal_client", ""),
                    "NewEnabled": "1" if m.get("enabled", True) else "0",
                    "NewPortMappingDescription": m.get("description", ""),
                    "NewLeaseDuration": m.get("lease_duration_remaining", 0),
                })
                return Response(resp, mimetype="text/xml; charset=utf-8")

        logger.warning(
            "GetSpecificPortMappingEntry: no match for %s/%s among %d mapping(s)",
            protocol, external_port, len(mappings),
        )
        resp = self.build_fault_response("No such entry", error_code=714)
        return Response(resp, mimetype="text/xml; charset=utf-8")

    @soap_action("GetPortMappingNumberOfEntries")
    def _handle_get_mapping_count(self, params: dict = None) -> Response:
        mappings = self.gost.get_port_mappings()
        resp = self.build_soap_response("GetPortMappingNumberOfEntries", {
            "NewPortMappingNumberOfEntries": len(mappings),
        })
        return Response(resp, mimetype="text/xml; charset=utf-8")

    @soap_action("GetExternalIPAddress")
    def _handle_get_external_ip(self, params: dict = None) -> Response:
        if Config.STUN:
            wan_ip = stun_client.get_wan_ip()
        else:
            wan_ip = Config.FALLBACK_WAN_IP
        resp = self.build_soap_response("GetExternalIPAddress", {
            "NewExternalIPAddress": wan_ip,
        })
        return Response(resp, mimetype="text/xml; charset=utf-8")

    @soap_action("GetConnectionTypeInfo")
    def _handle_get_connection_type_info(self, params: dict = None) -> Response:
        resp = self.build_soap_response("GetConnectionTypeInfo", {
            "NewConnectionType": "IP_Routed",
            "NewPossibleConnectionTypes": "IP_Routed",
        })
        return Response(resp, mimetype="text/xml; charset=utf-8")

    @soap_action("GetLinkLayerMaxBitRates")
    def _handle_get_link_layer_max_bit_rates(self, params: dict = None) -> Response:
        resp = self.build_soap_response("GetLinkLayerMaxBitRates", {
            "NewUpstreamMaxBitRate": 0,
            "NewDownstreamMaxBitRate": 0,
        })
        return Response(resp, mimetype="text/xml; charset=utf-8")

    @soap_action("GetStatusInfo")
    def _handle_get_status_info(self, params: dict = None) -> Response:
        uptime = int(time.time() - self._start_time)
        resp = self.build_soap_response("GetStatusInfo", {
            "NewConnectionStatus": "Connected",
            "NewLastConnectionError": "ERROR_NONE",
            "NewUptime": uptime,
        })
        return Response(resp, mimetype="text/xml; charset=utf-8")

    @soap_action("GetNATRSIPStatus")
    def _handle_get_nat_rsip_status(self, params: dict = None) -> Response:
        resp = self.build_soap_response("GetNATRSIPStatus", {
            "NewRSIPAvailable": "0",
            "NewNATEnabled": "1",
        })
        return Response(resp, mimetype="text/xml; charset=utf-8")

    @soap_action("SetConnectionType")
    def _handle_set_connection_type(self, params: dict = None) -> Response:
        logger.warning("SetConnectionType called but not supported (always IP_Routed)")
        resp = self.build_fault_response("Action failed", error_code=501)
        return Response(resp, mimetype="text/xml; charset=utf-8")

    @soap_action("RequestConnection")
    def _handle_request_connection(self, params: dict = None) -> Response:
        logger.warning("RequestConnection called but not needed (always Connected)")
        resp = self.build_fault_response("Action failed", error_code=501)
        return Response(resp, mimetype="text/xml; charset=utf-8")

    @soap_action("ForceTermination")
    def _handle_force_termination(self, params: dict = None) -> Response:
        logger.warning("ForceTermination called but not supported (always Connected)")
        resp = self.build_fault_response("Action failed", error_code=501)
        return Response(resp, mimetype="text/xml; charset=utf-8")



    def handle_wancommonifconfig(self) -> Response:
        return self._handle_service_request(
            CIC_ACTIONS,
            "urn:schemas-upnp-org:service:WANCommonInterfaceConfig:1",
        )

    @cic_action("GetCommonLinkProperties")
    def _handle_get_common_link_properties(self, params: dict = None) -> Response:
        resp = self.build_soap_response("GetCommonLinkProperties", {
            "NewWANAccessType": "Ethernet",
            "NewLayer1UpstreamMaxBitRate": 0,
            "NewLayer1DownstreamMaxBitRate": 0,
            "NewPhysicalLinkStatus": "Up",
        })
        return Response(resp, mimetype="text/xml; charset=utf-8")

    @cic_action("GetTotalBytesSent")
    def _handle_get_total_bytes_sent(self, params: dict = None) -> Response:
        resp = self.build_soap_response("GetTotalBytesSent", {
            "NewTotalBytesSent": 0,
        })
        return Response(resp, mimetype="text/xml; charset=utf-8")

    @cic_action("GetTotalBytesReceived")
    def _handle_get_total_bytes_received(self, params: dict = None) -> Response:
        resp = self.build_soap_response("GetTotalBytesReceived", {
            "NewTotalBytesReceived": 0,
        })
        return Response(resp, mimetype="text/xml; charset=utf-8")

    @cic_action("GetTotalPacketsSent")
    def _handle_get_total_packets_sent(self, params: dict = None) -> Response:
        resp = self.build_soap_response("GetTotalPacketsSent", {
            "NewTotalPacketsSent": 0,
        })
        return Response(resp, mimetype="text/xml; charset=utf-8")

    @cic_action("GetTotalPacketsReceived")
    def _handle_get_total_packets_received(self, params: dict = None) -> Response:
        resp = self.build_soap_response("GetTotalPacketsReceived", {
            "NewTotalPacketsReceived": 0,
        })
        return Response(resp, mimetype="text/xml; charset=utf-8")



    def handle_l3forwarding(self) -> Response:
        return self._handle_service_request(
            L3F_ACTIONS,
            "urn:schemas-upnp-org:service:Layer3Forwarding:1",
        )

    @l3f_action("GetDefaultConnectionService")
    def _handle_get_default_connection_service(self, params: dict = None) -> Response:
        resp = self.build_soap_response("GetDefaultConnectionService", {
            "NewDefaultConnectionService": "urn:upnp-org:serviceId:WANIPConn1",
        })
        return Response(resp, mimetype="text/xml; charset=utf-8")

    @l3f_action("SetDefaultConnectionService")
    def _handle_set_default_connection_service(self, params: dict = None) -> Response:
        resp = self.build_soap_response("SetDefaultConnectionService", {})
        return Response(resp, mimetype="text/xml; charset=utf-8")
