"""Coordinator for AiDot LAN — cloud-seeded with P2P-aware fallback."""

from __future__ import annotations

import ctypes
from datetime import timedelta
import logging
from typing import TYPE_CHECKING

from aidot.client import AidotClient
from aidot.const import (
    CONF_ACCESS_TOKEN,
    CONF_AES_KEY,
    CONF_DEVICE_LIST,
    CONF_ID,
    CONF_LOGIN_INFO,
    CONF_TYPE,
)
from aidot.device_client import DeviceClient, DeviceStatusData
from aidot.exceptions import AidotAuthFailed, AidotUserOrPassIncorrect

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import DOMAIN

if TYPE_CHECKING:
    AidotConfigEntry = ConfigEntry[AidotDeviceManagerCoordinator]
else:
    AidotConfigEntry = ConfigEntry

_LOGGER = logging.getLogger(__name__)

# How often to re-scan for new/removed cloud devices
UPDATE_DEVICE_LIST_INTERVAL = timedelta(hours=6)


class AidotDeviceUpdateCoordinator(DataUpdateCoordinator[DeviceStatusData]):
    """Class to manage per-device P2P state with cloud-seeded fallback.

    Key behaviour (differs from upstream v1.1.1):
    - update_interval=30s provides polling fallback when P2P is silent
    - P2P status that carries no real data (offline/defaults) is ignored,
      preserving either the cloud-seeded initial state or any subsequent
      optimistic local update made by service calls.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: AidotConfigEntry,
        device_client: DeviceClient,
    ) -> None:
        """Initialize the per-device coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=config_entry,
            name=DOMAIN,
            # Polling fallback so the entity stays reasonably fresh even when
            # P2P push does not arrive (e.g. network blip)
            update_interval=timedelta(seconds=30),
        )
        self.device_client = device_client

    async def _async_setup(self) -> None:
        """Register the P2P status callback."""
        self.device_client.on_status_update = self._handle_status_update

    def _handle_status_update(self, status: DeviceStatusData) -> None:
        """Handle incoming P2P status push."""
        self.async_set_updated_data(status)

    async def _async_update_data(self) -> DeviceStatusData:
        """Return current device status.

        If P2P has not delivered any real state yet (offline or still
        connecting), preserve whatever cloud-seeded or optimistically-updated
        state we already hold.  Only accept the client status when it carries
        genuine values.
        """
        client_status = self.device_client.status
        if client_status is None or client_status.online is None or client_status.dimming is None:
            # P2P not connected — keep existing state (cloud-seeded or local)
            if self.data is not None:
                return self.data
            return DeviceStatusData()
        return client_status


