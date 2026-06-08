"""Constants for the Cardinal CLiC integration."""

from __future__ import annotations

from datetime import timedelta

DOMAIN = "clic"

CONF_TOKEN = "token"
CONF_CHANNELS = "channels"

# Polling interval for the HC-108 status snapshot. Local HTTP on the LAN; the
# manual's webpage itself refreshes on the order of seconds. Not user-tunable.
SCAN_INTERVAL = timedelta(seconds=15)

MANUFACTURER = "Cardinal IG Company"
MODEL_HC108 = "HC-108"
