"""Prevent boot-time connection storms, stale retries, and leaked connections."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from bleak.exc import BleakError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.difluid.coordinator import DiFluidCoordinator


def make_coordinator(hass):
    entry = MockConfigEntry(domain="difluid", data={"address": "AA:BB:CC:DD:EE:FF"})
    entry.add_to_hass(hass)
    coordinator = DiFluidCoordinator(hass, entry)
    coordinator.not_before = hass.loop.time() + 0.03
    coordinator._fresh_advertisement = MagicMock(return_value=True)
    return coordinator


async def test_boot_delay_cooldown_disconnect_and_unload(hass):
    coordinator = make_coordinator(hass)
    ready = asyncio.Event()
    attempts = []
    backend = MagicMock(is_connected=False, disconnect=AsyncMock())
    unsubscribe = MagicMock()

    async def connect():
        attempts.append(hass.loop.time())
        if len(attempts) == 1:
            hass.loop.call_later(0.001, coordinator.wake.set)
            raise BleakError("transient radio failure")
        backend.is_connected = True
        coordinator.client.client = backend

    coordinator.client.connect = AsyncMock(side_effect=connect)
    coordinator.refresh_metadata = AsyncMock(side_effect=ready.set)
    with (
        patch("custom_components.difluid.coordinator.RETRY_COOLDOWN_SECONDS", 0.04),
        patch("custom_components.difluid.coordinator.METADATA_SETTLE_SECONDS", 0),
        patch(
            "custom_components.difluid.coordinator.bluetooth.async_register_callback",
            return_value=unsubscribe,
        ),
    ):
        started = hass.loop.time()
        await coordinator.start()
        await asyncio.sleep(0.01)
        assert not attempts
        await asyncio.wait_for(ready.wait(), timeout=1)
        assert len(attempts) == 2
        assert attempts[0] - started >= 0.025
        assert attempts[1] - attempts[0] >= 0.035
        assert coordinator.data["connected"]
        ready.clear()
        backend.is_connected = False
        coordinator._disconnected()
        await asyncio.wait_for(ready.wait(), timeout=1)
        assert len(attempts) == 3
        assert coordinator.data["connected"]
        await coordinator.stop()
        unsubscribe.assert_called_once()
        backend.disconnect.assert_awaited_once()
        assert coordinator.task.done()
        await coordinator.stop()
        backend.disconnect.assert_awaited_once()


async def test_repeated_failures_stop_automatic_connections(hass):
    coordinator = make_coordinator(hass)
    coordinator.client.connect = AsyncMock(side_effect=BleakError("failed"))
    with (
        patch("custom_components.difluid.coordinator.RETRY_COOLDOWN_SECONDS", 0.01),
        patch(
            "custom_components.difluid.coordinator.bluetooth.async_register_callback",
            return_value=lambda: None,
        ),
    ):
        await coordinator.start()
        for _ in range(30):
            coordinator.wake.set()
            await asyncio.sleep(0.005)
        assert coordinator.client.connect.await_count == 3
        assert coordinator.data["status"] == "connection_blocked"
        await coordinator.stop()


async def test_stale_discovery_does_not_attempt_connection(hass):
    coordinator = make_coordinator(hass)
    del coordinator._fresh_advertisement
    coordinator.client.connect = AsyncMock()
    with (
        patch(
            "custom_components.difluid.coordinator.bluetooth.async_last_service_info",
            return_value=SimpleNamespace(time=hass.loop.time() - 60),
        ),
        patch(
            "custom_components.difluid.coordinator.bluetooth.async_register_callback",
            return_value=lambda: None,
        ),
    ):
        await coordinator.start()
        await asyncio.sleep(0.05)
        coordinator.client.connect.assert_not_called()
        await coordinator.stop()


async def test_unload_cancels_boot_delay(hass):
    coordinator = make_coordinator(hass)
    coordinator.not_before = hass.loop.time() + 20
    coordinator.client.connect = AsyncMock()
    with patch(
        "custom_components.difluid.coordinator.bluetooth.async_register_callback",
        return_value=lambda: None,
    ):
        await coordinator.start()
        await asyncio.sleep(0)
        await coordinator.stop()
    coordinator.client.connect.assert_not_called()
    assert coordinator.task.done()
