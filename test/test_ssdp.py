from unittest.mock import Mock, patch
from ssdp import messages
from ssdp_responder import UPNP_NT_LIST, SSDPResponder, SSDPHandler, USN


def _make_responder(location: str = "http://10.0.0.1:5000/rootDesc.xml") -> SSDPResponder:
    return SSDPResponder(location=location)


class TestUPNPConstants:
    def test_upnp_nt_list_has_8_entries(self):
        assert len(UPNP_NT_LIST) == 8

    def test_upnp_nt_list_starts_with_rootdevice(self):
        assert UPNP_NT_LIST[0] == "upnp:rootdevice"


class TestNotifyHeaders:
    def test_contains_required_fields(self):
        responder = _make_responder()
        headers = responder._notify_headers(
            nt="upnp:rootdevice",
            usn=f"{USN}::upnp:rootdevice",
            nts="ssdp:alive",
        )
        header_dict = dict(headers)
        assert header_dict["HOST"] is not None
        assert header_dict["NT"] == "upnp:rootdevice"
        assert header_dict["NTS"] == "ssdp:alive"
        assert header_dict["USN"] == f"{USN}::upnp:rootdevice"
        assert header_dict["LOCATION"] == "http://10.0.0.1:5000/rootDesc.xml"
        assert "CACHE-CONTROL" in header_dict
        assert "SERVER" in header_dict
        assert "BOOTID.UPNP.ORG" in header_dict

    def test_byebye_nts(self):
        responder = _make_responder()
        headers = responder._notify_headers(
            nt="upnp:rootdevice",
            usn=f"{USN}::upnp:rootdevice",
            nts="ssdp:byebye",
        )
        header_dict = dict(headers)
        assert header_dict["NTS"] == "ssdp:byebye"

    def test_service_has_own_usn(self):
        responder = _make_responder()
        headers = responder._notify_headers(
            nt="urn:schemas-upnp-org:service:WANIPConnection:1",
            usn=f"{USN}::urn:schemas-upnp-org:service:WANIPConnection:1",
            nts="ssdp:alive",
        )
        header_dict = dict(headers)
        assert header_dict["NT"] == "urn:schemas-upnp-org:service:WANIPConnection:1"
        assert header_dict["USN"] == (
            f"{USN}::urn:schemas-upnp-org:service:WANIPConnection:1"
        )


class TestSendAlive:
    def test_sends_notify_for_each_nt(self):
        responder = _make_responder()
        transport = Mock()
        responder._send_alive(transport)
        assert transport.sendto.call_count == len(UPNP_NT_LIST)

    def test_send_byebye_sends_for_each_nt(self):
        responder = _make_responder()
        transport = Mock()
        responder._send_byebye(transport)
        assert transport.sendto.call_count == len(UPNP_NT_LIST)

    def test_alive_error_does_not_propagate(self):
        responder = _make_responder()
        transport = Mock()
        transport.sendto.side_effect = OSError("network unreachable")
        # Should not raise
        responder._send_alive(transport)
        # Should still attempt all sends
        assert transport.sendto.call_count == len(UPNP_NT_LIST)

    def test_byebye_error_does_not_propagate(self):
        responder = _make_responder()
        transport = Mock()
        transport.sendto.side_effect = OSError("network unreachable")
        responder._send_byebye(transport)
        assert transport.sendto.call_count == len(UPNP_NT_LIST)


class TestSendAliveIntegration:
    def test_send_alive_creates_notify_request(self):
        responder = _make_responder()
        transport = Mock()
        with patch("ssdp_responder.messages.SSDPRequest") as mock_req:
            responder._send_alive(transport)
            assert mock_req.call_count == len(UPNP_NT_LIST)
            for call_args in mock_req.call_args_list:
                assert call_args[0][0] == "NOTIFY"

    def test_send_byebye_creates_notify_request(self):
        responder = _make_responder()
        transport = Mock()
        with patch("ssdp_responder.messages.SSDPRequest") as mock_req:
            responder._send_byebye(transport)
            assert mock_req.call_count == len(UPNP_NT_LIST)
            for call_args in mock_req.call_args_list:
                assert call_args[0][0] == "NOTIFY"


class TestSearchResponse:
    def test_response_contains_required_headers(self):
        handler = SSDPHandler(location="http://10.0.0.1:5000/rootDesc.xml")
        resp = handler._make_search_response(
            st="upnp:rootdevice",
            usn=f"{USN}::upnp:rootdevice",
        )
        header_dict = dict(resp.headers)
        assert resp.status_code == 200
        assert header_dict["ST"] == "upnp:rootdevice"
        assert header_dict["USN"] == f"{USN}::upnp:rootdevice"
        assert "EXT" in header_dict
        assert "DATE" in header_dict
        assert "CACHE-CONTROL" in header_dict

    def test_st_usn_map_matches_nt_list(self):
        assert len(SSDPHandler._ST_USN_MAP) == len(UPNP_NT_LIST)
        for nt in UPNP_NT_LIST:
            assert nt in SSDPHandler._ST_USN_MAP
            assert SSDPHandler._ST_USN_MAP[nt] == f"{USN}::{nt}"


class TestMSearchDispatch:
    def test_known_st_triggers_response(self):
        handler = SSDPHandler(location="http://10.0.0.1:5000/rootDesc.xml")
        handler.transport = Mock()
        request = Mock()
        request.headers = [("ST", "upnp:rootdevice")]
        handler.request_received(request, ("192.168.1.100", 54321))
        assert handler.transport.sendto.called

    def test_ssdp_all_triggers_all_responses(self):
        handler = SSDPHandler(location="http://10.0.0.1:5000/rootDesc.xml")
        handler.transport = Mock()
        request = Mock()
        request.headers = [("ST", "ssdp:all")]
        handler.request_received(request, ("192.168.1.100", 54321))
        assert handler.transport.sendto.call_count == len(UPNP_NT_LIST)

    def test_unknown_st_is_ignored(self):
        handler = SSDPHandler(location="http://10.0.0.1:5000/rootDesc.xml")
        handler.transport = Mock()
        request = Mock()
        request.headers = [("ST", "urn:schemas-upnp-org:service:WANPOTSLinkConfig:1")]
        handler.request_received(request, ("192.168.1.100", 54321))
        assert not handler.transport.sendto.called

    def test_missing_st_is_ignored(self):
        handler = SSDPHandler(location="http://10.0.0.1:5000/rootDesc.xml")
        handler.transport = Mock()
        request = Mock()
        request.headers = []
        handler.request_received(request, ("192.168.1.100", 54321))
        assert not handler.transport.sendto.called
