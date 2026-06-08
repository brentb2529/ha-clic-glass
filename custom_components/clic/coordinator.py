"""DataUpdateCoordinator for the Cardinal CLiC HC-108."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import ClicAuthError, ClicClient, ClicConnectionError, ClicData, ClicResponseError
from .const import DOMAIN, SCAN_INTERVAL

_LOGGER = logging.getLogger(__name__)

type ClicConfigEntry = ConfigEntry[ClicCoordinator]


class ClicCoordinator(DataUpdateCoordinator[ClicData]):
    """Polls the HC-108 status snapshot."""

    config_entry: ClicConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ClicConfigEntry,
        client: ClicClient,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=config_entry,
            name=DOMAIN,
            update_interval=SCAN_INTERVAL,
        )
        self.client = client

    async def _async_update_data(self) -> ClicData:
        """Fetch one status snapshot from the controller."""
        try:
            return await self.client.async_get_data()
        except ClicAuthError as err:
            # ConfigEntryAuthFailed triggers a reauthentication flow so the
            # user can correct their credentials without removing the entry.
            raise ConfigEntryAuthFailed(
                f"HC-108 at {self.client.host} rejected credentials"
            ) from err
        except ClicResponseError as err:
            raise UpdateFailed(
                f"HC-108 at {self.client.host} returned unexpected data: {err}"
            ) from err
        except ClicConnectionError as err:
            raise UpdateFailed(
                f"Error communicating with HC-108 at {self.client.host}: {err}"
            ) from err
