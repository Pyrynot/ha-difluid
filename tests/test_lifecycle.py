"""Connection failure, wake-up reconnect, and clean unload without real Bluetooth."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from bleak.exc import BleakError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.difluid.coordinator import DiFluidCoordinator


async def test_connect_failure_retry_disconnect_and_unload(hass):
    entry = MockConfigEntry(domain="difluid", data={"address": "AA:BB:CC:DD:EE:FF"})
    entry.add_to_hass(hass)
    coordinator = DiFluidCoordinator(hass, entry)
    ready = asyncio.Event()
    attempts = 0
    backend = MagicMock(is_connected=False, disconnect=AsyncMock())
    unsubscribe = MagicMock()

    async def connect():
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            # A fresh advertisement should interrupt the connection backoff.
            hass.loop.call_later(0.01, coordinator.wake.set)
            raise BleakError("transient radio failure")
        backend.is_connected = True
        coordinator.client.client = backend

    coordinator.client.connect = AsyncMock(side_effect=connect)
    coordinator.refresh_metadata = AsyncMock(side_effect=ready.set)
    with patch(
        "custom_components.difluid.coordinator.bluetooth.async_register_callback",
        return_value=unsubscribe,
    ):
        await coordinator.start()
        await asyncio.wait_for(ready.wait(), timeout=1)
        assert attempts == 2
        assert coordinator.data["connected"]
        ready.clear()
        backend.is_connected = False
        coordinator._disconnected()
        await asyncio.wait_for(ready.wait(), timeout=1)
        assert attempts == 3
        assert coordinator.data["connected"]
        await coordinator.stop()
        unsubscribe.assert_called_once()
        backend.disconnect.assert_awaited_once()
        assert coordinator.task.done()
        await coordinator.stop()  # HA shutdown and unload can both request cleanup.
        backend.disconnect.assert_awaited_once()
