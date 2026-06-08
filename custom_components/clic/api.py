"""Async client for the Cardinal CLiC HC-108 "Fog Layer" REST API.

IMPORTANT — API CONFIDENCE
==========================
The HC-108 *data model* is CONFIRMED from the HC-108 Network Controller
Installation Manual (Rev. A, "Internal Webpage" -> "Hardware" page):

  Per channel ("Glass Out 1".."Glass Out 8"):
    - GLOBAL STATUS   : Global Override active (0/1)
    - LOCKOUT STATUS  : Local Lockout input active (0/1)
    - TRIGGER STATUS  : Trigger input active (0/1)
    - CHANGE OUTPUT   : requested state (Off=private / On=clear) -- also the
                        control toggle on the webpage
    - GLASS OUT STATUS: ACTUAL output (0=private / 1=clear). If it does not
                        match CHANGE OUTPUT, the channel is in an error/fault
                        state (manual: "can also indicate an error").
  Plus a "Global Override Target" (default Private) on the Settings page.

The HC-108 also serves, from its own webpage ("Links" page), an interactive
"API Routes Specifications" page (the "Fog Layer API") and a "Python API SDK"
(a plaintext Python 3 script). Those are served *from the device at runtime*
and are NOT published publicly (no PyPI package, no public GitHub repo found
as of 2026-06). Therefore the exact HTTP route strings below are ASSUMED and
modelled on the data fields the manual documents. They are deliberately
isolated as module-level constants so they can be corrected in one place once
we can read the live "API Routes Specifications" page on a real HC-108.

Confirmed:  base is HTTP on the controller's LAN IP; webpage login admin/admin.
Assumed:    REST paths, JSON field names, auth scheme for the API (we support
            none / token / basic and default to none).

This client is intentionally a thin wrapper. Once the real spec is known it
should be promoted to a standalone PyPI library; for now it lives here so the
integration is usable and testable against the bundled fake server.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import logging

import aiohttp

_LOGGER = logging.getLogger(__name__)

DEFAULT_PORT = 80
DEFAULT_TIMEOUT = 10

# --- ASSUMED endpoint paths (adjust here once the live spec is read) --------
# The fake server in clic-glass/fake/ implements exactly these paths so tests
# exercise the same surface. Keep the fake and these constants in lockstep.
PATH_INFO = "/api/v1/info"  # device info: firmware, channel count, mac
PATH_STATUS = "/api/v1/status"  # full snapshot: all channels + global override
PATH_CHANNEL_SET = "/api/v1/channel/{channel}/output"  # POST {"clear": bool}
PATH_GLOBAL_OVERRIDE = "/api/v1/global_override"  # POST {"active": bool}
# Per-channel LOCK is an INPUT on the HC-108 (a dry contact wired in the
# field); it is reported in status but is not settable over the API in the
# documented model, so there is no SET path for lock. We expose it read-only.
# ---------------------------------------------------------------------------


class ClicError(Exception):
    """Base error for the CLiC client."""


class ClicConnectionError(ClicError):
    """Raised when the controller cannot be reached."""


class ClicAuthError(ClicError):
    """Raised when the controller rejects credentials."""


@dataclass(slots=True)
class ClicChannel:
    """State of a single HC-108 glass output channel.

    ``clear`` is the ACTUAL glass state (GLASS OUT STATUS). ``requested_clear``
    is what was last commanded (CHANGE OUTPUT). When they disagree the channel
    is faulted (mirrors the manual's error semantics / external wiring error).
    """

    channel: int
    clear: bool
    requested_clear: bool
    lockout: bool
    trigger: bool
    global_status: bool

    @property
    def fault(self) -> bool:
        """True when actual output does not match the requested output."""
        return self.clear != self.requested_clear


@dataclass(slots=True)
class ClicDeviceInfo:
    """Static-ish device identity."""

    mac: str
    firmware: str
    channel_count: int


@dataclass(slots=True)
class ClicData:
    """A full poll snapshot of the controller."""

    channels: dict[int, ClicChannel]
    global_override: bool


class ClicClient:
    """Thin async HTTP client for one HC-108 controller."""

    def __init__(
        self,
        host: str,
        session: aiohttp.ClientSession,
        *,
        port: int = DEFAULT_PORT,
        token: str | None = None,
        username: str | None = None,
        password: str | None = None,
        timeout: int = DEFAULT_TIMEOUT,
    ) -> None:
        """Initialize the client."""
        self._host = host
        self._port = port
        self._session = session
        self._token = token
        self._timeout = timeout
        self._auth: aiohttp.BasicAuth | None = None
        if username is not None and password is not None:
            self._auth = aiohttp.BasicAuth(username, password)

    @property
    def _base(self) -> str:
        return f"http://{self._host}:{self._port}"

    def _headers(self) -> dict[str, str]:
        if self._token:
            return {"Authorization": f"Bearer {self._token}"}
        return {}

    async def _request(self, method: str, path: str, **kwargs) -> dict:
        url = f"{self._base}{path}"
        try:
            async with asyncio.timeout(self._timeout):
                resp = await self._session.request(
                    method,
                    url,
                    headers=self._headers(),
                    auth=self._auth,
                    **kwargs,
                )
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            raise ClicConnectionError(f"Error reaching {url}: {err}") from err

        if resp.status in (401, 403):
            raise ClicAuthError(f"Authentication rejected by {url}")
        if resp.status >= 400:
            raise ClicConnectionError(f"{url} returned HTTP {resp.status}")

        if resp.content_type == "application/json":
            return await resp.json()
        return {}

    async def async_get_info(self) -> ClicDeviceInfo:
        """Fetch device identity (used by config flow + device registry)."""
        data = await self._request("GET", PATH_INFO)
        return ClicDeviceInfo(
            mac=str(data["mac"]),
            firmware=str(data.get("firmware", "unknown")),
            channel_count=int(data.get("channel_count", 8)),
        )

    async def async_get_data(self) -> ClicData:
        """Fetch a full status snapshot."""
        data = await self._request("GET", PATH_STATUS)
        channels: dict[int, ClicChannel] = {}
        for raw in data["channels"]:
            ch = int(raw["channel"])
            channels[ch] = ClicChannel(
                channel=ch,
                clear=bool(raw["glass_out_status"]),
                requested_clear=bool(raw["change_output"]),
                lockout=bool(raw.get("lockout_status", False)),
                trigger=bool(raw.get("trigger_status", False)),
                global_status=bool(raw.get("global_status", False)),
            )
        return ClicData(
            channels=channels,
            global_override=bool(data["global_override"]),
        )

    async def async_set_channel(self, channel: int, clear: bool) -> None:
        """Command a channel Clear (True) or Private (False)."""
        await self._request(
            "POST",
            PATH_CHANNEL_SET.format(channel=channel),
            json={"clear": clear},
        )

    async def async_set_global_override(self, active: bool) -> None:
        """Activate/deactivate the Global Override (forces all to target)."""
        await self._request(
            "POST",
            PATH_GLOBAL_OVERRIDE,
            json={"active": active},
        )
