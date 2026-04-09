"""Tests for AiDot LAN light entity."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class MockDeviceStatusData:
    """Mimics aidot.device_client.DeviceStatusData."""

    def __init__(self):
        self.online = True
        self.on = True
        self.dimming = 204
        self.cct = 4000
        self.rgbw = (255, 128, 64, 32)


class TestAidotLight:
    """Tests for AidotLight entity."""

    @pytest.fixture
    def mock_coordinator(self, mock_device_client):
        """Return a mock AidotDeviceUpdateCoordinator."""
        coordinator = MagicMock()
        coordinator.data = MockDeviceStatusData()
        coordinator.device_client = mock_device_client
        coordinator.async_set_updated_data = MagicMock()
        coordinator.async_write_ha_state = MagicMock()
        return coordinator

    @pytest.fixture
    def light_entity(self, mock_coordinator):
        """Return an AidotLight entity backed by a mock coordinator."""
        with patch.dict(
            "sys.modules",
            {
                "homeassistant.components.light": MagicMock(),
                "homeassistant.components.light.ATTR_BRIGHTNESS": "brightness",
                "homeassistant.components.light.ATTR_COLOR_TEMP_KELVIN": "color_temp_kelvin",
                "homeassistant.components.light.ATTR_RGBW_COLOR": "rgbw_color",
                "homeassistant.components.light.ColorMode": MagicMock(
                    RGBW="rgbw",
                    COLOR_TEMP="color_temp",
                    BRIGHTNESS="brightness",
                ),
                "homeassistant.components.light.LightEntity": MagicMock(),
                "homeassistant.core": MagicMock(
                    HomeAssistant=MagicMock(),
                    callback=MagicMock(),
                ),
                "homeassistant.helpers.device_registry": MagicMock(
                    DeviceInfo=MagicMock(),
                    CONNECTION_NETWORK_MAC=MagicMock(),
                    format_mac=MagicMock(),
                ),
                "homeassistant.helpers.entity_platform": MagicMock(
                    AddConfigEntryEntitiesCallback=MagicMock(),
                ),
                "homeassistant.helpers.update_coordinator": MagicMock(
                    CoordinatorEntity=MagicMock(),
                ),
                "aidot": MagicMock(),
                "aidot.device_client": MagicMock(
                    DeviceStatusData=MockDeviceStatusData
                ),
            },
        ):
            from custom_components.aidot_lan.light import AidotLight

            entity = AidotLight(mock_coordinator)
            return entity

    def test_unique_id_set(self, light_entity):
        """Unique ID is derived from device dev_id."""
        assert light_entity._attr_unique_id == "dev_001"

    def test_available_true_when_online(self, light_entity):
        """Entity is available when online flag is True."""
        light_entity.coordinator.data.online = True
        light_entity.coordinator.data = light_entity.coordinator.data
        assert light_entity.available is True

    def test_available_false_when_offline(self, light_entity):
        """Entity is unavailable when online flag is False."""
        light_entity.coordinator.data.online = False
        assert light_entity.available is False

    def test_brightness_converted_from_percent(self, light_entity):
        """Brightness stored as 0-255 internally (80% -> 204)."""
        light_entity.coordinator.data.dimming = 204
        light_entity._update_status()
        assert light_entity._attr_brightness == 204

    async def test_async_turn_on_brightness(self, light_entity, mock_device_client):
        """Turn on with brightness updates coordinator optimistically."""
        light_entity.coordinator.data.on = False
        light_entity.coordinator.data.dimming = 0

        await light_entity.async_turn_on(brightness=128)

        assert light_entity._attr_is_on is True
        assert light_entity._attr_brightness == 128
        mock_device_client.async_set_brightness.assert_called_once_with(128)

    async def test_async_turn_on_cct(self, light_entity, mock_device_client):
        """Turn on with color temp updates coordinator optimistically."""
        await light_entity.async_turn_on(color_temp_kelvin=3000)

        assert light_entity._attr_is_on is True
        assert light_entity._attr_color_temp_kelvin == 3000
        mock_device_client.async_set_cct.assert_called_once_with(3000)

    async def test_async_turn_on_rgbw(self, light_entity, mock_device_client):
        """Turn on with RGBW updates coordinator optimistically."""
        rgbw = (255, 0, 128, 64)
        await light_entity.async_turn_on(rgbw_color=rgbw)

        assert light_entity._attr_is_on is True
        assert light_entity._attr_rgbw_color == rgbw
        mock_device_client.async_set_rgbw.assert_called_once_with(rgbw)

    async def test_async_turn_on_no_args_calls_turn_on(self, light_entity, mock_device_client):
        """Turn on with no args calls device async_turn_on."""
        light_entity.coordinator.data.on = False

        await light_entity.async_turn_on()

        mock_device_client.async_turn_on.assert_called_once()

    async def test_async_turn_on_connection_error_still_updates_optimistically(
        self, light_entity, mock_device_client
    ):
        """ConnectionError (P2P offline) does not prevent optimistic update."""
        mock_device_client.async_set_brightness = AsyncMock(
            side_effect=ConnectionError()
        )
        light_entity.coordinator.data.on = False
        light_entity.coordinator.data.dimming = 0

        # Should NOT raise — optimistic update still applies
        await light_entity.async_turn_on(brightness=128)

        assert light_entity._attr_is_on is True
        assert light_entity._attr_brightness == 128

    async def test_async_turn_off(self, light_entity, mock_device_client):
        """Turn off calls device async_turn_off and updates state."""
        light_entity.coordinator.data.on = True

        await light_entity.async_turn_off()

        mock_device_client.async_turn_off.assert_called_once()
        assert light_entity._attr_is_on is False

    async def test_async_turn_off_connection_error_still_updates_state(
        self, light_entity, mock_device_client
    ):
        """ConnectionError on turn_off still updates local state optimistically."""
        mock_device_client.async_turn_off = AsyncMock(side_effect=ConnectionError())
        light_entity.coordinator.data.on = True

        # Should NOT raise — optimistic update still applies
        await light_entity.async_turn_off()

        assert light_entity._attr_is_on is False
