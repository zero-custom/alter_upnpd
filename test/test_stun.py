import time
import pytest
from unittest.mock import patch, Mock

from stun_client import StunClient


class TestGetWanIp:
    def test_default_fallback(self):
        client = StunClient()
        assert client.get_wan_ip() == "192.0.2.1"

    def test_custom_fallback(self):
        client = StunClient(fallback_wan_ip="10.0.0.1")
        assert client.get_wan_ip() == "10.0.0.1"


class TestStart:
    def test_start_is_idempotent(self):
        client = StunClient()
        with patch.object(client, "_refresh_loop") as mock_loop:
            client.start()
            client.start()
            assert mock_loop.call_count == 1

    def test_reset_cache_allows_reinit(self):
        client = StunClient()
        with patch.object(client, "_refresh_loop") as mock_loop:
            client.start()
            assert client._started is True
            client.reset_cache()
            assert client._started is False
            assert client.get_wan_ip() == "192.0.2.1"


class TestRefresh:
    def test_success_updates_wan_ip(self):
        client = StunClient()
        with patch("stun_client.py3stun.get_ip_info") as mock_stun:
            mock_stun.return_value = ("Cone", "203.0.113.5", 3478)
            client._refresh()
            assert client.get_wan_ip() == "203.0.113.5"

    def test_failure_keeps_fallback(self):
        client = StunClient()
        with patch("stun_client.py3stun.get_ip_info") as mock_stun:
            mock_stun.side_effect = Exception("STUN server unreachable")
            client._refresh()
            assert client.get_wan_ip() == "192.0.2.1"

    def test_empty_ip_keeps_fallback(self):
        client = StunClient()
        with patch("stun_client.py3stun.get_ip_info") as mock_stun:
            mock_stun.return_value = ("Unknown", "", 0)
            client._refresh()
            assert client.get_wan_ip() == "192.0.2.1"

    def test_retries_on_failure(self):
        client = StunClient(retries=3)
        with patch("stun_client.py3stun.get_ip_info") as mock_stun:
            mock_stun.side_effect = [
                Exception("fail1"),
                Exception("fail2"),
                ("Cone", "203.0.113.5", 3478),
            ]
            client._refresh()
            assert client.get_wan_ip() == "203.0.113.5"
            assert mock_stun.call_count == 3

    def test_exhausts_retries(self):
        client = StunClient(retries=4)
        with patch("stun_client.py3stun.get_ip_info") as mock_stun:
            mock_stun.side_effect = Exception("always fail")
            client._refresh()
            assert client.get_wan_ip() == "192.0.2.1"
            assert mock_stun.call_count == 4


class TestRefreshLoop:
    def test_loop_calls_refresh(self):
        client = StunClient()
        with patch.object(client, "_refresh") as mock_refresh:
            mock_refresh.return_value = None
            with patch("stun_client.time.sleep") as mock_sleep:
                mock_sleep.side_effect = [None, KeyboardInterrupt]
                try:
                    client._refresh_loop()
                except KeyboardInterrupt:
                    pass
                assert mock_refresh.call_count == 2

    def test_loop_sleeps_interval(self):
        client = StunClient(refresh_interval=86400)
        with patch.object(client, "_refresh") as mock_refresh:
            mock_refresh.return_value = None
            with patch("stun_client.time.sleep") as mock_sleep:
                mock_sleep.side_effect = KeyboardInterrupt
                try:
                    client._refresh_loop()
                except KeyboardInterrupt:
                    pass
                mock_sleep.assert_called_once_with(86400)


class TestIndependentInstances:
    def test_two_instances_dont_interfere(self):
        c1 = StunClient(fallback_wan_ip="1.1.1.1")
        c2 = StunClient(fallback_wan_ip="2.2.2.2")
        assert c1.get_wan_ip() == "1.1.1.1"
        assert c2.get_wan_ip() == "2.2.2.2"

    def test_custom_server(self):
        client = StunClient(stun_server="custom.stun.example.com:3478")
        assert client._stun_server == "custom.stun.example.com:3478"
