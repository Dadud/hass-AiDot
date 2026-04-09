"""Support for AiDot LAN lights — P2P with optimistic local state fallback."""

from __future__ import annotations

from typing import Any

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP_KELVIN,
    ATTR_RGBW_COLOR,
    ColorMode,
    LightEntity,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import (
    CONNECTION_NETWORK_MAC,
    DeviceInfo,
    format_mac,
)
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import AidotConfigEntry, AidotDeviceUpdateCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AidotConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up AiDot LAN lights from a config entry."""
    coordinator = entry.runtime_data
    async_add_entities(
        AidotLight(device_coordinator)
        for device_coordinator in coordinator.device_coordinators.values()
    )


class AidotLight(CoordinatorEntity[AidotDeviceUpdateCoordinator], LightEntity):
    """Representation of an AiDot Wi-Fi Light.

    Supports both P2P direct control (when reachable) and optimistic local
    state updates (when P2P is blocked).  If the device is offline the service
    call updates Home Assistant's entity state immediately without waiting for
    an acknowledgement from the physical bulb.
    """

    _attr_has_entity_name = True
    _attr_name = None

    def __init__(self, coordinator: AidotDeviceUpdateCoordinator) -> None:
        """Initialize the light."""
        super().__init__(coordinator)
        info = coordinator.device_client.info
        self._attr_unique_id = info.dev_id

        # CCT range
        if hasattr(info, "cct_max"):
            self._attr_max_color_temp_kelvin = info.cct_max
        if hasattr(info, "cct_min"):
            self._attr_min_color_temp_kelvin = info.cct_min

        # Device info
        model_id = info.model_id
        manufacturer = model_id.split(".")[0]
        model = model_id[len(manufacturer) + 1 :]
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._attr_unique_id)},
            connections={(CONNECTION_NETWORK_MAC, format_mac(info.mac))},
            manufacturer=manufacturer,
            model=model,
            name=info.name,
            hw_version=info.hw_version,
        )

        # Colour capabilities
        if info.enable_rgbw:
            self._attr_color_mode = ColorMode.RGBW
            self._attr_supported_color_modes = {ColorMode.RGBW, ColorMode.COLOR_TEMP}
        elif info.enable_cct:
            self._attr_color_mode = ColorMode.COLOR_TEMP
            self._attr_supported_color_modes = {ColorMode.COLOR_TEMP}
        else:
            self._attr_color_mode = ColorMode.BRIGHTNESS
            self._attr_supported_color_modes = {ColorMode.BRIGHTNESS}

        self._update_status()

    # -------------------------------------------------------------------------
    # State synchronisation
    # -------------------------------------------------------------------------
    def _update_status(self) -> None:
        """Sync attributes from the current coordinator data."""
        data = self.coordinator.data
        if data is None:
            self._attr_available = False
            return
        self._attr_available = bool(data.online)
        self._attr_is_on = bool(data.on) if data.on is not None else False
        self._attr_brightness = getattr(data, "dimming", None)
        self._attr_color_temp_kelvin = getattr(data, "cct", None)
        self._attr_rgbw_color = getattr(data, "rgbw", None)

    @property
    def available(self) -> bool:
        """Return True if the coordinator has real device data."""
        return self.coordinator.data is not None and bool(self.coordinator.data.online)

    @callback
    def _handle_coordinator_update(self) -> None:
        """React to coordinator data changes."""
        self._update_status()
        super()._handle_coordinator_update()

    # -------------------------------------------------------------------------
    # Control methods — optimistic update pattern
    #
    # If P2P is reachable the command goes to the bulb and the resulting
    # status push updates the coordinator.  If P2P is blocked the command
    # raises ConnectionError; we catch it, update local state optimistically,
    # and let the periodic polling refresh the real state when connectivity
    # returns.
    # -------------------------------------------------------------------------
    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the light on (or apply parameters to an already-on light)."""
        # Optimistic local update — applies immediately in HA UI
        self.coordinator.data.on = True
        self._attr_is_on = True

        try:
            if ATTR_BRIGHTNESS in kwargs:
                brightness = kwargs[ATTR_BRIGHTNESS]
                self.coordinator.data.dimming = brightness
                self._attr_brightness = brightness
                await self.coordinator.device_client.async_set_brightness(brightness)
            elif ATTR_COLOR_TEMP_KELVIN in kwargs:
                color_temp_kelvin = kwargs[ATTR_COLOR_TEMP_KELVIN]
                self.coordinator.data.cct = color_temp_kelvin
                self._attr_color_temp_kelvin = color_temp_kelvin
                self._attr_color_mode = ColorMode.COLOR_TEMP
                await self.coordinator.device_client.async_set_cct(color_temp_kelvin)
            elif ATTR_RGBW_COLOR in kwargs:
                rgbw_color = kwargs[ATTR_RGBW_COLOR]
                self.coordinator.data.rgbw = rgbw_color
                self._attr_rgbw_color = rgbw_color
                self._attr_color_mode = ColorMode.RGBW
                await self.coordinator.device_client.async_set_rgbw(rgbw_color)
            else:
                await self.coordinator.device_client.async_turn_on()
        except ConnectionError:
            # Device offline — local state already updated optimistically above
            pass

        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the light off."""
        try:
            await self.coordinator.device_client.async_turn_off()
        except ConnectionError:
            # Device offline — local state updated optimistically below
            pass

        self.coordinator.data.on = False
        self._attr_is_on = False
        self.async_write_ha_state()
