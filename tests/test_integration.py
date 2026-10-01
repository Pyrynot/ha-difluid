"""Exercise real HA entity setup and recorder-facing state with captured packets."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.difluid.protocol.codec import Decoder

FIXTURE = json.loads((Path(__file__).parent / "fixtures/r2_pp/measurements.json").read_text())
PACKETS = Decoder().feed(b"".join(bytes.fromhex(v) for v in FIXTURE["notifications"]))


async def setup(hass):
    entry = MockConfigEntry(
        domain="difluid",
        title="R2 PP Test",
        unique_id="AA:BB:CC:DD:EE:FF",
        data={"address": "AA:BB:CC:DD:EE:FF"},
    )
    entry.add_to_hass(hass)
    with patch("custom_components.difluid.coordinator.DiFluidCoordinator.start", AsyncMock()):
        assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_physical_results_entities_replays_and_sleep(hass, mock_bluetooth):
    entry = await setup(hass)
    coordinator = entry.runtime_data
    assert hass.states.get("event.r2_pp_test_measurement").state == "unknown"
    coordinator._packet(PACKETS[0])
    await hass.async_block_till_done()
    assert hass.states.get("sensor.r2_pp_test_brix") is None
    coordinator._packet(PACKETS[1])
    await hass.async_block_till_done()
    brix = hass.states.get("sensor.r2_pp_test_brix")
    assert round(float(brix.state), 1) == 7.5
    event = hass.states.get("event.r2_pp_test_measurement")
    assert event.attributes["event_type"] == "measurement"
    assert event.attributes["refractive_index"] == 1.344
    assert hass.states.get("sensor.r2_pp_test_refractive_index").state == "1.344"
    coordinator._packet(PACKETS[1])
    await hass.async_block_till_done()
    assert hass.states.get(event.entity_id).state == event.state
    coordinator._packet(PACKETS[3])
    await hass.async_block_till_done()
    assert hass.states.get(event.entity_id).state != event.state
    assert hass.states.get("sensor.r2_pp_test_refractive_index").state == "1.34472"
    coordinator._disconnected()
    await hass.async_block_till_done()
    assert round(float(hass.states.get(brix.entity_id).state), 1) == 8.0
    assert hass.states.get("binary_sensor.r2_pp_test_connected").state == "off"
    assert hass.states.get("button.r2_pp_test_measure").state == "unavailable"
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_persisted_identity_does_not_reemit(hass, mock_bluetooth):
    entry = await setup(hass)
    coordinator = entry.runtime_data
    coordinator._packet(PACKETS[1])
    await hass.async_block_till_done()
    await coordinator.stop()
    original = coordinator.data["sample"]
    from custom_components.difluid.coordinator import DiFluidCoordinator

    restored = DiFluidCoordinator(hass, entry)
    with (
        patch.object(restored, "_run", AsyncMock()),
        patch(
            "custom_components.difluid.coordinator.bluetooth.async_register_callback",
            return_value=lambda: None,
        ),
    ):
        await restored.start()
        await hass.async_block_till_done()
    events = []
    restored.sample_listeners.append(events.append)
    restored._packet(PACKETS[1])
    assert not events
    assert restored.data["sample"] == original
    await restored.stop()
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_metadata_and_invalid_status_do_not_replace_result(hass, mock_bluetooth):
    entry = await setup(hass)
    coordinator = entry.runtime_data
    coordinator._packet(PACKETS[1])
    original = coordinator.data["sample"]
    coordinator._packet(PACKETS[2])
    assert coordinator.data["sample"] == original
    assert coordinator.data["status"] == "measuring"
    metadata = json.loads((Path(__file__).parent / "fixtures/r2_pp/responses.json").read_text())
    for name in ["firmware", "profile", "clock", "timezone"]:
        coordinator._packet(Decoder().feed(bytes.fromhex(metadata[name]))[0])
    await hass.async_block_till_done()
    assert coordinator.data["metadata"]["firmware"] == "V025-dirty"
    assert coordinator.data["metadata"]["profile_name"] == "Brix"
    assert coordinator.data["metadata"]["timezone"] == 3
    assert coordinator.data["sample"] == original
    assert hass.states.get("sensor.r2_pp_test_firmware").state == "V025-dirty"
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_full_reload_restores_sample_without_new_measurement(hass, mock_bluetooth):
    entry = await setup(hass)
    entry.runtime_data._packet(PACKETS[1])
    await hass.async_block_till_done()
    previous = entry.runtime_data.data["sample"]
    assert await hass.config_entries.async_unload(entry.entry_id)
    with patch("custom_components.difluid.coordinator.DiFluidCoordinator._run", AsyncMock()):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    coordinator = entry.runtime_data
    assert coordinator.data["sample"] == previous
    assert round(float(hass.states.get("sensor.r2_pp_test_brix").state), 1) == 7.5
    events = []
    coordinator.sample_listeners.append(events.append)
    coordinator._packet(PACKETS[1])
    await hass.async_block_till_done()
    assert not events
    assert await hass.config_entries.async_unload(entry.entry_id)
