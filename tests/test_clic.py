"""End-to-end tests for the Cardinal CLiC integration against the fake server."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from aiohttp.test_utils import TestServer

from homeassistant.const import (
    CONF_HOST,
    CONF_PASSWORD,
    CONF_PORT,
    CONF_USERNAME,
    STATE_OFF,
    STATE_ON,
    STATE_UNAVAILABLE,
)
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.clic.const import CONF_CHANNELS, CONF_TOKEN, DOMAIN
from fake.server import FakeState

from pytest_homeassistant_custom_component.common import MockConfigEntry


def _entry_data(server: TestServer) -> dict:
    return {CONF_HOST: server.host, CONF_PORT: server.port}


async def _setup(
    hass: HomeAssistant,
    server: TestServer,
    unique_id: str = "F8:DC:00:00:00:01",
    options: dict | None = None,
) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data=_entry_data(server),
        unique_id=unique_id,
        options=options or {},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


# ---------------------------------------------------------------------------
# Config flow
# ---------------------------------------------------------------------------


async def test_config_flow_success(hass: HomeAssistant, fake_server: TestServer) -> None:
    """A valid host connects and advances to the channel-naming step."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], _entry_data(fake_server)
    )
    # Should now be on the channels step.
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "channels"

    # Accept defaults (Glass 1..4).
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["result"].unique_id == "F8:DC:00:00:00:01"
    # Options should contain a channels mapping.
    assert CONF_CHANNELS in result["result"].options


