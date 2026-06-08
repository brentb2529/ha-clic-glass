"""Config flow for the Cardinal CLiC integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import (
    CONF_HOST,
    CONF_PASSWORD,
    CONF_PORT,
    CONF_USERNAME,
)
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import DEFAULT_PORT, ClicAuthError, ClicClient, ClicConnectionError, ClicDeviceInfo
from .const import CONF_CHANNELS, CONF_TOKEN, DOMAIN

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Optional(CONF_PORT, default=DEFAULT_PORT): int,
        vol.Optional(CONF_TOKEN): str,
        vol.Optional(CONF_USERNAME): str,
        vol.Optional(CONF_PASSWORD): str,
    }
)


class ClicConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Cardinal CLiC.

    Step 1 (user): connect to the HC-108 by host/IP and optional credentials.
    Step 2 (channels): optionally name each detected glass zone.

    Multiple HC-108 controllers are fully supported: each creates its own
    config entry keyed by the controller MAC address.
    """

    VERSION = 1

    def __init__(self) -> None:
        """Initialize."""
        self._user_input: dict[str, Any] = {}
        self._device_info: ClicDeviceInfo | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step: connect to the HC-108 by host/IP."""
        errors: dict[str, str] = {}
        if user_input is not None:
            session = async_get_clientsession(self.hass)
            client = ClicClient(
                user_input[CONF_HOST],
                session,
                port=user_input.get(CONF_PORT, DEFAULT_PORT),
                token=user_input.get(CONF_TOKEN),
                username=user_input.get(CONF_USERNAME),
                password=user_input.get(CONF_PASSWORD),
            )
            try:
                info = await client.async_get_info()
            except ClicAuthError:
                errors["base"] = "invalid_auth"
            except ClicConnectionError:
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(info.mac)
                self._abort_if_unique_id_configured(
                    updates={
                        CONF_HOST: user_input[CONF_HOST],
                        CONF_PORT: user_input.get(CONF_PORT, DEFAULT_PORT),
                    }
                )
                self._user_input = user_input
                self._device_info = info
                return await self.async_step_channels()

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_SCHEMA,
            errors=errors,
        )

    async def async_step_channels(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Optional step: name each detected glass zone."""
        assert self._device_info is not None
        channel_count = self._device_info.channel_count

        if user_input is not None:
            # Build the CONF_CHANNELS mapping: channel_number_str -> name
            channels = {
                str(i): user_input.get(f"channel_{i}", f"Glass {i}")
                for i in range(1, channel_count + 1)
            }
            host = self._user_input[CONF_HOST]
            return self.async_create_entry(
                title=f"CLiC HC-108 ({host})",
                data=self._user_input,
                options={CONF_CHANNELS: channels},
            )

        schema_fields: dict[Any, Any] = {}
        for i in range(1, channel_count + 1):
            schema_fields[vol.Optional(f"channel_{i}", default=f"Glass {i}")] = str

        return self.async_show_form(
            step_id="channels",
            data_schema=vol.Schema(schema_fields),
            description_placeholders={"channel_count": str(channel_count)},
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Return the options flow handler."""
        return ClicOptionsFlow()


class ClicOptionsFlow(OptionsFlow):
    """Allow the user to rename glass zones after initial setup."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage options: rename channels."""
        # Determine channel count from current options or fall back to 8.
        existing_channels: dict[str, str] = (
            self.config_entry.options.get(CONF_CHANNELS) or {}
        )
        # The channel keys are always present from setup; the max key gives count.
        if existing_channels:
            channel_count = max(int(k) for k in existing_channels)
        else:
            channel_count = 8

        if user_input is not None:
            channels = {
                str(i): user_input.get(f"channel_{i}", f"Glass {i}")
                for i in range(1, channel_count + 1)
            }
            return self.async_create_entry(data={CONF_CHANNELS: channels})

        schema_fields: dict[Any, Any] = {}
        for i in range(1, channel_count + 1):
            default_name = existing_channels.get(str(i), f"Glass {i}")
            schema_fields[
                vol.Optional(f"channel_{i}", default=default_name)
            ] = str

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(schema_fields),
        )
