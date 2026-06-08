"""End-to-end tests for the Cardinal CLiC integration against the fake server."""

from __future__ import annotations

from aiohttp.test_utils import TestServer

from homeassistant.const import CONF_HOST, CONF_PORT, STATE_OFF, STATE_ON, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.clic.const import DOMAIN
from fake.server import FakeState

from pytest_homeassistant_custom_component.common import MockConfigEntry


def _entry_data(server: TestServer) -> dict:
    return {CONF_HOST: server.host, CONF_PORT: server.port}


async def _setup(hass: HomeAssistant, server: TestServer) -> MockConfigEntry:
    entry = MockConfigEntry(domain=DOMAIN, data=_entry_data(server), unique_id="F8:DC:00:00:00:01")
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


# --- config flow ------------------------------------------------------------


async def test_config_flow_success(hass: HomeAssistant, fake_server: TestServer) -> None:
    """A valid host creates an entry keyed by the device MAC."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    assert result["type"] is FlowResultType.FORM

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], _entry_data(fake_server)
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["result"].unique_id == "F8:DC:00:00:00:01"


async def test_config_flow_cannot_connect(hass: HomeAssistant) -> None:
    """An unreachable host reports cannot_connect."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "127.0.0.1", CONF_PORT: 1}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


# --- setup + entity creation ------------------------------------------------


async def test_entities_created(hass: HomeAssistant, fake_server: TestServer) -> None:
    """4 channels => 4 glass switches + 1 global + 4 fault + 4 lockout."""
    await _setup(hass, fake_server)

    glass = [
        s for s in hass.states.async_entity_ids("switch")
        if "glass" in s and "all_glass_private" not in s
    ]
    assert len(glass) == 4  # ch1..ch4
    assert hass.states.get("switch.clic_hc_108_all_glass_private") is not None
    faults = [s for s in hass.states.async_entity_ids("binary_sensor") if "problem" in s]
    assert len(faults) == 4
    lockouts = [s for s in hass.states.async_entity_ids("binary_sensor") if "lock" in s]
    assert len(lockouts) == 4


# --- state read reflects API ------------------------------------------------


async def test_state_reflects_api(
    hass: HomeAssistant, fake_server: TestServer, fake_state: FakeState
) -> None:
    """A channel pre-set Clear in the device reads ON in HA."""
    fake_state.channels[2].requested_clear = True
    await _setup(hass, fake_server)

    ch1 = hass.states.get("switch.clic_glass_1")
    ch2 = hass.states.get("switch.clic_glass_2")
    assert ch1.state == STATE_OFF  # private
    assert ch2.state == STATE_ON  # clear


# --- set service -> state change --------------------------------------------


async def test_turn_on_makes_clear(
    hass: HomeAssistant, fake_server: TestServer, fake_state: FakeState
) -> None:
    """turn_on commands Clear and the new real state reads back ON."""
    await _setup(hass, fake_server)
    assert hass.states.get("switch.clic_glass_1").state == STATE_OFF

    await hass.services.async_call(
        "switch",
        "turn_on",
        {"entity_id": "switch.clic_glass_1"},
        blocking=True,
    )
    await hass.async_block_till_done()

    assert fake_state.channels[1].requested_clear is True
    assert hass.states.get("switch.clic_glass_1").state == STATE_ON


async def test_turn_off_makes_private(
    hass: HomeAssistant, fake_server: TestServer, fake_state: FakeState
) -> None:
    """turn_off commands Private."""
    fake_state.channels[3].requested_clear = True
    await _setup(hass, fake_server)
    assert hass.states.get("switch.clic_glass_3").state == STATE_ON

    await hass.services.async_call(
        "switch", "turn_off", {"entity_id": "switch.clic_glass_3"}, blocking=True
    )
    await hass.async_block_till_done()
    assert fake_state.channels[3].requested_clear is False
    assert hass.states.get("switch.clic_glass_3").state == STATE_OFF


# --- global override -> all private -----------------------------------------


async def test_global_override_forces_all_private(
    hass: HomeAssistant, fake_server: TestServer, fake_state: FakeState
) -> None:
    """Activating global override drives every glass channel Private."""
    for ch in fake_state.channels.values():
        ch.requested_clear = True
    await _setup(hass, fake_server)
    # all clear before override
    for ch in range(1, 5):
        assert hass.states.get(f"switch.clic_glass_{ch}").state == STATE_ON

    await hass.services.async_call(
        "switch", "turn_on", {"entity_id": "switch.clic_hc_108_all_glass_private"}, blocking=True
    )
    await hass.async_block_till_done()

    assert fake_state.global_override is True
    for ch in range(1, 5):
        # target default is Private -> actual glass state is private
        assert hass.states.get(f"switch.clic_glass_{ch}").state == STATE_OFF


# --- lockout behavior -------------------------------------------------------


async def test_lockout_blocks_clear(
    hass: HomeAssistant, fake_server: TestServer, fake_state: FakeState
) -> None:
    """A locked-out channel cannot go Clear; commanding clear stays Private."""
    fake_state.channels[1].lockout = True
    await _setup(hass, fake_server)

    # LOCK device class: on = unlocked. Locked channel reports off.
    assert hass.states.get("binary_sensor.clic_glass_1_lock").state == STATE_OFF

    await hass.services.async_call(
        "switch", "turn_on", {"entity_id": "switch.clic_glass_1"}, blocking=True
    )
    await hass.async_block_till_done()
    # requested clear, but lockout keeps actual private
    assert hass.states.get("switch.clic_glass_1").state == STATE_OFF


async def test_fault_when_actual_mismatches(
    hass: HomeAssistant, fake_server: TestServer, fake_state: FakeState
) -> None:
    """Wiring fault (actual != requested) raises the fault problem sensor."""
    fake_state.channels[2].wiring_fault = True
    await _setup(hass, fake_server)
    # requested private (default), wiring fault flips actual to clear -> mismatch
    assert hass.states.get("binary_sensor.clic_glass_2_problem").state == STATE_ON


# --- comm loss -> unavailable -----------------------------------------------


async def test_comm_loss_makes_unavailable(
    hass: HomeAssistant, fake_server: TestServer
) -> None:
    """When the controller stops responding, entities go unavailable."""
    await _setup(hass, fake_server)
    assert hass.states.get("switch.clic_glass_1").state == STATE_OFF

    await fake_server.close()

    from custom_components.clic.coordinator import ClicCoordinator

    entry = hass.config_entries.async_entries(DOMAIN)[0]
    coordinator: ClicCoordinator = entry.runtime_data
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert hass.states.get("switch.clic_glass_1").state == STATE_UNAVAILABLE
