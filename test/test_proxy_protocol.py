import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

from config import load_env_config
from gost_client import GostClient, PortMappingRepository


class FakeTransport:
    def __init__(self):
        self.calls = []

    def request(self, method, path, **kwargs):
        self.calls.append((method, path, kwargs.get("json")))
        return {}

    @property
    def last_body(self):
        return self.calls[-1][2]


def _add(repo, protocol="tcp"):
    return repo.add(
        external_port=8080,
        internal_port=80,
        internal_client="192.168.1.10",
        protocol=protocol,
        description="test",
    )


def test_default_on_tcp_add_sends_proxy_protocol():
    repo = PortMappingRepository(FakeTransport())
    _add(repo, "tcp")
    handler = repo._transport.last_body["handler"]
    assert handler == {"type": "tcp", "metadata": {"proxyProtocol": 1}}


def test_default_on_tcp_update_sends_proxy_protocol():
    repo = PortMappingRepository(FakeTransport())
    repo.update(
        external_port=8080,
        internal_port=80,
        internal_client="192.168.1.10",
        protocol="tcp",
    )
    handler = repo._transport.last_body["handler"]
    assert handler == {"type": "tcp", "metadata": {"proxyProtocol": 1}}


def test_explicit_off_tcp_has_no_proxy_protocol():
    repo = PortMappingRepository(FakeTransport(), proxy_protocol=False)
    _add(repo, "tcp")
    handler = repo._transport.last_body["handler"]
    assert handler == {"type": "tcp"}


def test_enabled_udp_never_sends_proxy_protocol():
    repo = PortMappingRepository(FakeTransport(), proxy_protocol=True)
    _add(repo, "udp")
    handler = repo._transport.last_body["handler"]
    assert handler == {"type": "udp"}


def test_default_on_udp_has_no_proxy_protocol():
    repo = PortMappingRepository(FakeTransport())
    _add(repo, "udp")
    handler = repo._transport.last_body["handler"]
    assert handler == {"type": "udp"}


def test_facade_default_on():
    transport = FakeTransport()
    client = GostClient(base_url="http://127.0.0.1:8000", transport=transport)
    client.add_port_mapping(
        external_port=8080,
        internal_port=80,
        internal_client="192.168.1.10",
        protocol="tcp",
    )
    assert transport.last_body["handler"] == {"type": "tcp", "metadata": {"proxyProtocol": 1}}


def test_facade_explicit_off():
    transport = FakeTransport()
    client = GostClient(base_url="http://127.0.0.1:8000", transport=transport, proxy_protocol=False)
    client.add_port_mapping(
        external_port=8080,
        internal_port=80,
        internal_client="192.168.1.10",
        protocol="tcp",
    )
    assert transport.last_body["handler"] == {"type": "tcp"}


def test_env_config_default_on(monkeypatch):
    monkeypatch.delenv("GOST_PROXY_PROTOCOL", raising=False)
    assert load_env_config().gost_proxy_protocol is True


def test_env_config_explicit_off_values(monkeypatch):
    for val in ("false", "0", "no", "FALSE"):
        monkeypatch.setenv("GOST_PROXY_PROTOCOL", val)
        assert load_env_config().gost_proxy_protocol is False
