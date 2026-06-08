"""Config flow for the Cardinal CLiC integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import (
    CONF_HOST,
    CONF_PASSWORD,
    CONF_PORT,
    CONF_USERNAME,
)
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import DEFAULT_PORT, ClicAuthError, ClicClient, ClicConnectionError
from .const import CONF_TOKEN, DOMAIN

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
    """Handle a config flow for Cardinal CLiC."""

    VERSION = 1

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
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=f"CLiC HC-108 ({user_input[CONF_HOST]})",
                    data=user_input,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_SCHEMA,
            errors=errors,
        )
