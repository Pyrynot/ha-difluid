"""Transport regressions from real PP response addresses and command lifecycle."""

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from bleak.exc import BleakError

from custom_components.difluid.client import DiFluidClient
from custom_components.difluid.protocol.codec import Decoder

FIXTURE = json.loads((Path(__file__).parent / "fixtures/r2_pp/responses.json").read_text())


async def test_real_metadata_response_resolves_pending_request(hass):
    packets = []
    client = DiFluidClient(hass, "AA:BB:CC:DD:EE:FF", packets.append, lambda: None)
    backend = client.client = MagicMock(is_connected=True)

    async def write(*args, **kwargs):
        # The reply can arrive before write acknowledgement.
        client._notification(None, bytearray.fromhex(FIXTURE["firmware"]))

    backend.write_gatt_char = AsyncMock(side_effect=write)
    result = await client.request(5, 11)
    assert result.address == 1
    assert result.payload.startswith(b"V025-dirty")
    assert packets == [result]
    assert client.pending is None


async def test_disconnect_releases_request_and_serialization_lock(hass):
    client = DiFluidClient(hass, "AA:BB:CC:DD:EE:FF", lambda p: None, lambda: None)
    backend = client.client = MagicMock(is_connected=True)
    backend.write_gatt_char = AsyncMock()
    task = asyncio.create_task(client.request(5, 11))
    await asyncio.sleep(0)
    client._disconnected(backend)
    with pytest.raises(BleakError, match="disconnected"):
        await task
    assert client.pending is None
    assert not client.lock.locked()


async def test_cancellation_releases_pending_and_lock(hass):
    client = DiFluidClient(hass, "AA:BB:CC:DD:EE:FF", lambda p: None, lambda: None)
    client.client = MagicMock(is_connected=True, write_gatt_char=AsyncMock())
    task = asyncio.create_task(client.request(5, 11))
    await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert client.pending is None
    assert not client.lock.locked()


def test_remote_measurement_ack_and_result_fixture():
    packets = Decoder().feed(bytes.fromhex(FIXTURE["remote_measurement"]))
    assert [(p.address, p.function, p.register) for p in packets] == [
        (1, 3, 9),
        (0, 3, 6),
        (0, 3, 6),
    ]
    assert packets[0].payload == bytes.fromhex("0000000001000000")
