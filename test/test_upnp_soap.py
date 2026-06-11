"""Tests for UPnPSOAPHandler — SOAP action dispatching and error handling.

The merged handler:
  - passes remote_host / enabled from AddPortMapping params to gost.add_port_mapping()
  - calls gost.delete_port_mapping(external_port, protocol=...) (no service_name)
  - GetExternalIPAddress uses stun_client.get_wan_ip() (default "1.2.3.4") or Config.STUN
"""

import pytest
from unittest.mock import Mock, patch
from flask import Flask

from gost_client import GostClient
from upnp_soap import UPnPSOAPHandler, SOAP_ACTIONS


# ── Shared fixtures ──


@pytest.fixture
def app():
    return Flask(__name__)


@pytest.fixture
def mock_gost():
    client = Mock(spec=GostClient)
    client.base_url = "http://test:8000"
    return client


@pytest.fixture
def handler(mock_gost):
    return UPnPSOAPHandler(mock_gost)


SOAP_TPL = '''<?xml version="1.0" encoding="utf-8"?>
<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"
            s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">
  <s:Body>
    <u:{action} xmlns:u="urn:schemas-upnp-org:service:WANIPConnection:1">
      {params}
    </u:{action}>
  </s:Body>
</s:Envelope>'''


def _soap_body(action: str, **kwargs) -> str:
    params = "\n".join(f"<{k}>{v}</{k}>" for k, v in kwargs.items())
    return SOAP_TPL.format(action=action, params=params)


# ── XML parsing ──


class TestParseSoapBody:
    def test_parses_action_and_params(self, handler):
        xml = _soap_body("AddPortMapping", NewExternalPort="8080", NewProtocol="TCP")
        result = handler.parse_soap_body(xml)
        assert result["action"] == "AddPortMapping"
        assert result["params"]["NewExternalPort"] == "8080"
        assert result["params"]["NewProtocol"] == "TCP"

    def test_returns_empty_on_garbage(self, handler):
        assert handler.parse_soap_body("not xml") == {}

    def test_returns_empty_on_empty_body(self, handler):
        xml = '''<?xml version="1.0"?>
<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/">
  <s:Body>
  </s:Body>
</s:Envelope>'''
        result = handler.parse_soap_body(xml)
        assert result == {}


# ── SOAP response building ──


class TestBuildSoapResponse:
    def test_basic_response(self, handler):
        xml = handler.build_soap_response("AddPortMapping")
        assert "AddPortMappingResponse" in xml
        assert "urn:schemas-upnp-org:service:WANIPConnection:1" in xml

    def test_with_return_values(self, handler):
        xml = handler.build_soap_response(
            "GetExternalIPAddress", {"NewExternalIPAddress": "1.2.3.4"}
        )
        assert "1.2.3.4" in xml
        assert "NewExternalIPAddress" in xml


class TestBuildFaultResponse:
    def test_fault_with_error_code(self, handler):
        xml = handler.build_fault_response("s:Client", 402)
        assert "Fault" in xml
        assert "s:Client" in xml


# ── SOAP Action: AddPortMapping ──


class TestAddPortMapping:
    def test_success(self, handler, mock_gost, app):
        mock_gost.has_port_mapping.return_value = False
        mock_gost.add_port_mapping.return_value = {"code": 0}
        with app.test_request_context():
            resp = handler._handle_add_port_mapping({
                "NewExternalPort": "8080",
                "NewInternalPort": "9000",
                "NewInternalClient": "192.168.1.10",
                "NewProtocol": "TCP",
                "NewPortMappingDescription": "test mapping",
                "NewRemoteHost": "",
                "NewEnabled": "1",
                "NewLeaseDuration": "3600",
            })
            assert resp.status_code == 200
            assert b"AddPortMappingResponse" in resp.data
            # No service_name kwarg — the client constructs it internally
            mock_gost.add_port_mapping.assert_called_once_with(
                external_port=8080,
                internal_port=9000,
                internal_client="192.168.1.10",
                protocol="tcp",
                description="test mapping",
                remote_host="",
                enabled=True,
                lease_duration=3600,
            )

    def test_invalid_port_returns_fault(self, handler, app):
        with app.test_request_context():
            resp = handler._handle_add_port_mapping({
                "NewExternalPort": "not_a_number",
                "NewInternalPort": "9000",
                "NewInternalClient": "10.0.0.5",
                "NewProtocol": "TCP",
            })
            assert resp.status_code == 200
            assert b"Invalid port number" in resp.data

    def test_conflict_returns_fault(self, handler, mock_gost, app):
        mock_gost.has_port_mapping.return_value = True
        with app.test_request_context():
            resp = handler._handle_add_port_mapping({
                "NewExternalPort": "8080",
                "NewInternalPort": "9000",
                "NewInternalClient": "10.0.0.5",
                "NewProtocol": "TCP",
            })
            assert b"ConflictInMappingEntry" in resp.data


