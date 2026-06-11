"""Tests for GostClient — GOST REST API client (merged version).

Mocks requests at the transport layer.  The merged client:
  - single POST /config/services for add (no chain)
  - direct name construction for delete (not _find_upnp_service)
  - metadata-only reads for get_port_mappings
  - exceptions (not dicts) on errors
"""

import time
import pytest
from unittest.mock import patch, Mock

from gost_client import GostClient, GostConnectionError, GostApiError


@pytest.fixture
def client():
    return GostClient(base_url="http://gost:8000")


def _mock_resp(status_code=200, json_data=None):
    m = Mock(status_code=status_code)
    m.raise_for_status.return_value = None
    m.json = lambda: json_data if json_data is not None else {}
    m.content = b"{}"
    return m


# ── _pluck_services ──


class TestPluckServices:
    def test_flat_dict_with_service_keys(self):
        from gost_client import _pluck_services

        data = {
            "svc1": {"addr": ":8080", "handler": {"type": "tcp"}},
            "svc2": {"addr": ":9090", "forwarder": {"nodes": []}},
        }
        result = _pluck_services(data)
        assert len(result) == 2
        names = {s["name"] for s in result}
        assert names == {"svc1", "svc2"}

    def test_nested_dict(self):
        from gost_client import _pluck_services

        data = {
            "group": {
                "svc1": {"addr": ":8080", "handler": {"type": "tcp"}},
            }
        }
        result = _pluck_services(data)
        assert len(result) == 1
        assert result[0]["name"] == "svc1"

    def test_list_values(self):
        from gost_client import _pluck_services

        data = {
            "services": [
                {"name": "svc1", "addr": ":8080"},
                {"name": "svc2", "addr": ":9090"},
            ]
        }
        result = _pluck_services(data)
        assert len(result) == 2


# ── _request ──


class TestRequest:
    def test_success_returns_json(self, client):
        with patch("gost_client.requests.request") as mock_req:
            mock_req.return_value = _mock_resp(200, {"code": 0})
            result = client._request("GET", "/config/services")
            assert result == {"code": 0}

    def test_retries_and_succeeds(self, client):
        import requests as req_mod

        with patch("gost_client.requests.request") as mock_req:
            mock_req.side_effect = [
                req_mod.exceptions.ConnectionError("fail1"),
                req_mod.exceptions.ConnectionError("fail2"),
                _mock_resp(200, {"ok": True}),
            ]
            result = client._request("GET", "/config/services")
            assert result == {"ok": True}
            assert mock_req.call_count == 3

    def test_exhausts_retries_raises(self, client):
        import requests as req_mod

        with patch("gost_client.requests.request") as mock_req:
            mock_req.side_effect = req_mod.exceptions.ConnectionError("always fail")
            with pytest.raises(GostConnectionError):
                client._request("GET", "/config/services")
            assert mock_req.call_count == 3

    def test_http_error_raises_gost_api_error(self, client):
        import requests as req_mod

        with patch("gost_client.requests.request") as mock_req:
            resp = Mock(status_code=500)
            resp.raise_for_status.side_effect = req_mod.exceptions.HTTPError(
                "HTTP 500", response=resp
            )
            resp.text = "Internal Server Error"
            mock_req.return_value = resp
            with pytest.raises(GostApiError) as exc:
                client._request("GET", "/config/services")
            assert exc.value.status_code == 500

    def test_timeout_retries_then_raises(self, client):
        import requests as req_mod

        with patch("gost_client.requests.request") as mock_req:
            mock_req.side_effect = req_mod.exceptions.Timeout("timed out")
            with pytest.raises(GostConnectionError):
                client._request("GET", "/config/services")
            assert mock_req.call_count == 3


# ── add_port_mapping ──


class TestAddPortMapping:
    def test_success(self, client):
        with patch("gost_client.requests.request") as mock_req:
            mock_req.return_value = _mock_resp(201, {"code": 0})
            result = client.add_port_mapping(
                external_port=8080,
                internal_port=9000,
                internal_client="192.168.1.10",
                protocol="tcp",
                description="test mapping",
                remote_host="",
                enabled=True,
                lease_duration=3600,
            )
            assert result.get("code") == 0
            assert mock_req.call_count == 1
            call = mock_req.call_args_list[0]
            assert call[0][0] == "POST"
            assert call[0][1] == "http://gost:8000/config/services"
            body = call[1]["json"]
            assert body["name"] == "upnp_8080_tcp"
            assert body["forwarder"]["nodes"][0]["addr"] == "192.168.1.10:9000"
            meta = body["metadata"]
            assert meta["upnp"] is True
            assert meta["external_port"] == 8080
            assert meta["internal_port"] == 9000
            assert meta["remote_host"] == ""
            assert meta["enabled"] is True
            assert meta["lease_duration"] == 3600

    def test_cache_cleared_on_add(self, client):
        with patch("gost_client.requests.request") as mock_req:
            mock_req.return_value = _mock_resp(
                200, [{"name": "existing", "metadata": {"upnp": True}}]
            )
            client.get_services()
            assert client._services_cache is not None

            mock_req.return_value = _mock_resp(201, {"code": 0})
            client.add_port_mapping(
                external_port=8080,
                internal_port=9000,
                internal_client="10.0.0.5",
                protocol="tcp",
            )
            assert client._services_cache is None


