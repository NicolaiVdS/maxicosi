"""Local polling coordinator for the Maxi-Cosi monitor (Tuya LAN protocol)."""

from __future__ import annotations

import logging
from datetime import timedelta

import tinytuya

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_DEVICE_ID,
    CONF_HOST,
    CONF_LOCAL_KEY,
    CONF_PROTOCOL_VERSION,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

type MaxiCosiConfigEntry = ConfigEntry[MaxiCosiCoordinator]


class MaxiCosiCoordinator(DataUpdateCoordinator[dict[str, object]]):
    """Poll the monitor over the local network and expose its datapoints."""

    def __init__(self, hass: HomeAssistant, entry: MaxiCosiConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
        )
        self._entry = entry
        self._device: tinytuya.Device | None = None

    def _build_device(self) -> tinytuya.Device:
        data = self._entry.data
        dev = tinytuya.Device(
            data[CONF_DEVICE_ID],
            data[CONF_HOST],
            data[CONF_LOCAL_KEY],
            version=float(data[CONF_PROTOCOL_VERSION]),
        )
        dev.set_socketPersistent(True)
        dev.set_socketTimeout(5)
        return dev

    def _poll(self) -> dict[str, object]:
        """Blocking poll; runs in an executor thread."""
        if self._device is None:
            self._device = self._build_device()
        status = self._device.status()
        if not isinstance(status, dict) or "dps" not in status:
            # Drop the socket so the next cycle reconnects cleanly.
            self._device = None
            raise UpdateFailed(f"Unexpected response from device: {status}")
        return status["dps"]

    async def _async_update_data(self) -> dict[str, object]:
        try:
            return await self.hass.async_add_executor_job(self._poll)
        except UpdateFailed:
            raise
        except Exception as err:  # tinytuya raises bare exceptions
            self._device = None
            raise UpdateFailed(f"Error polling Maxi-Cosi monitor: {err}") from err