# ── SOAP Action: DeletePortMapping ──


class TestDeletePortMapping:
    def test_success(self, handler, mock_gost, app):
        mock_gost.delete_port_mapping.return_value = {"code": 0}
        with app.test_request_context():
            resp = handler._handle_delete_port_mapping({
                "NewExternalPort": "8080",
                "NewProtocol": "TCP",
            })
            assert resp.status_code == 200
            assert b"DeletePortMappingResponse" in resp.data
            mock_gost.delete_port_mapping.assert_called_once_with(
                8080, protocol="tcp"
            )

    def test_invalid_port_returns_fault(self, handler, app):
        with app.test_request_context():
            resp = handler._handle_delete_port_mapping({
                "NewExternalPort": "bad",
                "NewProtocol": "TCP",
            })
            assert b"Invalid port number" in resp.data


# ── SOAP Action: GetGenericPortMappingEntry ──


class TestGetGenericPortMappingEntry:
    def test_found(self, handler, mock_gost, app):
        mock_gost.get_port_mapping_by_index.return_value = {
            "remote_host": "",
            "external_port": 8080,
            "protocol": "TCP",
            "internal_port": 9000,
            "internal_client": "192.168.1.10",
            "enabled": True,
            "description": "test",
            "lease_duration_remaining": 3500,
        }
        with app.test_request_context():
            resp = handler._handle_get_port_mapping_entry({"NewPortMappingIndex": "0"})
            assert resp.status_code == 200
            assert b"GetGenericPortMappingEntryResponse" in resp.data
            assert b"test" in resp.data
            assert b"3500" in resp.data

    def test_not_found(self, handler, mock_gost, app):
        mock_gost.get_port_mapping_by_index.return_value = None
        with app.test_request_context():
            resp = handler._handle_get_port_mapping_entry({"NewPortMappingIndex": "99"})
            assert b"SpecifiedArrayIndexInvalid" in resp.data


# ── SOAP Action: GetSpecificPortMappingEntry ──


class TestGetSpecificPortMappingEntry:
    def test_found(self, handler, mock_gost, app):
        mock_gost.get_port_mappings.return_value = [
            {
                "external_port": 8080,
                "protocol": "TCP",
                "remote_host": "",
                "internal_port": 9000,
                "internal_client": "192.168.1.10",
                "enabled": True,
                "description": "test",
            }
        ]
        with app.test_request_context():
            resp = handler._handle_get_specific_port_mapping({
                "NewExternalPort": "8080",
                "NewProtocol": "TCP",
                "NewRemoteHost": "",
            })
            assert resp.status_code == 200
            assert b"GetSpecificPortMappingEntryResponse" in resp.data

    def test_not_found(self, handler, mock_gost, app):
        mock_gost.get_port_mappings.return_value = []
        with app.test_request_context():
            resp = handler._handle_get_specific_port_mapping({
                "NewExternalPort": "9999",
                "NewProtocol": "TCP",
                "NewRemoteHost": "",
            })
            assert b"No such entry" in resp.data


# ── SOAP Action: GetPortMappingNumberOfEntries ──


class TestGetPortMappingNumberOfEntries:
    def test_returns_count(self, handler, mock_gost, app):
        mock_gost.get_port_mappings.return_value = [
            {"external_port": 8080},
            {"external_port": 9090},
        ]
        with app.test_request_context():
            resp = handler._handle_get_mapping_count()
            assert b"2" in resp.data


# ── SOAP Action: GetExternalIPAddress ──


