"""Shared entity base classes for Cardinal CLiC."""

from __future__ import annotations

from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_CHANNELS, DOMAIN, MANUFACTURER, MODEL_HC108
from .coordinator import ClicCoordinator


class ClicHubEntity(CoordinatorEntity[ClicCoordinator]):
    """Base for entities that belong to the controller itself (e.g. global override)."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: ClicCoordinator) -> None:
        """Initialize."""
        super().__init__(coordinator)
        self._hub_id = (
            coordinator.config_entry.unique_id or coordinator.config_entry.entry_id
        )

    @property
    def device_info(self) -> DeviceInfo:
        """Hub device for the HC-108 controller.

        The configuration_url is set to the controller's HTTP address so the
        device registry "Visit" button opens the HC-108 web UI directly.
        """
        entry = self.coordinator.config_entry
        host = entry.data.get(CONF_HOST, "")
        port = entry.data.get(CONF_PORT, 80)
        port_suffix = f":{port}" if port != 80 else ""

        return DeviceInfo(
            identifiers={(DOMAIN, self._hub_id)},
            manufacturer=MANUFACTURER,
            model=MODEL_HC108,
            name="CLiC HC-108",
            configuration_url=f"http://{host}{port_suffix}",
        )


class ClicChannelEntity(CoordinatorEntity[ClicCoordinator]):
    """Base for per-channel (per glass zone) entities.

    Each channel is modelled as its own device, grouped under the HC-108 hub
    via ``via_device``. This makes each glass zone a tidy unit in HA while
    still showing the controller as the parent hub.

    Zone names are sourced from the config entry options (CONF_CHANNELS dict
    mapping channel number str → friendly name). If no name is configured for
    a channel, a default "Glass {n}" is used.
    """

    _attr_has_entity_name = True

    def __init__(self, coordinator: ClicCoordinator, channel: int) -> None:
        """Initialize."""
        super().__init__(coordinator)
        self._channel = channel
        self._hub_id = (
            coordinator.config_entry.unique_id or coordinator.config_entry.entry_id
        )

    def _zone_name(self) -> str:
        """Friendly zone name from options, or fallback."""
        channels: dict[str, str] = (
            self.coordinator.config_entry.options.get(CONF_CHANNELS) or {}
        )
        return channels.get(str(self._channel)) or f"Glass {self._channel}"

    @property
    def device_info(self) -> DeviceInfo:
        """One device per glass channel/zone."""
        return DeviceInfo(
            identifiers={(DOMAIN, f"{self._hub_id}_ch{self._channel}")},
            manufacturer=MANUFACTURER,
            model=f"{MODEL_HC108} Channel",
            name=self._zone_name(),
            via_device=(DOMAIN, self._hub_id),
        )

    @property
    def available(self) -> bool:
        """Available only when the last poll succeeded and the channel exists."""
        return (
            super().available
            and self.coordinator.data is not None
            and self._channel in self.coordinator.data.channels
        )
