"""Pytest fixtures and mocks for AiDot LAN tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
import pytest

# ---------------------------------------------------------------------------
# Mock homeassistant before any integration modules are imported
# ---------------------------------------------------------------------------


class MockHomeAssistant:
    """Stand-in for homeassistant.core.HomeAssistant."""

    def __init__(self) -> None:
        self.config_entries = MagicMock()
        self.config_entries.async_get_entry = MagicMock()
        self.config_entries.async_update_entry = MagicMock()
        self.config_entries.async_forward_entry_setups = AsyncMock()
        self.config_entries.async_unload_platforms = AsyncMock()
        self.data = {}


class MockConfigEntry:
    """Stand-in for homeassistant.config_entries.ConfigEntry."""

    def __init__(
        self,
        entry_id: str = "entry_1",
        data: dict | None = None,
        runtime_data: Any = None,
    ) -> None:
        self.entry_id = entry_id
        self.data = data or {}
        self.runtime_data = runtime_data


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_hass():
    """Return a mock HomeAssistant instance."""
    return MockHomeAssistant()


@pytest.fixture
def mock_config_entry():
    """Return a mock ConfigEntry with cloud login_info."""
    return MockConfigEntry(
        entry_id="test_entry",
        data={
            "login_info": {
                "accessToken": "test_token",
                "refreshToken": "test_refresh",
                "username": "test@example.com",
                "countryCode": "US",
            }
        },
    )


@pytest.fixture
def mock_aidot_client():
    """Return a mock AidotClient."""
    client = MagicMock()
    client.async_post_login = AsyncMock(
        return_value={
            "accessToken": "new_token",
            "refreshToken": "new_refresh",
            "username": "test@example.com",
        }
    )
    client.async_get_all_device = AsyncMock(
        return_value={
            "device_list": [
                {
                    "id": "dev_001",
                    "type": "light",
                    "aesKey": ["abcdef123456"],
                    "name": "Bedroom Light",
                    "model_id": "LK.light.A000108",
                    "mac": "aa:bb:cc:dd:ee:ff",
                    "hw_version": "1.0",
                    "properties": {
                        "online": True,
                        "OnOff": 1,
                        "Dimming": "80",
                        "CCT": "4000",
                        "RGBW": "-224833024",
                    },
                }
            ]
        }
    )
    client.login_info = {
        "accessToken": "test_token",
        "refreshToken": "test_refresh",
        "username": "test@example.com",
    }
    client.get_identifier = MagicMock(return_value="test@example.com")
    return client


@pytest.fixture
def mock_device_client():
    """Return a mock DeviceClient with status data."""
    client = MagicMock()
    client.info = MagicMock()
    client.info.dev_id = "dev_001"
    client.info.name = "Bedroom Light"
    client.info.model_id = "LK.light.A000108"
    client.info.mac = "aa:bb:cc:dd:ee:ff"
    client.info.hw_version = "1.0"
    client.info.enable_rgbw = True
    client.info.enable_cct = True
    client.info.cct_min = 1800
    client.info.cct_max = 6500

    status = MagicMock()
    status.online = True
    status.on = True
    status.dimming = 204
    status.cct = 4000
    status.rgbw = (255, 128, 64, 32)
    client.status = status

    client.async_set_brightness = AsyncMock()
    client.async_set_cct = AsyncMock()
    client.async_set_rgbw = AsyncMock()
    client.async_turn_on = AsyncMock()
    client.async_turn_off = AsyncMock()
    client.on_status_update = None
    return client