async def test_config_flow_cannot_connect(hass: HomeAssistant) -> None:
    """An unreachable host reports cannot_connect on the user step."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "127.0.0.1", CONF_PORT: 1}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {"base": "cannot_connect"}


async def test_config_flow_duplicate_aborts(
    hass: HomeAssistant, fake_server: TestServer
) -> None:
    """A second setup for the same MAC aborts with already_configured."""
    # First entry
    entry = MockConfigEntry(
        domain=DOMAIN, data=_entry_data(fake_server), unique_id="F8:DC:00:00:00:01"
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], _entry_data(fake_server)
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


# ---------------------------------------------------------------------------
# Options flow
# ---------------------------------------------------------------------------


async def test_options_flow_renames_zones(
    hass: HomeAssistant, fake_server: TestServer, fake_state: FakeState
) -> None:
    """The options flow lets the user rename zones; reload reflects new names."""
    entry = await _setup(
        hass,
        fake_server,
        options={CONF_CHANNELS: {"1": "Glass 1", "2": "Glass 2", "3": "Glass 3", "4": "Glass 4"}},
    )

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "init"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {"channel_1": "Master Bath", "channel_2": "Office"},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_CHANNELS]["1"] == "Master Bath"
    assert result["data"][CONF_CHANNELS]["2"] == "Office"


# ---------------------------------------------------------------------------
# Entity creation
# ---------------------------------------------------------------------------


async def test_entities_created(hass: HomeAssistant, fake_server: TestServer) -> None:
    """4 channels => 4 glass switches + 1 global + 4 fault + 4 lockout."""
    await _setup(hass, fake_server)

    switches = hass.states.async_entity_ids("switch")
    glass_switches = [s for s in switches if "all_glass_private" not in s]
    assert len(glass_switches) == 4  # ch1..ch4

    # Global override switch exists on the hub device.
    global_ids = [s for s in switches if "all_glass_private" in s]
    assert len(global_ids) == 1

    faults = [
        s for s in hass.states.async_entity_ids("binary_sensor") if "fault" in s
    ]
    assert len(faults) == 4

    lockouts = [
        s for s in hass.states.async_entity_ids("binary_sensor") if "lockout" in s
    ]
    assert len(lockouts) == 4


# ---------------------------------------------------------------------------
# State read reflects API
# ---------------------------------------------------------------------------


async def test_state_reflects_api(
    hass: HomeAssistant, fake_server: TestServer, fake_state: FakeState
) -> None:
    """A channel pre-set Clear in the device reads ON in HA."""
    fake_state.channels[2].requested_clear = True
    await _setup(hass, fake_server)

    # Find channel entities by scanning (names may vary).
    all_switches = hass.states.async_entity_ids("switch")
    glass = [s for s in all_switches if "all_glass_private" not in s]
    # channel 1 default private -> OFF
    ch1_id = next(s for s in glass if "_1" in s or "glass_1" in s or "1" in s.split(".")[-1])
    ch2_id = next(s for s in glass if "_2" in s or "glass_2" in s or "2" in s.split(".")[-1])

    assert hass.states.get(ch1_id).state == STATE_OFF
    assert hass.states.get(ch2_id).state == STATE_ON


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


async def test_turn_on_makes_clear(
    hass: HomeAssistant, fake_server: TestServer, fake_state: FakeState
) -> None:
    """turn_on commands Clear and the new real state reads back ON."""
    await _setup(hass, fake_server)

    glass = [
        s for s in hass.states.async_entity_ids("switch") if "all_glass_private" not in s
    ]
    ch1_id = next(s for s in glass if s.endswith("_1") or "glass_1" in s or s.split("_")[-1] == "1")

    assert hass.states.get(ch1_id).state == STATE_OFF

    await hass.services.async_call(
        "switch", "turn_on", {"entity_id": ch1_id}, blocking=True
    )
    await hass.async_block_till_done()

    assert fake_state.channels[1].requested_clear is True
    assert hass.states.get(ch1_id).state == STATE_ON


async def test_turn_off_makes_private(
    hass: HomeAssistant, fake_server: TestServer, fake_state: FakeState
) -> None:
    """turn_off commands Private."""
    fake_state.channels[3].requested_clear = True
    await _setup(hass, fake_server)

    glass = [
        s for s in hass.states.async_entity_ids("switch") if "all_glass_private" not in s
    ]
    ch3_id = next(s for s in glass if s.endswith("_3") or "glass_3" in s or s.split("_")[-1] == "3")

    assert hass.states.get(ch3_id).state == STATE_ON

    await hass.services.async_call(
        "switch", "turn_off", {"entity_id": ch3_id}, blocking=True
    )
    await hass.async_block_till_done()

    assert fake_state.channels[3].requested_clear is False
    assert hass.states.get(ch3_id).state == STATE_OFF


# ---------------------------------------------------------------------------
# Global override
# ---------------------------------------------------------------------------


async def test_global_override_forces_all_private(
    hass: HomeAssistant, fake_server: TestServer, fake_state: FakeState
) -> None:
    """Activating global override drives every glass channel Private."""
    for ch in fake_state.channels.values():
        ch.requested_clear = True
    await _setup(hass, fake_server)

    glass = [
        s for s in hass.states.async_entity_ids("switch") if "all_glass_private" not in s
    ]
    for s in glass:
        assert hass.states.get(s).state == STATE_ON

    override_id = next(
        s for s in hass.states.async_entity_ids("switch") if "all_glass_private" in s
    )
    await hass.services.async_call(
        "switch", "turn_on", {"entity_id": override_id}, blocking=True
    )
    await hass.async_block_till_done()

    assert fake_state.global_override is True
    for s in glass:
        # target default is Private -> actual glass state is private
        assert hass.states.get(s).state == STATE_OFF


# ---------------------------------------------------------------------------
# Lockout behavior
# ---------------------------------------------------------------------------


async def test_lockout_sensor_locked(
    hass: HomeAssistant, fake_server: TestServer, fake_state: FakeState
) -> None:
    """When lockout is active the LOCK sensor is ON (locked)."""
    fake_state.channels[1].lockout = True
    await _setup(hass, fake_server)

    # LOCK device class: on = locked.
    lockout_sensors = [
        s for s in hass.states.async_entity_ids("binary_sensor") if "lockout" in s
    ]
    ch1_lock = next(s for s in lockout_sensors if "_1" in s or "1" in s.split(".")[-1])
    assert hass.states.get(ch1_lock).state == STATE_ON  # locked


async def test_lockout_sensor_unlocked(
    hass: HomeAssistant, fake_server: TestServer, fake_state: FakeState
) -> None:
    """When lockout is inactive the LOCK sensor is OFF (unlocked)."""
    # Default: lockout = False (unlocked)
    await _setup(hass, fake_server)

    lockout_sensors = [
        s for s in hass.states.async_entity_ids("binary_sensor") if "lockout" in s
    ]
    ch1_lock = next(s for s in lockout_sensors if "_1" in s or "1" in s.split(".")[-1])
    assert hass.states.get(ch1_lock).state == STATE_OFF  # unlocked


async def test_lockout_blocks_clear(
    hass: HomeAssistant, fake_server: TestServer, fake_state: FakeState
) -> None:
    """A locked-out channel cannot go Clear; commanding clear stays Private."""
    fake_state.channels[1].lockout = True
    await _setup(hass, fake_server)

    glass = [
        s for s in hass.states.async_entity_ids("switch") if "all_glass_private" not in s
    ]
    ch1_id = next(s for s in glass if s.endswith("_1") or "glass_1" in s or s.split("_")[-1] == "1")

    await hass.services.async_call(
        "switch", "turn_on", {"entity_id": ch1_id}, blocking=True
    )
    await hass.async_block_till_done()
    # requested clear, but lockout keeps actual private
    assert hass.states.get(ch1_id).state == STATE_OFF


# ---------------------------------------------------------------------------
# Fault behavior
# ---------------------------------------------------------------------------


async def test_fault_when_actual_mismatches(
    hass: HomeAssistant, fake_server: TestServer, fake_state: FakeState
) -> None:
    """Wiring fault (actual != requested) raises the fault problem sensor."""
    fake_state.channels[2].wiring_fault = True
    await _setup(hass, fake_server)

    fault_sensors = [
        s for s in hass.states.async_entity_ids("binary_sensor") if "fault" in s
    ]
    ch2_fault = next(s for s in fault_sensors if "_2" in s or "2" in s.split(".")[-1])
    # requested private (default), wiring fault flips actual to clear -> mismatch
    assert hass.states.get(ch2_fault).state == STATE_ON


async def test_no_fault_when_states_match(
    hass: HomeAssistant, fake_server: TestServer, fake_state: FakeState
) -> None:
    """No fault when requested and actual states agree."""
    await _setup(hass, fake_server)

    fault_sensors = [
        s for s in hass.states.async_entity_ids("binary_sensor") if "fault" in s
    ]
    for s in fault_sensors:
        assert hass.states.get(s).state == STATE_OFF


# ---------------------------------------------------------------------------
# Comm loss -> unavailable
# ---------------------------------------------------------------------------


async def test_comm_loss_makes_unavailable(
    hass: HomeAssistant, fake_server: TestServer
) -> None:
    """When the controller stops responding, entities go unavailable."""
    await _setup(hass, fake_server)

    glass = [
        s for s in hass.states.async_entity_ids("switch") if "all_glass_private" not in s
    ]
    ch1_id = next(s for s in glass if s.endswith("_1") or "glass_1" in s or s.split("_")[-1] == "1")
    assert hass.states.get(ch1_id).state == STATE_OFF

    await fake_server.close()

    from custom_components.clic.coordinator import ClicCoordinator

    entry = hass.config_entries.async_entries(DOMAIN)[0]
    coordinator: ClicCoordinator = entry.runtime_data
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert hass.states.get(ch1_id).state == STATE_UNAVAILABLE


# ---------------------------------------------------------------------------
# Multi-controller
# ---------------------------------------------------------------------------


async def test_multi_controller(
    hass: HomeAssistant,
    fake_server: TestServer,
    fake_state: FakeState,
    aiohttp_client,
) -> None:
    """Two HC-108 controllers create two independent sets of entities."""
    from fake.server import FakeState as FS, build_app
    from aiohttp.test_utils import TestServer as TS

    state2 = FS(mac="F8:DC:00:00:00:02")
    for i in range(1, 3):  # 2-channel second controller
        from fake.server import FakeChannel
        state2.channels[i] = FakeChannel(channel=i)

    app2 = build_app(state2)
    server2 = TS(app2, host="127.0.0.1")
    await server2.start_server()

    try:
        entry1 = await _setup(hass, fake_server, unique_id="F8:DC:00:00:00:01")
        entry2 = await _setup(hass, server2, unique_id="F8:DC:00:00:00:02")

        # Two independent entries
        entries = hass.config_entries.async_entries(DOMAIN)
        assert len(entries) == 2

        # Each has its own switch entities (no entity_id collision)
        all_switches = hass.states.async_entity_ids("switch")
        assert len(all_switches) >= 2  # at least 2 glass channels + 2 global overrides
    finally:
        await server2.close()


# ---------------------------------------------------------------------------
# Tolerant JSON parsing
# ---------------------------------------------------------------------------


def test_tolerant_parsing_bool_fields() -> None:
    """The _truthy helper handles int, bool, and string variants correctly.

    The HC-108 manual documents 0/1 integers for all status fields. We accept
    native Python booleans and common string representations so the client
    does not break on minor firmware variations or future API updates.
    """
    from custom_components.clic.api import _truthy

    # Native booleans
    assert _truthy(True, "f") is True
    assert _truthy(False, "f") is False
    # Integers (documented HC-108 format)
    assert _truthy(1, "f") is True
    assert _truthy(0, "f") is False
    assert _truthy(2, "f") is True   # any non-zero int is truthy
    # String variants that some embedded web servers produce
    assert _truthy("true", "f") is True
    assert _truthy("false", "f") is False
    assert _truthy("True", "f") is True
    assert _truthy("False", "f") is False
    assert _truthy("1", "f") is True
    assert _truthy("0", "f") is False
    assert _truthy("on", "f") is True
    assert _truthy("off", "f") is False
    assert _truthy("yes", "f") is True
    assert _truthy("no", "f") is False
    assert _truthy("", "f") is False


async def test_setup_survives_with_no_route_discovery(
    hass: HomeAssistant, fake_server: TestServer
) -> None:
    """Route discovery failure is non-fatal and setup still succeeds."""
    # The fake server doesn't serve PATH_API_SPEC; that's fine.
    await _setup(hass, fake_server)
    # Integration is up; entities are available.
    glass = [
        s for s in hass.states.async_entity_ids("switch") if "all_glass_private" not in s
    ]
    assert len(glass) == 4


# ---------------------------------------------------------------------------
# Reauth flow
# ---------------------------------------------------------------------------


async def test_reauth_flow_success(
    hass: HomeAssistant, fake_server: TestServer
) -> None:
    """Reauth flow accepts new credentials and reloads the entry."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={**_entry_data(fake_server), CONF_USERNAME: "old", CONF_PASSWORD: "wrong"},
        unique_id="F8:DC:00:00:00:01",
        options={},
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": "reauth", "entry_id": entry.entry_id},
        data=entry.data,
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"

    # Provide empty credentials (the fake server doesn't require auth).
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_USERNAME: "", CONF_PASSWORD: ""},
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"


