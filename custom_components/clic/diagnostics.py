"""Diagnostics support for Cardinal CLiC Privacy Glass.

Redacts host and all auth fields (token, username, password) from the
config-entry dump so users can share diagnostics publicly without exposing
network addresses or credentials.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import (
    CONF_HOST,
    CONF_PASSWORD,
    CONF_USERNAME,
)
from homeassistant.core import HomeAssistant

from .const import CONF_TOKEN
from .coordinator import ClicConfigEntry

# Redact network address and all auth fields.
TO_REDACT: set[str] = {CONF_HOST, CONF_TOKEN, CONF_PASSWORD, CONF_USERNAME}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: ClicConfigEntry,
) -> dict[str, Any]:
    """Return diagnostics for a CLiC config entry."""
    coordinator = entry.runtime_data
    data = coordinator.data

    channels_summary: dict[int, dict[str, Any]] = {}
    if data is not None:
        for ch_num, ch in data.channels.items():
            channels_summary[ch_num] = {
                "channel": ch.channel,
                "clear": ch.clear,
                "requested_clear": ch.requested_clear,
                "lockout": ch.lockout,
                "trigger": ch.trigger,
                "fault": ch.fault,
            }

    return {
        "entry": async_redact_data(dict(entry.data), TO_REDACT),
        "options": dict(entry.options),
        "last_update_success": coordinator.last_update_success,
        "channels": channels_summary,
        "global_override": data.global_override if data is not None else None,
    }
