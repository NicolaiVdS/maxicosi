"""Config flow for the Maxi-Cosi integration."""

from __future__ import annotations

from typing import Any

import tinytuya
import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_DEVICE_ID,
    CONF_HOST,
    CONF_LOCAL_KEY,
    CONF_PROTOCOL_VERSION,
    CONF_SCAN_INTERVAL,
    DEFAULT_PROTOCOL_VERSION,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
    PROTOCOL_VERSIONS,
)
from .tuya_cloud import TuyaCloud, TuyaCloudError

STEP_MANUAL_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_DEVICE_ID): str,
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_LOCAL_KEY): str,
        vol.Required(CONF_PROTOCOL_VERSION, default=DEFAULT_PROTOCOL_VERSION): vol.In(
            PROTOCOL_VERSIONS
        ),
    }
)


def _test_connection(data: dict[str, Any]) -> dict | None:
    """Blocking local poll to validate credentials. Returns status dict or None."""
    device = tinytuya.Device(
        data[CONF_DEVICE_ID],
        data[CONF_HOST],
        data[CONF_LOCAL_KEY],
        version=float(data[CONF_PROTOCOL_VERSION]),
    )
    device.set_socketTimeout(5)
    status = device.status()
    return status if isinstance(status, dict) and "dps" in status else None


def _scan_for_ip(dev_id: str) -> str | None:
    """Blocking LAN scan to find the device's local IP by its Tuya id."""
    try:
        found = tinytuya.deviceScan(False, 6)
    except Exception:  # noqa: BLE001
        return None
    for ip, info in (found or {}).items():
        if info.get("gwId") == dev_id or info.get("id") == dev_id:
            return ip
    return None


class MaxiCosiConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Maxi-Cosi."""

    VERSION = 1

    def __init__(self) -> None:
        self._cloud: TuyaCloud | None = None
        self._email = ""
        self._password = ""
        self._devices: list[dict] = []
        self._picked: dict = {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return self.async_show_menu(step_id="user", menu_options=["cloud", "manual"])

    # -- Manual entry ----------------------------------------------------------
    async def async_step_manual(
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
            except Exception:  # noqa: BLE001
                errors["base"] = "cannot_connect"
            else:
                if status is None:
                    errors["base"] = "cannot_connect"
                else:
                    return self.async_create_entry(
                        title="See Pro Baby Monitor", data=user_input
                    )
        return self.async_show_form(
            step_id="manual", data_schema=STEP_MANUAL_SCHEMA, errors=errors
        )

    # -- Cloud login -----------------------------------------------------------
    async def async_step_cloud(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            self._email = user_input["email"]
            self._password = user_input["password"]
            self._cloud = TuyaCloud(
                async_get_clientsession(self.hass),
                country_code=user_input.get("country_code", "32"),
            )
            try:
                await self._cloud.login(self._email, self._password)
            except TuyaCloudError as err:
                if "MFA" in err.code.upper():
                    try:
                        await self._cloud.send_mfa(self._email, self._password)
                    except TuyaCloudError:
                        pass
                    return await self.async_step_mfa()
                errors["base"] = "invalid_auth"
            except Exception:  # noqa: BLE001
                errors["base"] = "cannot_connect"
            else:
                return await self.async_step_select()

        schema = vol.Schema(
            {
                vol.Required("email"): str,
                vol.Required("password"): str,
                vol.Required("country_code", default="32"): str,
            }
        )
        return self.async_show_form(step_id="cloud", data_schema=schema, errors=errors)

    async def async_step_mfa(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None and self._cloud is not None:
            try:
                await self._cloud.login(
                    self._email, self._password, user_input["code"]
                )
            except TuyaCloudError:
                errors["base"] = "invalid_auth"
            except Exception:  # noqa: BLE001
                errors["base"] = "cannot_connect"
            else:
                return await self.async_step_select()
        return self.async_show_form(
            step_id="mfa",
            data_schema=vol.Schema({vol.Required("code"): str}),
            errors=errors,
        )

    async def async_step_select(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Pick a discovered device, then resolve its IP."""
        assert self._cloud is not None
        if not self._devices:
            try:
                self._devices = [
                    d for d in await self._cloud.list_devices() if d.get("localKey")
                ]
            except Exception:  # noqa: BLE001
                return self.async_abort(reason="cannot_connect")
            if not self._devices:
                return self.async_abort(reason="no_devices")

        if user_input is not None:
            dev = next(
                d
                for d in self._devices
                if (d.get("devId") or d.get("deviceId")) == user_input["device"]
            )
            self._picked = dev
            return await self.async_step_confirm()

        choices = {
            (d.get("devId") or d.get("deviceId")): (
                d.get("name") or d.get("deviceName") or d.get("devId")
            )
            for d in self._devices
        }
        return self.async_show_form(
            step_id="select",
            data_schema=vol.Schema({vol.Required("device"): vol.In(choices)}),
        )

    async def async_step_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Resolve/confirm the local IP and create the entry."""
        dev = self._picked
        dev_id = dev.get("devId") or dev.get("deviceId")
        await self.async_set_unique_id(dev_id)
        self._abort_if_unique_id_configured()
        errors: dict[str, str] = {}

        suggested_ip = dev.get("ip") or ""
        if user_input is None:
            scanned = await self.hass.async_add_executor_job(_scan_for_ip, dev_id)
            suggested_ip = scanned or suggested_ip
        else:
            data = {
                CONF_DEVICE_ID: dev_id,
                CONF_HOST: user_input[CONF_HOST],
                CONF_LOCAL_KEY: dev["localKey"],
                CONF_PROTOCOL_VERSION: user_input[CONF_PROTOCOL_VERSION],
            }
            try:
                status = await self.hass.async_add_executor_job(_test_connection, data)
            except Exception:  # noqa: BLE001
                errors["base"] = "cannot_connect"
            else:
                if status is None:
                    errors["base"] = "cannot_connect"
                else:
                    return self.async_create_entry(
                        title=dev.get("name") or "See Pro Baby Monitor", data=data
                    )
            suggested_ip = user_input[CONF_HOST]

        schema = vol.Schema(
            {
                vol.Required(CONF_HOST, default=suggested_ip): str,
                vol.Required(
                    CONF_PROTOCOL_VERSION, default=DEFAULT_PROTOCOL_VERSION
                ): vol.In(PROTOCOL_VERSIONS),
            }
        )
        return self.async_show_form(
            step_id="confirm",
            data_schema=schema,
            errors=errors,
            description_placeholders={"name": dev.get("name") or dev_id},
        )

    # -- Options ---------------------------------------------------------------
    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return MaxiCosiOptionsFlow()


class MaxiCosiOptionsFlow(OptionsFlow):
    """Handle options (polling interval)."""

    async def async_step_init(self, user_input=None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        current = self.config_entry.options.get(
            CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
        )
        schema = vol.Schema(
            {
                vol.Required(CONF_SCAN_INTERVAL, default=current): vol.All(
                    vol.Coerce(int),
                    vol.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL),
                )
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