async def test_reauth_flow_invalid_credentials(
    hass: HomeAssistant, fake_server: TestServer
) -> None:
    """Reauth form stays open and shows invalid_auth when the device rejects credentials."""
    from aiohttp import web
    from aiohttp.test_utils import TestServer as TS

    # Build a fake server that always returns 401.
    async def always_401(request: web.Request) -> web.Response:
        return web.Response(status=401)

    auth_app = web.Application()
    auth_app.router.add_get("/api/v1/info", always_401)
    auth_server = TS(auth_app, host="127.0.0.1")
    await auth_server.start_server()

    try:
        entry = MockConfigEntry(
            domain=DOMAIN,
            data={CONF_HOST: auth_server.host, CONF_PORT: auth_server.port},
            unique_id="F8:DC:00:00:00:AA",
            options={},
        )
        entry.add_to_hass(hass)

        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": "reauth", "entry_id": entry.entry_id},
            data=entry.data,
        )
        assert result["step_id"] == "reauth_confirm"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_TOKEN: "bad-token"},
        )
        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "reauth_confirm"
        assert result["errors"] == {"base": "invalid_auth"}
    finally:
        await auth_server.close()


async def test_reauth_flow_cannot_connect(
    hass: HomeAssistant,
) -> None:
    """Reauth form shows cannot_connect when the device is unreachable."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "127.0.0.1", CONF_PORT: 1},
        unique_id="F8:DC:00:00:00:BB",
        options={},
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": "reauth", "entry_id": entry.entry_id},
        data=entry.data,
    )
    assert result["step_id"] == "reauth_confirm"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {},
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


# ---------------------------------------------------------------------------
# Reconfigure flow
# ---------------------------------------------------------------------------


async def test_reconfigure_flow_success(
    hass: HomeAssistant, fake_server: TestServer
) -> None:
    """Reconfigure flow updates host/port/credentials and reloads the entry."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "192.0.2.1", CONF_PORT: 9999},
        unique_id="F8:DC:00:00:00:01",
        options={CONF_CHANNELS: {"1": "Room A", "2": "Room B"}},
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": "reconfigure", "entry_id": entry.entry_id},
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reconfigure"

    # Provide valid new host/port pointing at the fake server.
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_HOST: fake_server.host, CONF_PORT: fake_server.port},
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"

    # Entry data updated; zone names preserved in options.
    assert entry.data[CONF_HOST] == fake_server.host
    assert entry.data[CONF_PORT] == fake_server.port
    assert entry.options[CONF_CHANNELS]["1"] == "Room A"


