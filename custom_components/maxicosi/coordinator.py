"""Local polling coordinator for the Maxi-Cosi monitor (Tuya LAN protocol)."""

from __future__ import annotations

import logging
import time
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
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    POLL_RETRIES,
    POLL_RETRY_DELAY,
)

_LOGGER = logging.getLogger(__name__)

type MaxiCosiConfigEntry = ConfigEntry[MaxiCosiCoordinator]


class MaxiCosiCoordinator(DataUpdateCoordinator[dict[str, object]]):
    """Poll the monitor over the local network and expose its datapoints."""

    def __init__(self, hass: HomeAssistant, entry: MaxiCosiConfigEntry) -> None:
        interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=interval),
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
        """Blocking poll with retries; runs in an executor thread.

        The monitor sometimes refuses a local socket while the app is
        streaming, so retry a few times (reconnecting each time) before giving
        up, to avoid gaps in history.
        """
        last = None
        for attempt in range(POLL_RETRIES):
            if self._device is None:
                self._device = self._build_device()
            try:
                status = self._device.status()
            except Exception as err:  # tinytuya raises bare exceptions
                last = err
                status = None
            if isinstance(status, dict) and "dps" in status:
                return status["dps"]
            last = status if status is not None else last
            # Drop the socket so the next attempt reconnects cleanly.
            self._device = None
            if attempt < POLL_RETRIES - 1:
                time.sleep(POLL_RETRY_DELAY)
        raise UpdateFailed(f"No valid response after {POLL_RETRIES} attempts: {last}")

    async def _async_update_data(self) -> dict[str, object]:
        try:
            return await self.hass.async_add_executor_job(self._poll)
        except UpdateFailed:
            raise
        except Exception as err:  # tinytuya raises bare exceptions
            self._device = None
            raise UpdateFailed(f"Error polling Maxi-Cosi monitor: {err}") from err
