"""Config flow for the Cardinal CLiC integration."""

from __future__ import annotations

import ipaddress
import re
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

# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

# Matches strings that look like dotted-decimal IPs (to route them through
# ipaddress validation rather than the hostname regex).
_IP_LIKE_RE = re.compile(r"^\d+(\.\d+){1,3}$")

# Matches plain hostnames and FQDNs.  Strings that look like dotted IPs are
# NOT tested against this regex — they are handled by ipaddress above.
_HOSTNAME_RE = re.compile(
    r"^[a-zA-Z0-9]([a-zA-Z0-9\-\.]*[a-zA-Z0-9])?$"
)


def _is_valid_host(host: str) -> bool:
    """Return True if *host* looks like a valid hostname or IP address.

    Uses ipaddress.ip_address() for strict IP validation (rejects out-of-range
    octets such as 999.x.x.x).  Strings that look like dotted-decimal addresses
    are rejected unless they pass ipaddress validation.  Non-IP strings are
    accepted if they match the hostname regex.
    """
    host = host.strip()
    if not host:
        return False

    # Try IP validation first.
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        pass

    # If it looks like a dotted IP but failed validation, reject it outright
    # so that 999.999.999.999 is not accepted as a hostname.
    if _IP_LIKE_RE.match(host):
        return False

    # Fall through to hostname regex.
    return bool(_HOSTNAME_RE.match(host))

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Optional(CONF_PORT, default=DEFAULT_PORT): int,
        vol.Optional(CONF_TOKEN): str,
        vol.Optional(CONF_USERNAME): str,
        vol.Optional(CONF_PASSWORD): str,
    }
)


def _build_connect_schema(
    host: str = "",
    port: int = DEFAULT_PORT,
    token: str = "",
    username: str = "",
    password: str = "",
) -> vol.Schema:
    """Build the connection schema with optional pre-populated defaults."""
    return vol.Schema(
        {
            vol.Required(CONF_HOST, default=host): str,
            vol.Optional(CONF_PORT, default=port): int,
            vol.Optional(CONF_TOKEN, default=token): str,
            vol.Optional(CONF_USERNAME, default=username): str,
            vol.Optional(CONF_PASSWORD, default=password): str,
        }
    )


async def _try_connect(
    hass: Any,
    user_input: dict[str, Any],
) -> tuple[ClicDeviceInfo | None, dict[str, str]]:
    """Attempt to connect to the HC-108.  Returns (device_info, errors)."""
    errors: dict[str, str] = {}
    session = async_get_clientsession(hass)
    client = ClicClient(
        user_input[CONF_HOST],
        session,
        port=user_input.get(CONF_PORT, DEFAULT_PORT),
        token=user_input.get(CONF_TOKEN) or None,
        username=user_input.get(CONF_USERNAME) or None,
        password=user_input.get(CONF_PASSWORD) or None,
    )
    try:
        info = await client.async_get_info()
    except ClicAuthError:
        errors["base"] = "invalid_auth"
        return None, errors
    except ClicConnectionError:
        errors["base"] = "cannot_connect"
        return None, errors
    except Exception:  # noqa: BLE001
        errors["base"] = "unknown"
        return None, errors
    return info, errors


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
            host = user_input.get(CONF_HOST, "").strip()
            if not _is_valid_host(host):
                errors[CONF_HOST] = "invalid_host"
            else:
                info, errors = await _try_connect(self.hass, user_input)
            if not errors:
                assert info is not None
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
                str(i): user_input.get(f"channel_{i}") or f"Glass {i}"
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

    async def async_step_reauth(
        self, entry_data: dict[str, Any]
    ) -> ConfigFlowResult:
        """Handle reauthentication when the HC-108 rejects credentials.

        Triggered automatically by Home Assistant when the coordinator raises
        ConfigEntryAuthFailed.  The user can update credentials; host/port are
        pre-filled and read-only in the banner context (the entry stays).
        """
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show the reauth form and validate new credentials."""
        reauth_entry = self._get_reauth_entry()
        errors: dict[str, str] = {}

        if user_input is not None:
            # Merge new credentials on top of the existing entry data so
            # host/port are preserved.
            merged = {**reauth_entry.data, **user_input}
            info, errors = await _try_connect(self.hass, merged)
            if not errors:
                self.hass.config_entries.async_update_entry(
                    reauth_entry, data=merged
                )
                await self.hass.config_entries.async_reload(reauth_entry.entry_id)
                return self.async_abort(reason="reauth_successful")

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_TOKEN): str,
                    vol.Optional(CONF_USERNAME): str,
                    vol.Optional(CONF_PASSWORD): str,
                }
            ),
            description_placeholders={
                "host": reauth_entry.data.get(CONF_HOST, ""),
            },
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Allow the user to change host/port/credentials without re-adding.

        This keeps the existing entry (entity IDs, automations, history) intact
        while updating the connection parameters.
        """
        reconfigure_entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input.get(CONF_HOST, "").strip()
            if not _is_valid_host(host):
                errors[CONF_HOST] = "invalid_host"
            else:
                info, errors = await _try_connect(self.hass, user_input)
            if not errors:
                assert info is not None
                # Verify the controller at the new address is the same physical
                # unit (same MAC). Abort with "wrong_device" if the user
                # accidentally pointed at a different controller.
                await self.async_set_unique_id(info.mac, raise_on_progress=False)
                self._abort_if_unique_id_mismatch(reason="wrong_device")
                return self.async_update_reload_and_abort(
                    reconfigure_entry,
                    data_updates={
                        CONF_HOST: user_input[CONF_HOST],
                        CONF_PORT: user_input.get(CONF_PORT, DEFAULT_PORT),
                        CONF_TOKEN: user_input.get(CONF_TOKEN) or None,
                        CONF_USERNAME: user_input.get(CONF_USERNAME) or None,
                        CONF_PASSWORD: user_input.get(CONF_PASSWORD) or None,
                    },
                )

        current = reconfigure_entry.data
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=_build_connect_schema(
                host=current.get(CONF_HOST, ""),
                port=current.get(CONF_PORT, DEFAULT_PORT),
                token=current.get(CONF_TOKEN, ""),
                username=current.get(CONF_USERNAME, ""),
                password=current.get(CONF_PASSWORD, ""),
            ),
            errors=errors,
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
                str(i): user_input.get(f"channel_{i}") or f"Glass {i}"
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