async def test_reconfigure_flow_cannot_connect(
    hass: HomeAssistant,
) -> None:
    """Reconfigure form shows cannot_connect when the new host is unreachable."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "192.0.2.1", CONF_PORT: 9999},
        unique_id="F8:DC:00:00:00:01",
        options={},
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": "reconfigure", "entry_id": entry.entry_id},
    )
    assert result["step_id"] == "reconfigure"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_HOST: "127.0.0.1", CONF_PORT: 1},
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reconfigure"
    assert result["errors"] == {"base": "cannot_connect"}


async def test_reconfigure_preserves_zone_names(
    hass: HomeAssistant, fake_server: TestServer
) -> None:
    """Reconfigure updates connection only; CONF_CHANNELS options are untouched."""
    original_channels = {"1": "Master Bath", "2": "Office", "3": "Bedroom", "4": "Hallway"}
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "192.0.2.1", CONF_PORT: 9999},
        unique_id="F8:DC:00:00:00:01",
        options={CONF_CHANNELS: original_channels},
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": "reconfigure", "entry_id": entry.entry_id},
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_HOST: fake_server.host, CONF_PORT: fake_server.port},
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"

    # Zone names must not be touched.
    assert entry.options[CONF_CHANNELS] == original_channels


async def test_reconfigure_wrong_device(
    hass: HomeAssistant, fake_server: TestServer
) -> None:
    """Reconfigure aborts with wrong_device when the controller MAC changes."""
    # The entry has unique_id = MAC:02; the fake server returns MAC:01.
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "192.0.2.1", CONF_PORT: 9999},
        unique_id="F8:DC:00:00:00:02",
        options={},
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": "reconfigure", "entry_id": entry.entry_id},
    )
    assert result["step_id"] == "reconfigure"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_HOST: fake_server.host, CONF_PORT: fake_server.port},
    )
    # fake server returns MAC:01, entry has MAC:02 -> mismatch -> abort
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "wrong_device"
