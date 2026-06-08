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
from typing import Any

import aiohttp

_LOGGER = logging.getLogger(__name__)

DEFAULT_PORT = 80
DEFAULT_TIMEOUT = 10

# --- ASSUMED endpoint paths (adjust here once the live spec is read) ---------
# The fake server in clic-glass/fake/ implements exactly these paths so tests
# exercise the same surface. Keep the fake and these constants in lockstep.
#
# If async_discover_routes() successfully reads the live "API Routes
# Specifications" page off the device, a ClicClient subclass could patch
# these at runtime. For now they are module constants — one place to fix.
PATH_INFO = "/api/v1/info"  # GET device info: firmware, channel count, mac
PATH_STATUS = "/api/v1/status"  # GET full snapshot: all channels + global override
PATH_CHANNEL_SET = "/api/v1/channel/{channel}/output"  # POST {"clear": bool}
PATH_GLOBAL_OVERRIDE = "/api/v1/global_override"  # POST {"active": bool}
# Per-channel LOCK is an INPUT on the HC-108 (a dry contact wired in the
# field); it is reported in status but is not settable over the API in the
# documented model, so there is no SET path for lock. Exposed read-only.
# The "API Routes Specifications" page lives at this URL on the device:
PATH_API_SPEC = "/api/v1/routes"  # GET spec page (assumed); may be /routes or similar
# ---------------------------------------------------------------------------


class ClicError(Exception):
    """Base error for the CLiC client."""


class ClicConnectionError(ClicError):
    """Raised when the controller cannot be reached."""


class ClicAuthError(ClicError):
    """Raised when the controller rejects credentials."""


class ClicResponseError(ClicError):
    """Raised when the controller returns an unexpected/malformed response."""


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


def _truthy(value: Any, field: str) -> bool:
    """Coerce a JSON int/bool/string to bool, tolerating device quirks.

    The HC-108 manual documents these fields as 0/1 integers but we accept
    native booleans and any truthy string so the client does not break on
    minor firmware variations.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value != 0
    if isinstance(value, str):
        return value.lower() not in ("0", "false", "off", "no", "")
    _LOGGER.debug("Unexpected type for field %s: %r — treating as falsy", field, value)
    return False


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
    def host(self) -> str:
        """Controller hostname or IP."""
        return self._host

    @property
    def _base(self) -> str:
        return f"http://{self._host}:{self._port}"

    def _headers(self) -> dict[str, str]:
        if self._token:
            return {"Authorization": f"Bearer {self._token}"}
        return {}

    async def _request(
        self,
        method: str,
        path: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Execute an HTTP request and return the parsed JSON body.

        Raises:
            ClicConnectionError: network error, timeout, or non-auth HTTP error.
            ClicAuthError: HTTP 401 or 403.
            ClicResponseError: response is not JSON or is not a dict.
        """
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

        # Parse JSON — tolerate non-JSON content types from embedded web servers
        # that may send text/html on some firmware versions.
        try:
            body = await resp.json(content_type=None)
        except Exception as err:
            raise ClicResponseError(
                f"{url} returned non-JSON response: {err}"
            ) from err

        if not isinstance(body, dict):
            raise ClicResponseError(
                f"{url} returned unexpected JSON type {type(body).__name__!r}"
            )
        return body

    async def async_get_info(self) -> ClicDeviceInfo:
        """Fetch device identity (used by config flow + device registry)."""
        data = await self._request("GET", PATH_INFO)
        mac = data.get("mac")
        if not mac or not isinstance(mac, str):
            raise ClicResponseError(
                f"Missing or invalid 'mac' in info response: {data!r}"
            )
        return ClicDeviceInfo(
            mac=str(mac).upper(),
            firmware=str(data.get("firmware", "unknown")),
            channel_count=int(data.get("channel_count", 8)),
        )

    async def async_get_data(self) -> ClicData:
        """Fetch a full status snapshot."""
        data = await self._request("GET", PATH_STATUS)

        raw_channels = data.get("channels")
        if not isinstance(raw_channels, list):
            raise ClicResponseError(
                f"Missing or invalid 'channels' list in status response: {data!r}"
            )

        channels: dict[int, ClicChannel] = {}
        for raw in raw_channels:
            if not isinstance(raw, dict):
                _LOGGER.warning("Skipping malformed channel entry: %r", raw)
                continue
            ch_raw = raw.get("channel")
            if ch_raw is None:
                _LOGGER.warning("Skipping channel entry missing 'channel' key: %r", raw)
                continue
            try:
                ch = int(ch_raw)
            except (TypeError, ValueError):
                _LOGGER.warning("Skipping channel entry with non-integer channel: %r", raw)
                continue

            glass_out = raw.get("glass_out_status")
            change_out = raw.get("change_output")
            if glass_out is None or change_out is None:
                _LOGGER.warning(
                    "Channel %d missing glass_out_status or change_output — skipping", ch
                )
                continue

            channels[ch] = ClicChannel(
                channel=ch,
                clear=_truthy(glass_out, "glass_out_status"),
                requested_clear=_truthy(change_out, "change_output"),
                lockout=_truthy(raw.get("lockout_status", 0), "lockout_status"),
                trigger=_truthy(raw.get("trigger_status", 0), "trigger_status"),
                global_status=_truthy(raw.get("global_status", 0), "global_status"),
            )

        if not channels:
            raise ClicResponseError(
                "Status response contained no valid channel entries"
            )

        return ClicData(
            channels=channels,
            global_override=_truthy(
                data.get("global_override", False), "global_override"
            ),
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

    async def async_discover_routes(self) -> dict[str, Any] | None:
        """Attempt to fetch the device's own API Routes Specification page.

        This is a best-effort, non-blocking call used at setup to self-correct
        route paths if the device publishes them. Returns the parsed spec dict
        on success; returns None silently on any failure (wrong path, no page,
        non-JSON, etc.) so callers can ignore it safely.

        The spec URL is itself assumed (PATH_API_SPEC). If the real HC-108
        serves the spec at a different path, update PATH_API_SPEC.
        """
        try:
            return await self._request("GET", PATH_API_SPEC)
        except (ClicError, Exception) as err:  # noqa: BLE001
            _LOGGER.debug(
                "Route discovery at %s failed (non-fatal): %s", PATH_API_SPEC, err
            )
            return None
