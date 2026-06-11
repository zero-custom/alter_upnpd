"""Tests for STUN client — external IP discovery."""

import time
import pytest
from unittest.mock import patch, Mock

import stun_client
from config import Config


@pytest.fixture(autouse=True)
def reset_stun():
    stun_client.reset_cache()
    yield
    stun_client.reset_cache()


class TestGetWanIp:
    def test_default_fallback(self):
        assert stun_client.get_wan_ip() == "1.2.3.4"

    def test_returns_set_value(self):
        import stun_client as sc
        with sc._lock:
            sc._wan_ip = "10.0.0.1"
        assert stun_client.get_wan_ip() == "10.0.0.1"


class TestInit:
    def test_init_starts_thread(self):
        with patch("stun_client._refresh_loop") as mock_loop:
            stun_client.init()
            assert stun_client._started is True

    def test_init_is_idempotent(self):
        with patch("stun_client._refresh_loop") as mock_loop:
            stun_client.init()
            stun_client.init()
            assert stun_client._started is True
            assert mock_loop.call_count == 1

    def test_reset_cache_allows_reinit(self):
        with patch("stun_client._refresh_loop") as mock_loop:
            stun_client.init()
            assert stun_client._started is True
            stun_client.reset_cache()
            assert stun_client._started is False
            assert stun_client.get_wan_ip() == "1.2.3.4"


class TestRefresh:
    def test_success_updates_wan_ip(self):
        with patch("stun_client.py3stun.get_ip_info") as mock_stun:
            mock_stun.return_value = ("Cone", "203.0.113.5", 3478)
            stun_client._refresh()
            assert stun_client.get_wan_ip() == "203.0.113.5"

    def test_failure_keeps_fallback(self):
        with patch("stun_client.py3stun.get_ip_info") as mock_stun:
            mock_stun.side_effect = Exception("STUN server unreachable")
            stun_client._refresh()
            assert stun_client.get_wan_ip() == "1.2.3.4"

    def test_empty_ip_keeps_fallback(self):
        with patch("stun_client.py3stun.get_ip_info") as mock_stun:
            mock_stun.return_value = ("Unknown", "", 0)
            stun_client._refresh()
            assert stun_client.get_wan_ip() == "1.2.3.4"

    def test_retries_on_failure(self):
        with patch("stun_client.py3stun.get_ip_info") as mock_stun:
            mock_stun.side_effect = [
                Exception("fail1"),
                Exception("fail2"),
                ("Cone", "203.0.113.5", 3478),
            ]
            stun_client._refresh()
            assert stun_client.get_wan_ip() == "203.0.113.5"
            assert mock_stun.call_count == 3

    def test_exhausts_retries(self):
        with patch("stun_client.py3stun.get_ip_info") as mock_stun:
            mock_stun.side_effect = Exception("always fail")
            stun_client._refresh()
            assert stun_client.get_wan_ip() == "1.2.3.4"
            assert mock_stun.call_count == 4


class TestRefreshLoop:
    def test_loop_calls_refresh(self):
        with patch("stun_client._refresh") as mock_refresh:
            mock_refresh.return_value = None
            with patch("stun_client.time.sleep") as mock_sleep:
                mock_sleep.side_effect = [None, KeyboardInterrupt]
                try:
                    stun_client._refresh_loop()
                except KeyboardInterrupt:
                    pass
                assert mock_refresh.call_count == 2

    def test_loop_sleeps_interval(self):
        with patch("stun_client._refresh") as mock_refresh:
            mock_refresh.return_value = None
            with patch("stun_client.time.sleep") as mock_sleep:
                mock_sleep.side_effect = KeyboardInterrupt
                try:
                    stun_client._refresh_loop()
                except KeyboardInterrupt:
                    pass
                mock_sleep.assert_called_once_with(86400)
