"""Switch platform for Cardinal CLiC: per-channel Clear/Private + global override."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import ClicConfigEntry, ClicCoordinator
from .entity import ClicChannelEntity, ClicHubEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ClicConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up CLiC switches."""
    coordinator = entry.runtime_data
    entities: list[SwitchEntity] = [ClicGlobalOverrideSwitch(coordinator)]
    entities.extend(
        ClicGlassSwitch(coordinator, channel)
        for channel in sorted(coordinator.data.channels)
    )
    async_add_entities(entities)


class ClicGlassSwitch(ClicChannelEntity, SwitchEntity):
    """A single glass channel. ON = Clear, OFF = Private (real API state)."""

    _attr_translation_key = "glass"
    _attr_name = None  # device name carries the channel identity

    def __init__(self, coordinator: ClicCoordinator, channel: int) -> None:
        """Initialize."""
        super().__init__(coordinator, channel)
        self._attr_unique_id = f"{self._hub_id}_ch{channel}_glass"

    @property
    def is_on(self) -> bool | None:
        """Return True when the glass is actually Clear (GLASS OUT STATUS)."""
        channel = self.coordinator.data.channels.get(self._channel)
        if channel is None:
            return None
        return channel.clear

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Make the glass Clear."""
        await self.coordinator.client.async_set_channel(self._channel, True)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Make the glass Private."""
        await self.coordinator.client.async_set_channel(self._channel, False)
        await self.coordinator.async_request_refresh()


class ClicGlobalOverrideSwitch(ClicHubEntity, SwitchEntity):
    """Global Override. ON forces all panels to the controller's configured
    target (default Private) and blocks individual triggers."""

    _attr_translation_key = "global_override"
    _attr_name = "All glass private"

    def __init__(self, coordinator: ClicCoordinator) -> None:
        """Initialize."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{self._hub_id}_global_override"

    @property
    def is_on(self) -> bool:
        """Return True when global override is active."""
        return self.coordinator.data.global_override

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Activate global override (all glass -> target, default Private)."""
        await self.coordinator.client.async_set_global_override(True)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Release global override."""
        await self.coordinator.client.async_set_global_override(False)
        await self.coordinator.async_request_refresh()
