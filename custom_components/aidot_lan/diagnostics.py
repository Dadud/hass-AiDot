"""Diagnostics support for AiDot LAN."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .coordinator import AidotConfigEntry, AidotDeviceManagerCoordinator

TO_REDACT: set[str] = {
    "password",
    "aesKey",
    "accessToken",
    "refreshToken",
    "login_info",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for an AiDot LAN config entry."""
    coordinator: AidotDeviceManagerCoordinator = entry.runtime_data

    device_states = []
    for dev_id, dev_coord in coordinator.device_coordinators.items():
        client = dev_coord.device_client
        info = client.info
        status = dev_coord.data

        device_states.append(
            {
                "device_id": dev_id,
                "name": info.name,
                "model_id": info.model_id,
                "mac": info.mac,
                "hw_version": info.hw_version,
                "online": status.online if status else None,
                "on": status.on if status else None,
                "brightness": status.dimming if status else None,
                "color_temp_kelvin": status.cct if status else None,
                "rgbw": status.rgbw if status else None,
                "enable_rgbw": info.enable_rgbw,
                "enable_cct": info.enable_cct,
                "cct_min": getattr(info, "cct_min", None),
                "cct_max": getattr(info, "cct_max", None),
            }
        )

    return {
        "devices": device_states,
        "integration": {
            "domain": DOMAIN,
            "version": "1.2.0",
            "connected_devices": len(device_states),
            "online_devices": sum(1 for d in device_states if d["online"]),
        },
    }
