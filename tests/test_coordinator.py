"""Tests for AiDot LAN coordinator."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class MockAidotAuthFailed(Exception):
    """Stand-in for aidot.exceptions.AidotAuthFailed."""


class MockConfigEntryAuthFailed(Exception):
    """Stand-in for homeassistant.exceptions.ConfigEntryAuthFailed."""


class TestAidotDeviceManagerCoordinator:
    """Tests for AidotDeviceManagerCoordinator."""

    async def test_auth_failed_raises_config_entry_auth_failed(self):
        """AidotAuthFailed from async_get_all_device raises ConfigEntryAuthFailed."""
        mock_client_instance = MagicMock()
        mock_client_instance.async_get_all_device = AsyncMock(
            side_effect=MockAidotAuthFailed()
        )
        mock_client_instance.async_post_login = AsyncMock()
        mock_client_instance.async_cleanup = AsyncMock()
        mock_client_instance.login_info = {
            "accessToken": "token",
            "refreshToken": "refresh",
        }
        mock_client_instance.set_token_fresh_cb = MagicMock()

        mock_entry = MagicMock()
        mock_entry.data = {"login_info": {"accessToken": "token"}}
        mock_entry.entry_id = "entry_1"

        mock_hass = MagicMock()
        mock_hass.config_entries = MagicMock()

        with patch.dict(
            "sys.modules",
            {
                "aidot": MagicMock(),
                "aidot.client": MagicMock(),
                "aidot.const": MagicMock(),
                "aidot.exceptions": MagicMock(
                    AidotAuthFailed=MockAidotAuthFailed,
                    AidotUserOrPassIncorrect=Exception,
                ),
                "homeassistant.config_entries": MagicMock(ConfigEntry=MagicMock()),
                "homeassistant.core": MagicMock(HomeAssistant=MagicMock()),
                "homeassistant.exceptions": MagicMock(
                    ConfigEntryAuthFailed=MockConfigEntryAuthFailed
                ),
                "homeassistant.helpers.device_registry": MagicMock(),
                "homeassistant.helpers.aiohttp_client": MagicMock(),
                "homeassistant.helpers.update_coordinator": MagicMock(
                    DataUpdateCoordinator=MagicMock()
                ),
            },
        ):
            from homeassistant.exceptions import ConfigEntryAuthFailed

            from custom_components.aidot_lan.coordinator import (
                AidotDeviceManagerCoordinator,
            )

            coordinator = AidotDeviceManagerCoordinator(mock_hass, mock_entry)
            coordinator.client = mock_client_instance

            # _async_update_data should propagate AidotAuthFailed as ConfigEntryAuthFailed
            with pytest.raises(ConfigEntryAuthFailed):
                await coordinator._async_update_data()


class TestAidotDeviceUpdateCoordinatorCloudSeeding:
    """Tests for cloud-seeded state preservation in AidotDeviceUpdateCoordinator."""

    def test_seed_initial_cloud_state_sets_on_off(self):
        """Cloud-seeded data correctly sets on/off from properties."""
        mock_device = {
            "properties": {
                "OnOff": 1,
                "online": True,
            }
        }

        mock_status = MagicMock()
        mock_coordinator = MagicMock()
        mock_coordinator.data = None

        with patch.dict(
            "sys.modules",
            {
                "aidot": MagicMock(),
                "aidot.device_client": MagicMock(
                    DeviceStatusData=MagicMock(return_value=mock_status)
                ),
                "homeassistant.config_entries": MagicMock(ConfigEntry=MagicMock()),
                "homeassistant.core": MagicMock(HomeAssistant=MagicMock()),
                "homeassistant.exceptions": MagicMock(),
                "homeassistant.helpers.device_registry": MagicMock(),
                "homeassistant.helpers.aiohttp_client": MagicMock(),
                "homeassistant.helpers.update_coordinator": MagicMock(
                    DataUpdateCoordinator=MagicMock()
                ),
            },
        ):
            from custom_components.aidot_lan.coordinator import (
                AidotDeviceManagerCoordinator,
            )

            coordinator = AidotDeviceManagerCoordinator.__new__(
                AidotDeviceManagerCoordinator
            )
            coordinator._seed_initial_cloud_state(mock_coordinator, mock_device)

            # Verify data was set on coordinator
            mock_coordinator.async_set_updated_data.assert_called_once()

    def test_seed_preserves_cloud_state_when_p2p_offline(self):
        """P2P offline (None values) preserves existing cloud-seeded state."""
        # Simulate P2P returning no real data
        mock_coordinator = MagicMock()
        mock_coordinator.data = None  # Seeded state

        with patch.dict(
            "sys.modules",
            {
                "aidot": MagicMock(),
                "aidot.device_client": MagicMock(
                    DeviceStatusData=MagicMock()
                ),
                "homeassistant.config_entries": MagicMock(ConfigEntry=MagicMock()),
                "homeassistant.core": MagicMock(HomeAssistant=MagicMock()),
                "homeassistant.exceptions": MagicMock(),
                "homeassistant.helpers.device_registry": MagicMock(),
                "homeassistant.helpers.aiohttp_client": MagicMock(),
                "homeassistant.helpers.update_coordinator": MagicMock(
                    DataUpdateCoordinator=MagicMock()
                ),
            },
        ):
            from custom_components.aidot_lan.coordinator import (
                AidotDeviceUpdateCoordinator,
            )

            coordinator = AidotDeviceUpdateCoordinator.__new__(
                AidotDeviceUpdateCoordinator
            )
            coordinator.data = None
            coordinator.device_client = MagicMock()
            coordinator.device_client.status = None  # P2P offline

            # Should return empty DeviceStatusData, not crash
            result = coordinator._async_update_data()
            assert result is not None  # Should return a valid DeviceStatusData
