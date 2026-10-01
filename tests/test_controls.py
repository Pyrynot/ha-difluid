from unittest.mock import AsyncMock

import pytest
from homeassistant.exceptions import HomeAssistantError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.difluid.coordinator import DiFluidCoordinator
from custom_components.difluid.protocol.codec import Packet


def coordinator(hass):
    entry = MockConfigEntry(domain="difluid", data={"address": "AA:BB:CC:DD:EE:FF"})
    entry.add_to_hass(hass)
    return DiFluidCoordinator(hass, entry)


async def test_offline_action_never_sends(hass):
    c = coordinator(hass)
    c.client.request = AsyncMock()
    with pytest.raises(HomeAssistantError, match="Wake"):
        await c.command("measure")
    c.client.request.assert_not_called()


async def test_measure_accepted_and_busy_guard(hass):
    c = coordinator(hass)
    c._update(connected=True)
    c.client.request = AsyncMock(return_value=Packet(1, 3, 9, bytes.fromhex("0000000001000000")))
    await c.command("measure")
    with pytest.raises(HomeAssistantError, match="already"):
        await c.command("measure")
    assert c.client.request.await_count == 1


async def test_timeout_does_not_retry_measurement(hass):
    c = coordinator(hass)
    c._update(connected=True)
    c.client.request = AsyncMock(side_effect=TimeoutError)
    with pytest.raises(HomeAssistantError, match="failed"):
        await c.command("measure")
    assert c.client.request.await_count == 1


@pytest.mark.parametrize("value", [-12.5, 14.5, 3.25, float("nan")])
async def test_timezone_rejects_invalid_values(hass, value):
    c = coordinator(hass)
    c._update(connected=True)
    c.client.request = AsyncMock()
    with pytest.raises(HomeAssistantError, match="half-hour"):
        await c.command("timezone", value)
    c.client.request.assert_not_called()


async def test_timezone_verifies_readback(hass):
    c = coordinator(hass)
    c._update(connected=True)
    c.client.request = AsyncMock(return_value=Packet(0, 4, 2, b"\x06"))
    await c.command("timezone", 3)
    c.client.request = AsyncMock(return_value=Packet(0, 4, 2, b"\x05"))
    with pytest.raises(HomeAssistantError, match="readback"):
        await c.command("timezone", 3)
