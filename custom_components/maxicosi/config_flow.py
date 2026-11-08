"""Config flow for the Maxi-Cosi integration."""

from __future__ import annotations

from typing import Any

import tinytuya
import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult

from .const import (
    CONF_DEVICE_ID,
    CONF_HOST,
    CONF_LOCAL_KEY,
    CONF_PROTOCOL_VERSION,
    DEFAULT_PROTOCOL_VERSION,
    DOMAIN,
    PROTOCOL_VERSIONS,
)

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_DEVICE_ID): str,
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_LOCAL_KEY): str,
        vol.Required(
            CONF_PROTOCOL_VERSION, default=DEFAULT_PROTOCOL_VERSION
        ): vol.In(PROTOCOL_VERSIONS),
    }
)


def _test_connection(data: dict[str, Any]) -> dict | None:
    """Blocking local poll to validate the credentials. Returns status dict."""
    device = tinytuya.Device(
        data[CONF_DEVICE_ID],
        data[CONF_HOST],
        data[CONF_LOCAL_KEY],
        version=float(data[CONF_PROTOCOL_VERSION]),
    )
    device.set_socketTimeout(5)
    status = device.status()
    if isinstance(status, dict) and "dps" in status:
        return status
    return None


class MaxiCosiConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Maxi-Cosi."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            await self.async_set_unique_id(user_input[CONF_DEVICE_ID])
            self._abort_if_unique_id_configured()
            try:
                status = await self.hass.async_add_executor_job(
                    _test_connection, user_input
                )
            except Exception:  # noqa: BLE001 - tinytuya raises bare exceptions
                errors["base"] = "cannot_connect"
            else:
                if status is None:
                    errors["base"] = "cannot_connect"
                else:
                    return self.async_create_entry(
                        title="See Pro Baby Monitor", data=user_input
                    )

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_SCHEMA, errors=errors
        )