class AidotDeviceManagerCoordinator(DataUpdateCoordinator[None]):
    """Class to manage fetching device list from AiDot cloud and provisioning per-device coordinators."""

    config_entry: AidotConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: AidotConfigEntry,
    ) -> None:
        """Initialize the device-manager coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=config_entry,
            name=DOMAIN,
            update_interval=UPDATE_DEVICE_LIST_INTERVAL,
        )
        self.client = AidotClient(
            session=async_get_clientsession(hass),
            token=config_entry.data[CONF_LOGIN_INFO],
        )
        self.client.set_token_fresh_cb(self.token_fresh_cb)
        # { dev_id: AidotDeviceUpdateCoordinator }
        self.device_coordinators: dict[str, AidotDeviceUpdateCoordinator] = {}

    async def _async_setup(self) -> None:
        """Authenticate on startup."""
        try:
            await self.async_auto_login()
        except AidotUserOrPassIncorrect as error:
            raise ConfigEntryAuthFailed from error

    async def _async_update_data(self) -> None:
        """Fetch the device list from the cloud API and provision coordinators for new devices."""
        try:
            data = await self.client.async_get_all_device()
        except AidotAuthFailed as error:
            self.token_fresh_cb()
            raise ConfigEntryError from error

        current_devices = {
            device[CONF_ID]: device
            for device in data[CONF_DEVICE_LIST]
            if (
                device[CONF_TYPE] == "light"
                and CONF_AES_KEY in device
                and device[CONF_AES_KEY][0] is not None
            )
        }

        # Tear down coordinators for devices that are no longer in the cloud list
        removed_ids = set(self.device_coordinators) - set(current_devices)
        for dev_id in removed_ids:
            del self.device_coordinators[dev_id]
        if removed_ids:
            self._purge_deleted_device_entries()

        # Provision coordinators for newly discovered devices
        for dev_id, device in current_devices.items():
            if dev_id not in self.device_coordinators:
                device_client = self.client.get_device_client(device)
                device_coordinator = AidotDeviceUpdateCoordinator(
                    self.hass, self.config_entry, device_client
                )
                self._seed_initial_cloud_state(device_coordinator, device)
                await device_coordinator.async_config_entry_first_refresh()
                self.device_coordinators[dev_id] = device_coordinator
                _LOGGER.debug(
                    "AiDot LAN: new device coordinator registered dev_id=%s total=%d",
                    dev_id,
                    len(self.device_coordinators),
                )

    # -------------------------------------------------------------------------
    # Cloud-state seeding
    #
    # AiDot's official integration relies entirely on P2P push for state.  When
    # P2P is blocked (e.g. VLAN isolation) the entity stays "unavailable"
    # indefinitely.  We seed the coordinator with the last-known cloud-reported
    # state at startup so the entity becomes available immediately while P2P
    # connects in the background.
    # -------------------------------------------------------------------------
    def _seed_initial_cloud_state(
        self,
        coordinator: AidotDeviceUpdateCoordinator,
        device: dict,
    ) -> None:
        """Seed coordinator with cloud properties to avoid unavailable on startup."""
        props: dict = device.get("properties", {}) or {}

        # online flag
        raw_online = props.get("online", True)
        if isinstance(raw_online, str):
            online = raw_online.lower() in ("true", "1", "yes")
        else:
            online = bool(raw_online)

        # on/off — default to on so a freshly-seeded bulb isn't "off" by default
        raw_on = props.get("OnOff", 1)
        try:
            on = bool(int(raw_on) if isinstance(raw_on, str) else raw_on)
        except (ValueError, TypeError):
            on = True

        # brightness 0-100 → 0-255
        raw_dim = props.get("Dimming", "100")
        try:
            dim_pct = float(raw_dim) if raw_dim not in (None, "") else 100.0
        except (ValueError, TypeError):
            dim_pct = 100.0
        dimming = int(dim_pct * 255 / 100)

        # colour temperature
        raw_cct = props.get("CCT", "6500")
        try:
            cct = int(float(raw_cct) if raw_cct not in (None, "") else 6500)
        except (ValueError, TypeError):
            cct = 6500

        # RGBW packed int → tuple
        raw_rgbw = props.get("RGBW", "-224833024")
        try:
            rgbw_val = int(raw_rgbw) if raw_rgbw not in (None, "") else -224833024
        except (ValueError, TypeError):
            rgbw_val = -224833024
        rgbw_uint = ctypes.c_uint32(rgbw_val).value
        rgbw = (
            (rgbw_uint >> 24) & 0xFF,
            (rgbw_uint >> 16) & 0xFF,
            (rgbw_uint >> 8) & 0xFF,
            rgbw_uint & 0xFF,
        )

        status = DeviceStatusData()
        status.online = online
        status.on = on
        status.dimming = dimming
        status.cct = cct
        status.rgbw = rgbw

        _LOGGER.debug(
            "AiDot LAN: seeding dev_id=%s online=%s on=%s dimming=%s cct=%s rgbw=%s",
            device.get("id", "?"),
            online,
            on,
            dimming,
            cct,
            rgbw,
        )
        coordinator.async_set_updated_data(status)

    async def async_cleanup(self) -> None:
        """Close the AiDot client session."""
        await self.client.async_cleanup()

    def token_fresh_cb(self) -> None:
        """Handle token refresh by persisting updated login info into the config entry."""
        self.hass.config_entries.async_update_entry(
            self.config_entry,
            data={CONF_LOGIN_INFO: self.client.login_info.copy()},
        )

    async def async_auto_login(self) -> None:
        """Authenticate with AiDot cloud when no cached token is available."""
        if self.client.login_info.get(CONF_ACCESS_TOKEN) is None:
            await self.client.async_post_login()

    def _purge_deleted_device_entries(self) -> None:
        """Remove stale device registry entries for devices no longer in the cloud list."""
        device_reg = dr.async_get(self.hass)
        active_identifiers = {
            (DOMAIN, coord.device_client.info.dev_id)
            for coord in self.device_coordinators.values()
        }
        for device in dr.async_entries_for_config_entry(
            device_reg, self.config_entry.entry_id
        ):
            if not set(device.identifiers) & active_identifiers:
                _LOGGER.debug("Removing stale device entry %s", device.name)
                device_reg.async_update_device(
                    device.id, remove_config_entry_id=self.config_entry.entry_id
                )
