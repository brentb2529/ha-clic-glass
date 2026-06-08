"""A fake HC-108 'Fog Layer' REST server.

Reproduces the endpoints the integration's ClicClient calls, backed by an
in-memory channel state store, so the integration can be developed and tested
without real hardware. The state machine follows the HC-108 manual:

  - Each channel has a requested state (CHANGE OUTPUT) and an actual state
    (GLASS OUT STATUS). Normally they match. A channel can be put into a
    'wiring fault' where actual != requested (e.g. missing panel) to exercise
    the fault binary_sensor.
  - LOCKOUT (Local Lockout input) when active prevents a channel going Clear:
    commanding clear leaves it Private (actual stays private), which the manual
    describes as the lockout disabling the clear transition.
  - GLOBAL OVERRIDE when active forces every channel actual state to the
    configured target (default Private) and reports global_status per channel.

The route strings here intentionally mirror the ASSUMED constants in
custom_components/clic/api.py. If/when the real 'API Routes Specifications'
page is read off a physical HC-108, update both in lockstep.

Run standalone:  python -m fake.server  (serves on 127.0.0.1:8108)
"""

from __future__ import annotations

from dataclasses import dataclass, field

from aiohttp import web


@dataclass
class FakeChannel:
    """In-memory state for one glass output channel."""

    channel: int
    requested_clear: bool = False  # CHANGE OUTPUT (default private)
    lockout: bool = False  # LOCKOUT STATUS input
    wiring_fault: bool = False  # forces actual != requested

    def actual_clear(self, global_override: bool, override_clear: bool) -> bool:
        """Compute GLASS OUT STATUS from the inputs."""
        if global_override:
            return override_clear
        if self.lockout:
            # Lockout disables switching to clear: actual can never be clear.
            return False
        if self.wiring_fault:
            # Panel does not follow the command (e.g. missing/short).
            return not self.requested_clear
        return self.requested_clear


@dataclass
class FakeState:
    """The whole fake controller."""

    mac: str = "F8:DC:00:00:00:01"
    firmware: str = "0.1.11"
    channels: dict[int, FakeChannel] = field(default_factory=dict)
    global_override: bool = False
    # Global Override Target (Settings page); default Private per the manual.
    override_clear: bool = False

    @classmethod
    def with_channels(cls, count: int = 8) -> "FakeState":
        state = cls()
        for ch in range(1, count + 1):
            state.channels[ch] = FakeChannel(channel=ch)
        return state


def build_app(state: FakeState | None = None) -> web.Application:
    """Build the aiohttp app exposing the fake Fog Layer API."""
    state = state or FakeState.with_channels(8)
    app = web.Application()
    app["state"] = state

    async def info(request: web.Request) -> web.Response:
        s: FakeState = request.app["state"]
        return web.json_response(
            {
                "mac": s.mac,
                "firmware": s.firmware,
                "channel_count": len(s.channels),
            }
        )

    async def status(request: web.Request) -> web.Response:
        s: FakeState = request.app["state"]
        channels = []
        for ch in sorted(s.channels):
            c = s.channels[ch]
            actual = c.actual_clear(s.global_override, s.override_clear)
            channels.append(
                {
                    "channel": ch,
                    "glass_out_status": int(actual),
                    "change_output": int(c.requested_clear),
                    "lockout_status": int(c.lockout),
                    "trigger_status": int(c.requested_clear),
                    "global_status": int(s.global_override),
                }
            )
        return web.json_response(
            {"channels": channels, "global_override": s.global_override}
        )

    async def set_channel(request: web.Request) -> web.Response:
        s: FakeState = request.app["state"]
        ch = int(request.match_info["channel"])
        if ch not in s.channels:
            return web.json_response({"error": "no such channel"}, status=404)
        body = await request.json()
        s.channels[ch].requested_clear = bool(body["clear"])
        return web.json_response({"ok": True})

    async def set_global_override(request: web.Request) -> web.Response:
        s: FakeState = request.app["state"]
        body = await request.json()
        s.global_override = bool(body["active"])
        return web.json_response({"ok": True})

    app.router.add_get("/api/v1/info", info)
    app.router.add_get("/api/v1/status", status)
    app.router.add_post("/api/v1/channel/{channel}/output", set_channel)
    app.router.add_post("/api/v1/global_override", set_global_override)
    return app


def main() -> None:
    """Run the fake server standalone for manual poking."""
    web.run_app(build_app(), host="127.0.0.1", port=8108)


if __name__ == "__main__":
    main()