class TestGetExternalIPAddress:
    def test_returns_stun_ip_when_enabled(self, handler, app):
        import config as cfg

        cfg.Config.STUN = True
        cfg.Config.STUN_SERVER = "stun.l.google.com:19302"
        with patch("upnp_soap.stun_client.get_wan_ip", return_value="203.0.113.5"):
            with app.test_request_context():
                resp = handler._handle_get_external_ip()
                assert b"203.0.113.5" in resp.data

    def test_returns_fallback_when_stun_disabled(self, handler, app):
        import config as cfg

        cfg.Config.STUN = False
        with app.test_request_context():
            resp = handler._handle_get_external_ip()
            assert b"1.2.3.4" in resp.data


# ── SOAP Action: GetStatusInfo ──


class TestGetStatusInfo:
    def test_returns_connected(self, handler, app):
        with app.test_request_context():
            resp = handler._handle_get_status_info()
            assert b"Connected" in resp.data
            assert b"ERROR_NONE" in resp.data


# ── SOAP Action: GetNATRSIPStatus ──


class TestGetNATRSIPStatus:
    def test_nat_enabled(self, handler, app):
        with app.test_request_context():
            resp = handler._handle_get_nat_rsip_status()
            assert b"NATEnabled" in resp.data


# ── Full dispatch (via handle_wanipconnection) ──


class TestDispatchIntegration:
    @staticmethod
    def _disable_acl():
        from upnp_soap import Config
        Config.ACL_ENABLED = False

    def test_add_port_mapping_via_dispatch(self, handler, mock_gost, app):
        self._disable_acl()
        mock_gost.has_port_mapping.return_value = False
        mock_gost.add_port_mapping.return_value = {"code": 0}
        with app.test_request_context(
            method="POST",
            data=_soap_body(
                "AddPortMapping",
                NewExternalPort="8080",
                NewInternalPort="9000",
                NewInternalClient="192.168.1.10",
                NewProtocol="TCP",
                NewLeaseDuration="0",
            ),
            content_type="text/xml",
            headers={
                "SOAPAction": '"urn:schemas-upnp-org:service:WANIPConnection:1#AddPortMapping"'
            },
        ):
            resp = handler.handle_wanipconnection()
            assert resp.status_code == 200
            assert b"AddPortMappingResponse" in resp.data

    def test_get_port_mapping_number_via_dispatch(self, handler, mock_gost, app):
        self._disable_acl()
        mock_gost.get_port_mappings.return_value = []
        with app.test_request_context(
            method="POST",
            data=_soap_body("GetPortMappingNumberOfEntries"),
            content_type="text/xml",
            headers={
                "SOAPAction": '"urn:schemas-upnp-org:service:WANIPConnection:1#GetPortMappingNumberOfEntries"'
            },
        ):
            resp = handler.handle_wanipconnection()
            assert resp.status_code == 200

    def test_unknown_action_via_dispatch(self, handler, app):
        self._disable_acl()
        with app.test_request_context(
            method="POST",
            data=_soap_body("NonExistentAction"),
            content_type="text/xml",
            headers={"SOAPAction": '"NonExistentAction"'},
        ):
            resp = handler.handle_wanipconnection()
            assert resp.status_code == 200
            assert b"Unknown action" in resp.data

    def test_dispatch_add_missing_fields(self, handler, mock_gost, app):
        self._disable_acl()
        mock_gost.has_port_mapping.return_value = False
        mock_gost.add_port_mapping.return_value = {"code": 0}
        with app.test_request_context(
            method="POST",
            data=_soap_body(
                "AddPortMapping",
                NewExternalPort="8080",
                NewInternalPort="9000",
                NewInternalClient="192.168.1.10",
                NewProtocol="TCP",
                NewLeaseDuration="0",
                # Intentionally omit NewRemoteHost and NewEnabled
            ),
            content_type="text/xml",
            headers={
                "SOAPAction": '"urn:schemas-upnp-org:service:WANIPConnection:1#AddPortMapping"'
            },
        ):
            resp = handler.handle_wanipconnection()
            assert resp.status_code == 200
            # Verify defaults: remote_host="" and enabled="1" (True)
            mock_gost.add_port_mapping.assert_called_once()
            kwargs = mock_gost.add_port_mapping.call_args[1]
            assert kwargs["remote_host"] == ""
            assert kwargs["enabled"] is True
