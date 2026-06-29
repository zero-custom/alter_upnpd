import os
import sys

import pytest
from unittest.mock import Mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))


@pytest.fixture
def env_config():
    from config import EnvConfig
    return EnvConfig()


@pytest.fixture
def mock_gost_client():
    from gost_client import GostClient
    client = Mock(spec=GostClient)
    client.base_url = "http://test:8000"
    client.is_available.return_value = True
    client.get_port_mappings.return_value = [{"external_port": 8080}]
    return client


@pytest.fixture
def client(mock_gost_client):
    import app as app_module
    from app_health import HealthService

    app_module.gost_client = mock_gost_client
    app_module.health_service = HealthService(
        gost_client=mock_gost_client,
        version=app_module.VERSION,
        get_local_ip=app_module.get_local_ip,
        get_local_port=app_module.get_local_port,
    )

    import webui
    webui.init(gost_client=mock_gost_client)
    app_module.app.config["TESTING"] = True
    app_module.template._cache.clear()

    with app_module.app.test_client() as test_client:
        yield test_client

    # Teardown
    app_module.template._cache.clear()
