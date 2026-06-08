"""Binary sensor platform for Cardinal CLiC: per-channel fault + lockout."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import ClicConfigEntry, ClicCoordinator
from .entity import ClicChannelEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ClicConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up CLiC binary sensors."""
    coordinator = entry.runtime_data
    entities: list[BinarySensorEntity] = []
    for channel in sorted(coordinator.data.channels):
        entities.append(ClicFaultSensor(coordinator, channel))
        entities.append(ClicLockoutSensor(coordinator, channel))
    async_add_entities(entities)


class ClicFaultSensor(ClicChannelEntity, BinarySensorEntity):
    """Per-channel fault: actual glass state disagrees with the requested state.

    Mirrors the HC-108 manual's error semantics (GLASS OUT STATUS != CHANGE
    OUTPUT), which the manual notes "can also indicate an error" -- typically an
    external wiring error / missing panel on that channel.

    PROBLEM device class: on = problem present, off = no problem.
    """

    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_translation_key = "fault"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: ClicCoordinator, channel: int) -> None:
        """Initialize."""
        super().__init__(coordinator, channel)
        self._attr_unique_id = f"{self._hub_id}_ch{channel}_fault"

    @property
    def is_on(self) -> bool | None:
        """Return True (problem) when actual output does not match requested."""
        ch = self.coordinator.data.channels.get(self._channel)
        if ch is None:
            return None
        return ch.fault


class ClicLockoutSensor(ClicChannelEntity, BinarySensorEntity):
    """Per-channel Local Lockout input state (read-only).

    LOCK is a field-wired dry-contact INPUT on the HC-108 that disables
    switching the channel to Clear when closed. The documented API model
    reports it but does not expose a way to set it, so it is read-only here.

    LOCK device class semantics (HA): on = locked, off = unlocked.
    The HC-108 LOCKOUT STATUS: 1 = lockout active (locked), 0 = inactive.
    Therefore: is_on = ch.lockout (lockout active -> on -> locked).

    (If a future firmware/API allows commanding lockout, promote this to a
    guarded switch — but keep the semantics: on = locked.)
    """

    _attr_device_class = BinarySensorDeviceClass.LOCK
    _attr_translation_key = "lockout"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: ClicCoordinator, channel: int) -> None:
        """Initialize."""
        super().__init__(coordinator, channel)
        self._attr_unique_id = f"{self._hub_id}_ch{channel}_lockout"

    @property
    def is_on(self) -> bool | None:
        """Return True (locked) when the Local Lockout input is active.

        HC-108 LOCKOUT STATUS 1 -> lockout active -> glass cannot go Clear.
        LOCK device class: on = locked. So is_on = ch.lockout.
        """
        ch = self.coordinator.data.channels.get(self._channel)
        if ch is None:
            return None
        return ch.lockout