# ── delete_port_mapping ──


class TestDeletePortMapping:
    def test_success(self, client):
        with patch("gost_client.requests.request") as mock_req:
            mock_req.return_value = _mock_resp(200, {"code": 0})
            result = client.delete_port_mapping(external_port=8080, protocol="tcp")
            assert result["code"] == 0
            call = mock_req.call_args_list[0]
            assert call[0][0] == "DELETE"
            assert call[0][1] == "http://gost:8000/config/services/upnp_8080_tcp"

    def test_404_swallowed(self, client):
        import requests as req_mod

        with patch("gost_client.requests.request") as mock_req:
            resp = Mock(status_code=404)
            resp.raise_for_status.side_effect = req_mod.exceptions.HTTPError(
                "404", response=resp
            )
            resp.text = "Not Found"
            mock_req.return_value = resp
            result = client.delete_port_mapping(external_port=8080, protocol="tcp")
            assert result["code"] == 0

    def test_other_error_raises(self, client):
        import requests as req_mod

        with patch("gost_client.requests.request") as mock_req:
            resp = Mock(status_code=500)
            resp.raise_for_status.side_effect = req_mod.exceptions.HTTPError(
                "500", response=resp
            )
            resp.text = "Internal error"
            mock_req.return_value = resp
            with pytest.raises(GostApiError):
                client.delete_port_mapping(external_port=8080, protocol="tcp")

    def test_cache_cleared_on_delete(self, client):
        import requests as req_mod

        with patch("gost_client.requests.request") as mock_req:
            mock_req.return_value = _mock_resp(200, [])
            client.get_services()
            assert client._services_cache is not None

            resp = Mock(status_code=404)
            resp.raise_for_status.side_effect = req_mod.exceptions.HTTPError(
                "404", response=resp
            )
            resp.text = ""
            mock_req.return_value = resp
            client.delete_port_mapping(external_port=8080, protocol="tcp")
            assert client._services_cache is None


# ── get_port_mappings ──


class TestGetPortMappings:
    def test_filters_by_upnp_metadata(self, client):
        services = [
            {
                "name": "svc1",
                "metadata": {
                    "upnp": True,
                    "external_port": 8080,
                    "internal_port": 9000,
                    "internal_client": "10.0.0.5",
                    "protocol": "tcp",
                    "description": "a",
                    "remote_host": "",
                    "enabled": True,
                    "lease_duration": 0,
                    "created_at": 1000,
                },
            },
            {"name": "svc2", "metadata": {"upnp": False}},
            {"name": "svc3", "metadata": {}},
            {"name": "svc4"},
        ]
        with patch.object(client, "get_services", return_value=services):
            mappings = client.get_port_mappings()
            assert len(mappings) == 1
            assert mappings[0]["external_port"] == 8080

    def test_reads_all_fields(self, client):
        services = [
            {
                "name": "test",
                "metadata": {
                    "upnp": True,
                    "external_port": 8080,
                    "internal_port": 9000,
                    "internal_client": "10.0.0.5",
                    "protocol": "tcp",
                    "description": "test desc",
                    "remote_host": "192.168.1.1",
                    "enabled": True,
                    "lease_duration": 3600,
                    "created_at": 1000,
                },
            }
        ]
        with patch.object(client, "get_services", return_value=services):
            m = client.get_port_mappings()[0]
            assert m["remote_host"] == "192.168.1.1"
            assert m["external_port"] == 8080
            assert m["protocol"] == "TCP"
            assert m["internal_port"] == 9000
            assert m["internal_client"] == "10.0.0.5"
            assert m["description"] == "test desc"
            assert m["enabled"] is True
            assert "lease_duration_remaining" in m

    def test_protocol_uppercased(self, client):
        services = [
            {
                "name": "test",
                "metadata": {
                    "upnp": True,
                    "external_port": 8080,
                    "internal_port": 9000,
                    "internal_client": "10.0.0.5",
                    "protocol": "udp",
                    "description": "",
                    "remote_host": "",
                    "enabled": True,
                    "lease_duration": 0,
                    "created_at": 1000,
                },
            }
        ]
        with patch.object(client, "get_services", return_value=services):
            m = client.get_port_mappings()[0]
            assert m["protocol"] == "UDP"

    def test_empty_when_no_upnp(self, client):
        with patch.object(client, "get_services", return_value=[]):
            assert client.get_port_mappings() == []

    def test_lease_remaining_calculation(self, client):
        now = time.time()
        services = [
            {
                "name": "test",
                "metadata": {
                    "upnp": True,
                    "external_port": 8080,
                    "internal_port": 9000,
                    "internal_client": "10.0.0.5",
                    "protocol": "tcp",
                    "description": "",
                    "remote_host": "",
                    "enabled": True,
                    "lease_duration": 3600,
                    "created_at": int(now - 100),
                },
            }
        ]
        with patch.object(client, "get_services", return_value=services):
            m = client.get_port_mappings()[0]
            assert m["lease_duration_remaining"] <= 3500
            assert m["lease_duration_remaining"] > 3490


