import logging
import time

from flask import request, Response
from gost_client import GostClient, GostConnectionError, GostApiError
from stun_client import StunClient
from upstream_client import UpstreamClient
from soap_xml import SoapBodyParser
from acl import ACLEnforcer

logger = logging.getLogger("alter_upnpd.upnp_soap")


class UPnPSOAPHandler:
    _SOAP_HANDLERS = {
        "AddPortMapping": "_handle_add_port_mapping",
        "DeletePortMapping": "_handle_delete_port_mapping",
        "GetGenericPortMappingEntry": "_handle_get_port_mapping_entry",
        "GetSpecificPortMappingEntry": "_handle_get_specific_port_mapping",
        "GetPortMappingNumberOfEntries": "_handle_get_mapping_count",
        "GetExternalIPAddress": "_handle_get_external_ip",
        "GetConnectionTypeInfo": "_handle_get_connection_type_info",
        "GetLinkLayerMaxBitRates": "_handle_get_link_layer_max_bit_rates",
        "GetStatusInfo": "_handle_get_status_info",
        "GetNATRSIPStatus": "_handle_get_nat_rsip_status",
        "SetConnectionType": "_handle_set_connection_type",
        "RequestConnection": "_handle_request_connection",
        "ForceTermination": "_handle_force_termination",
    }
    _CIC_HANDLERS = {
        "GetCommonLinkProperties": "_handle_get_common_link_properties",
        "GetTotalBytesSent": "_handle_get_total_bytes_sent",
        "GetTotalBytesReceived": "_handle_get_total_bytes_received",
        "GetTotalPacketsSent": "_handle_get_total_packets_sent",
        "GetTotalPacketsReceived": "_handle_get_total_packets_received",
    }
    _L3F_HANDLERS = {
        "GetDefaultConnectionService": "_handle_get_default_connection_service",
        "SetDefaultConnectionService": "_handle_set_default_connection_service",
    }

    _xml = SoapBodyParser  # static methods

    def __init__(
        self,
        gost_client: GostClient,
        upstream_client: "UpstreamClient | None" = None,
        acl_enforcer: ACLEnforcer | None = None,
        lease_duration: int = 604800,
        stun_client: StunClient | None = None,
        upstream_igd_url: str = "",
        upstream_internal_host: str = "",
        # Backward compat constructor params
        acl_enabled: bool = True,
        secure_mode: bool = True,
        acl_allowed_subnets: str = "192.168.0.0/16,10.0.0.0/8,172.16.0.0/12",
    ):
        self.gost = gost_client
        self._upstream_client = upstream_client
        self._lease_duration = lease_duration
        self._stun_client = stun_client
        self._upstream_igd_url = upstream_igd_url
        self._upstream_internal_host = upstream_internal_host
        self._acl = acl_enforcer or ACLEnforcer(
            enabled=acl_enabled,
            secure_mode=secure_mode,
            allowed_subnets=acl_allowed_subnets,
        )
        self._start_time = time.time()
        self._current_service_urn = None

    def _handle_service_request(self, handler_map: dict, default_urn: str) -> Response:
        client_ip = request.remote_addr or "0.0.0.0"
        reason = self._acl.check_request(client_ip)
        if reason:
            logger.warning("ACL blocked request from %s", client_ip)
            resp = self._xml.build_error_response("Forbidden")
            return Response(resp, status=403, mimetype="text/xml; charset=utf-8")

        content = request.get_data(as_text=True)
        parsed = self._xml.parse_body(content)
        soap_action_header = request.headers.get("SOAPAction", "")

        service_urn = self._xml.extract_service_urn(soap_action_header) or default_urn
        self._current_service_urn = service_urn

        action = self._xml.parse_action_from_header(soap_action_header)
        if not action or action not in handler_map:
            action = parsed.get("action", "")

        params = parsed.get("params", {})

        method_name = handler_map.get(action)
        if method_name:
            handler = getattr(self, method_name)
            logger.info("Handling SOAP action: %s on %s from %s",
                        action, service_urn, request.remote_addr)
            return handler(params)

        logger.warning("Unknown SOAP action: %s on %s", action, service_urn)
        resp = self._xml.build_error_response("Unknown action")
        return Response(resp, mimetype="text/xml; charset=utf-8")

    def handle_wanipconnection(self) -> Response:
        return self._handle_service_request(
            self._SOAP_HANDLERS,
            "urn:schemas-upnp-org:service:WANIPConnection:1",
        )

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
            resp = self._xml.build_error_response("Invalid port number", error_code=402)
            return Response(resp, mimetype="text/xml; charset=utf-8")

        if not self._xml.validate_port(external_port) or not self._xml.validate_port(internal_port):
            logger.warning(
                "Port out of range (%d-%d): external=%d internal=%d",
                SoapBodyParser.PORT_MIN, SoapBodyParser.PORT_MAX,
                external_port, internal_port,
            )
            resp = self._xml.build_error_response("Port out of range (1-65535)", error_code=715)
            return Response(resp, mimetype="text/xml; charset=utf-8")

        reason = self._acl.check_port_mapping(request.remote_addr or "", internal_client)
        if reason:
            logger.warning("SECURE: %s", reason)
            resp = self._xml.build_error_response("ConflictInMappingEntry", error_code=718)
            return Response(resp, mimetype="text/xml; charset=utf-8")

        existing = self.gost.get_port_mapping_by_port(external_port, protocol)
        if existing and existing.get("internal_client", "") != internal_client:
            logger.warning(
                "Conflict: port %s/%s already mapped to different client %s",
                protocol, external_port, existing.get("internal_client", ""),
            )
            resp = self._xml.build_error_response("ConflictInMappingEntry", error_code=718)
            return Response(resp, mimetype="text/xml; charset=utf-8")

        lease_duration_str = params.get("NewLeaseDuration", "")
        try:
            lease_duration = int(lease_duration_str)
        except ValueError:
            lease_duration = 0
        if lease_duration == 0:
            lease_duration = self._lease_duration
        if lease_duration <= 0 or lease_duration > 604800:
            lease_duration = 604800

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
                if self._upstream_client is not None and self._upstream_igd_url:
                    self._upstream_client.add_port_mapping(
                        external_port=external_port,
                        protocol=protocol,
                        description=description,
                        lease_duration=lease_duration,
                        remote_host=remote_host,
                        upstream_internal_host=self._upstream_internal_host,
                    )
                resp = self._xml.build_success_response("AddPortMapping", {})
                return Response(resp, mimetype="text/xml; charset=utf-8")
            except (GostConnectionError, GostApiError) as e:
                logger.error("AddPortMapping renew failed: %s", e)
                resp = self._xml.build_error_response(str(e))
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
            if self._upstream_client is not None and self._upstream_igd_url:
                self._upstream_client.add_port_mapping(
                    external_port=external_port,
                    protocol=protocol,
                    description=description,
                    lease_duration=lease_duration,
                    remote_host=remote_host,
                    upstream_internal_host=self._upstream_internal_host,
                )
            resp = self._xml.build_success_response("AddPortMapping", {})
            return Response(resp, mimetype="text/xml; charset=utf-8")
        except GostConnectionError as e:
            logger.error("AddPortMapping failed (GOST unreachable): %s", e)
            resp = self._xml.build_error_response("Service unavailable", error_code=501)
            return Response(resp, mimetype="text/xml; charset=utf-8")
        except GostApiError as e:
            logger.error("AddPortMapping failed (GOST error): %s", e)
            resp = self._xml.build_error_response(str(e))
            return Response(resp, mimetype="text/xml; charset=utf-8")

    def _handle_delete_port_mapping(self, params: dict) -> Response:
        external_port_str = params.get("NewExternalPort", "")
        protocol = params.get("NewProtocol", "TCP")

        try:
            external_port = int(external_port_str)
        except ValueError:
            logger.warning("Invalid port number: %r", external_port_str)
            resp = self._xml.build_error_response("Invalid port number", error_code=402)
            return Response(resp, mimetype="text/xml; charset=utf-8")

        if not self._xml.validate_port(external_port):
            logger.warning("Port out of range (%d-%d): external=%d",
                           SoapBodyParser.PORT_MIN, SoapBodyParser.PORT_MAX, external_port)
            resp = self._xml.build_error_response("Port out of range (1-65535)", error_code=715)
            return Response(resp, mimetype="text/xml; charset=utf-8")

        existing = self.gost.get_port_mapping_by_port(external_port, protocol)
        existing_client = existing.get("internal_client", "") if existing else None
        reason = self._acl.check_port_mapping(
            request.remote_addr or "",
            existing_client=existing_client,
            internal_client="",
        )
        if reason:
            logger.warning("SECURE: %s", reason)
            resp = self._xml.build_error_response("NoSuchEntryInArray", error_code=714)
            return Response(resp, mimetype="text/xml; charset=utf-8")

        try:
            self.gost.delete_port_mapping(external_port, protocol=protocol.lower())
            logger.info("DeletePortMapping success: %s/%s", protocol, external_port)
            if self._upstream_client is not None and self._upstream_igd_url:
                self._upstream_client.delete_port_mapping(
                    external_port=external_port,
                    protocol=protocol,
                )
            resp = self._xml.build_success_response("DeletePortMapping", {})
            return Response(resp, mimetype="text/xml; charset=utf-8")
        except (GostConnectionError, GostApiError) as e:
            logger.warning("DeletePortMapping failed: %s", e)
            resp = self._xml.build_error_response(str(e))
            return Response(resp, mimetype="text/xml; charset=utf-8")

    def _handle_get_port_mapping_entry(self, params: dict) -> Response:
        index = params.get("NewPortMappingIndex", "0")

        try:
            index = int(index)
        except ValueError:
            resp = self._xml.build_error_response("Invalid index", error_code=402)
            return Response(resp, mimetype="text/xml; charset=utf-8")

        mapping = self.gost.get_port_mapping_by_index(index)

        if mapping:
            resp = self._xml.build_success_response("GetGenericPortMappingEntry", {
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
            resp = self._xml.build_error_response("SpecifiedArrayIndexInvalid", error_code=713)
            return Response(resp, mimetype="text/xml; charset=utf-8")

    def _handle_get_specific_port_mapping(self, params: dict) -> Response:
        external_port_str = params.get("NewExternalPort", "")
        protocol = params.get("NewProtocol", "TCP").upper()
        remote_host = params.get("NewRemoteHost", "")

        try:
            external_port = int(external_port_str)
        except ValueError:
            resp = self._xml.build_error_response("Invalid port", error_code=402)
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
                resp = self._xml.build_success_response("GetSpecificPortMappingEntry", {
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
        resp = self._xml.build_error_response("No such entry", error_code=714)
        return Response(resp, mimetype="text/xml; charset=utf-8")

    def _handle_get_mapping_count(self, params: dict = None) -> Response:
        mappings = self.gost.get_port_mappings()
        resp = self._xml.build_success_response("GetPortMappingNumberOfEntries", {
            "NewPortMappingNumberOfEntries": len(mappings),
        })
        return Response(resp, mimetype="text/xml; charset=utf-8")

    def _handle_get_external_ip(self, params: dict = None) -> Response:
        if self._stun_client:
            wan_ip = self._stun_client.get_wan_ip()
        else:
            wan_ip = "192.0.2.1"
        resp = self._xml.build_success_response("GetExternalIPAddress", {
            "NewExternalIPAddress": wan_ip,
        })
        return Response(resp, mimetype="text/xml; charset=utf-8")

    def _handle_get_connection_type_info(self, params: dict = None) -> Response:
        resp = self._xml.build_success_response("GetConnectionTypeInfo", {
            "NewConnectionType": "IP_Routed",
            "NewPossibleConnectionTypes": "IP_Routed",
        })
        return Response(resp, mimetype="text/xml; charset=utf-8")

    def _handle_get_link_layer_max_bit_rates(self, params: dict = None) -> Response:
        resp = self._xml.build_success_response("GetLinkLayerMaxBitRates", {
            "NewUpstreamMaxBitRate": 0,
            "NewDownstreamMaxBitRate": 0,
        })
        return Response(resp, mimetype="text/xml; charset=utf-8")

    def _handle_get_status_info(self, params: dict = None) -> Response:
        uptime = int(time.time() - self._start_time)
        resp = self._xml.build_success_response("GetStatusInfo", {
            "NewConnectionStatus": "Connected",
            "NewLastConnectionError": "ERROR_NONE",
            "NewUptime": uptime,
        })
        return Response(resp, mimetype="text/xml; charset=utf-8")

    def _handle_get_nat_rsip_status(self, params: dict = None) -> Response:
        resp = self._xml.build_success_response("GetNATRSIPStatus", {
            "NewRSIPAvailable": "0",
            "NewNATEnabled": "1",
        })
        return Response(resp, mimetype="text/xml; charset=utf-8")

    def _handle_set_connection_type(self, params: dict = None) -> Response:
        logger.warning("SetConnectionType called but not supported (always IP_Routed)")
        resp = self._xml.build_error_response("Action failed", error_code=501)
        return Response(resp, mimetype="text/xml; charset=utf-8")

    def _handle_request_connection(self, params: dict = None) -> Response:
        logger.warning("RequestConnection called but not needed (always Connected)")
        resp = self._xml.build_error_response("Action failed", error_code=501)
        return Response(resp, mimetype="text/xml; charset=utf-8")

    def _handle_force_termination(self, params: dict = None) -> Response:
        logger.warning("ForceTermination called but not supported (always Connected)")
        resp = self._xml.build_error_response("Action failed", error_code=501)
        return Response(resp, mimetype="text/xml; charset=utf-8")

    def handle_wancommonifconfig(self) -> Response:
        return self._handle_service_request(
            self._CIC_HANDLERS,
            "urn:schemas-upnp-org:service:WANCommonInterfaceConfig:1",
        )

    def _handle_get_common_link_properties(self, params: dict = None) -> Response:
        resp = self._xml.build_success_response("GetCommonLinkProperties", {
            "NewWANAccessType": "Ethernet",
            "NewLayer1UpstreamMaxBitRate": 0,
            "NewLayer1DownstreamMaxBitRate": 0,
            "NewPhysicalLinkStatus": "Up",
        })
        return Response(resp, mimetype="text/xml; charset=utf-8")

    def _handle_get_total_bytes_sent(self, params: dict = None) -> Response:
        resp = self._xml.build_success_response("GetTotalBytesSent", {
            "NewTotalBytesSent": 0,
        })
        return Response(resp, mimetype="text/xml; charset=utf-8")

    def _handle_get_total_bytes_received(self, params: dict = None) -> Response:
        resp = self._xml.build_success_response("GetTotalBytesReceived", {
            "NewTotalBytesReceived": 0,
        })
        return Response(resp, mimetype="text/xml; charset=utf-8")

    def _handle_get_total_packets_sent(self, params: dict = None) -> Response:
        resp = self._xml.build_success_response("GetTotalPacketsSent", {
            "NewTotalPacketsSent": 0,
        })
        return Response(resp, mimetype="text/xml; charset=utf-8")

    def _handle_get_total_packets_received(self, params: dict = None) -> Response:
        resp = self._xml.build_success_response("GetTotalPacketsReceived", {
            "NewTotalPacketsReceived": 0,
        })
        return Response(resp, mimetype="text/xml; charset=utf-8")

    def handle_l3forwarding(self) -> Response:
        return self._handle_service_request(
            self._L3F_HANDLERS,
            "urn:schemas-upnp-org:service:Layer3Forwarding:1",
        )

    def _handle_get_default_connection_service(self, params: dict = None) -> Response:
        resp = self._xml.build_success_response("GetDefaultConnectionService", {
            "NewDefaultConnectionService": "urn:upnp-org:serviceId:WANIPConn1",
        })
        return Response(resp, mimetype="text/xml; charset=utf-8")

    def _handle_set_default_connection_service(self, params: dict = None) -> Response:
        resp = self._xml.build_success_response("SetDefaultConnectionService", {})
        return Response(resp, mimetype="text/xml; charset=utf-8")
