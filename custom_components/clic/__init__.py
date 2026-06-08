"""The Cardinal CLiC Privacy Glass integration."""

from __future__ import annotations

from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import ClicClient
from .const import CONF_TOKEN
from .coordinator import ClicConfigEntry, ClicCoordinator

PLATFORMS = ["switch", "binary_sensor"]


async def async_setup_entry(hass: HomeAssistant, entry: ClicConfigEntry) -> bool:
    """Set up Cardinal CLiC from a config entry."""
    session = async_get_clientsession(hass)
    client = ClicClient(
        entry.data[CONF_HOST],
        session,
        port=entry.data.get(CONF_PORT, 80),
        token=entry.data.get(CONF_TOKEN),
        username=entry.data.get(CONF_USERNAME),
        password=entry.data.get(CONF_PASSWORD),
    )

    coordinator = ClicCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ClicConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
