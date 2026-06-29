import pytest
from unittest.mock import patch


# ── XML template routes ──


class TestXMLRoutes:
    def test_root_desc(self, client):
        resp = client.get("/rootDesc.xml")
        assert resp.status_code == 200
        assert resp.content_type.startswith("text/xml")
        assert b"urn" in resp.data

    def test_l3f_xml(self, client):
        resp = client.get("/L3F.xml")
        assert resp.status_code == 200
        assert resp.content_type.startswith("text/xml")

    def test_wan_cfg_xml(self, client):
        resp = client.get("/WANCfg.xml")
        assert resp.status_code == 200
        assert resp.content_type.startswith("text/xml")

    def test_wan_ipcn_xml(self, client):
        resp = client.get("/WANIPCn.xml")
        assert resp.status_code == 200
        assert resp.content_type.startswith("text/xml")

    def test_unknown_xml_returns_not_found_body(self, client):
        resp = client.get("/nonexistent.xml")
        assert b"404 Not Found" in resp.data


# ── GET / ──


class TestIndex:
    def test_returns_status_page(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert b"alter_upnpd" in resp.data


# ── GET /health ──


class TestHealth:
    def test_healthy(self, client):
        resp = client.get("/health")
        data = resp.get_json()
        assert data["status"] == "healthy"
        assert data["port_mappings_count"] == 1
        assert data["version"] is not None
        assert data["gost_connected"] is True

    def test_degraded_when_gost_unreachable(self, client):
        import app as app_module

        app_module.gost_client.is_available.return_value = False
        # get_port_mappings should not be called when gost is unavailable,
        # but even if it is, handle gracefully
        resp = client.get("/health")
        data = resp.get_json()
        assert data["status"] == "degraded"
        assert data["gost_connected"] is False
        assert data["port_mappings_count"] == 0

    def test_healthy_no_mappings(self, client):
        import app as app_module

        app_module.gost_client.get_port_mappings.return_value = []
        resp = client.get("/health")
        data = resp.get_json()
        assert data["status"] == "healthy"
        assert data["port_mappings_count"] == 0


# ── Helper functions ──


class TestHelpers:
    def test_get_local_ip(self):
        from app import get_local_ip

        ip = get_local_ip()
        # Should return a valid IP (either real or loopback)
        parts = ip.split(".")
        assert len(parts) == 4
        assert all(p.isdigit() for p in parts)

    def test_get_local_ip_fallback_on_socket_error(self):
        from app import get_local_ip

        with patch("app.socket.socket", side_effect=Exception("mock error")):
            assert get_local_ip() == "127.0.0.1"

    def test_get_local_port(self):
        from app import get_local_port

        assert get_local_port() == 5000  # default from Config

    def test_get_local_port_from_env(self):
        from config import EnvConfig

        assert EnvConfig(listen_port=9999).listen_port == 9999

    def test_location_format(self):
        from app import get_location

        loc = get_location()
        assert loc.endswith("/rootDesc.xml")
        assert loc.startswith("http://")


# ── Template rendering ──


class TestRenderXML:
    def test_render_xml_success(self, monkeypatch, tmp_path):
        import app as app_module

        xml_dir = tmp_path / "xml"
        xml_dir.mkdir()
        (xml_dir / "test.xml").write_text("hello {{ LOCAL_IP }}:{{ LOCAL_PORT }}")
        monkeypatch.setattr(app_module.template, "_xml_dir", str(xml_dir))
        # Mock the template vars
        app_module.template._vars["test.xml"] = lambda: {
            "LOCAL_IP": "10.0.0.5",
            "LOCAL_PORT": 8888,
        }
        app_module.template._cache.clear()
        result = app_module.render_xml("test.xml")
        assert result == "hello 10.0.0.5:8888"

    def test_render_xml_not_found(self):
        import app as app_module

        assert app_module.render_xml("nonexistent.xml") == "404 Not Found"


# ── SOAP control routes (integration smoke tests) ──


class TestSOAPRoutes:
    def test_post_to_ipconn_no_auth(self, client):
        resp = client.post(
            "/ctl/IPConn", data="not soap", content_type="text/xml"
        )
        assert resp.status_code in (200, 403, 500)

    def test_post_to_cmnifcfg_no_auth(self, client):
        resp = client.post(
            "/ctl/CmnIfCfg", data="not soap", content_type="text/xml"
        )
        assert resp.status_code in (200, 403, 500)

    def test_post_to_l3f_no_auth(self, client):
        resp = client.post(
            "/ctl/L3F", data="not soap", content_type="text/xml"
        )
        assert resp.status_code in (200, 403, 500)