# ── get_port_mapping_by_index ──


class TestGetPortMappingByIndex:
    def test_valid_index(self, client):
        with patch.object(client, "get_port_mappings", return_value=[
            {"external_port": 8080},
            {"external_port": 9090},
        ]):
            assert client.get_port_mapping_by_index(0)["external_port"] == 8080
            assert client.get_port_mapping_by_index(1)["external_port"] == 9090

    def test_out_of_range(self, client):
        with patch.object(client, "get_port_mappings", return_value=[]):
            assert client.get_port_mapping_by_index(5) is None


# ── get_services ──


class TestGetServices:
    def test_list_response(self, client):
        with patch("gost_client.requests.request") as mock_req:
            mock_req.return_value = _mock_resp(200, [{"name": "svc1"}])
            svcs = client.get_services()
            assert len(svcs) == 1

    def test_dict_with_data_key(self, client):
        with patch("gost_client.requests.request") as mock_req:
            mock_req.return_value = _mock_resp(200, {"code": 0, "data": [{"name": "svc1"}]})
            svcs = client.get_services()
            assert len(svcs) == 1

    def test_empty_on_exception(self, client):
        with patch("gost_client.requests.request") as mock_req:
            mock_req.side_effect = GostConnectionError("fail")
            assert client.get_services() == []

    def test_cache_used(self, client):
        with patch("gost_client.requests.request") as mock_req:
            mock_req.return_value = _mock_resp(200, [{"name": "svc1"}])
            client.get_services()
            assert mock_req.call_count == 1
            client.get_services()
            assert mock_req.call_count == 1  # cached


# ── helpers ──


class TestHelpers:
    def test_is_available_true(self, client):
        with patch("gost_client.requests.get") as mock_get:
            mock_get.return_value = _mock_resp(200)
            assert client.is_available() is True

    def test_is_available_false(self, client):
        import requests as req_mod

        with patch("gost_client.requests.get") as mock_get:
            mock_get.side_effect = req_mod.exceptions.ConnectionError("fail")
            assert client.is_available() is False

    def test_has_port_mapping_true(self, client):
        with patch.object(client, "get_port_mappings", return_value=[
            {"external_port": 8080, "protocol": "TCP"},
        ]):
            assert client.has_port_mapping(8080, "tcp") is True

    def test_has_port_mapping_false(self, client):
        with patch.object(client, "get_port_mappings", return_value=[
            {"external_port": 9090, "protocol": "TCP"},
        ]):
            assert client.has_port_mapping(8080, "tcp") is False

    def test_get_expired_services(self, client):
        now = time.time()
        services = [
            {
                "name": "s1",
                "metadata": {
                    "upnp": True,
                    "external_port": 8080,
                    "protocol": "tcp",
                    "created_at": int(now - 10000),
                    "lease_duration": 100,
                },
            },
            {
                "name": "s2",
                "metadata": {
                    "upnp": True,
                    "external_port": 9090,
                    "protocol": "tcp",
                    "created_at": int(now),
                    "lease_duration": 3600,
                },
            },
            {"name": "s3", "metadata": {"upnp": False}},
        ]
        with patch.object(client, "get_services", return_value=services):
            expired = client.get_expired_services()
            assert len(expired) == 1
            assert expired[0]["external_port"] == 8080

    def test_get_expired_returns_empty_when_none(self, client):
        now = time.time()
        services = [
            {
                "name": "s1",
                "metadata": {
                    "upnp": True,
                    "external_port": 8080,
                    "protocol": "tcp",
                    "created_at": int(now),
                    "lease_duration": 3600,
                },
            }
        ]
        with patch.object(client, "get_services", return_value=services):
            assert client.get_expired_services() == []

    def test_get_expired_handles_no_lease(self, client):
        services = [
            {
                "name": "s1",
                "metadata": {
                    "upnp": True,
                    "external_port": 8080,
                    "protocol": "tcp",
                    "created_at": int(time.time()),
                    "lease_duration": 0,
                },
            }
        ]
        with patch.object(client, "get_services", return_value=services):
            assert client.get_expired_services() == []

    def test_get_expired_handles_missing_created_at(self, client):
        services = [
            {
                "name": "s1",
                "metadata": {
                    "upnp": True,
                    "external_port": 8080,
                    "protocol": "tcp",
                    "lease_duration": 3600,
                },
            }
        ]
        with patch.object(client, "get_services", return_value=services):
            assert client.get_expired_services() == []
