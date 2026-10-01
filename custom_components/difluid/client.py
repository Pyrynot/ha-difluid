"""BLE transport using Home Assistant's local adapters and remote proxies."""

import asyncio
import logging
from collections.abc import Callable
from contextlib import suppress
from typing import Any

from bleak import BleakClient
from bleak.exc import BleakError
from bleak_retry_connector import BleakClientWithServiceCache, establish_connection
from homeassistant.components import bluetooth
from homeassistant.core import HomeAssistant

from .const import CHAR_UUID
from .protocol.codec import Decoder, Packet, encode

_LOGGER = logging.getLogger(__name__)


class DiFluidClient:
    """One peripheral connection, incremental notifications, serialized commands."""

    def __init__(
        self,
        hass: HomeAssistant,
        address: str,
        on_packet: Callable[[Packet], None],
        on_disconnect: Callable[[], None],
    ) -> None:
        self.hass = hass
        self.address = address
        self.on_packet = on_packet
        self.on_disconnect = on_disconnect
        self.client: BleakClient | None = None
        self.decoder = Decoder()
        self.lock = asyncio.Lock()
        self.pending: tuple[tuple[int, int], asyncio.Future[Packet]] | None = None

    @property
    def connected(self) -> bool:
        return self.client is not None and self.client.is_connected

    async def connect(self) -> None:
        device = bluetooth.async_ble_device_from_address(self.hass, self.address, connectable=True)
        if device is None:
            raise BleakError("Instrument is not currently visible")
        self.decoder.reset()
        owner = self

        class ManagedClient(BleakClientWithServiceCache):
            """Retain ownership even if service discovery or connect is cancelled."""

            def __init__(self, *args: Any, **kwargs: Any) -> None:
                super().__init__(*args, **kwargs)
                owner.client = self

        try:
            async with asyncio.timeout(30):
                self.client = await establish_connection(
                    ManagedClient,
                    device,
                    device.name or "DiFluid R2 PP",
                    disconnected_callback=self._disconnected,
                    ble_device_callback=lambda: (
                        bluetooth.async_ble_device_from_address(
                            self.hass, self.address, connectable=True
                        )
                        or device
                    ),
                    max_attempts=1,
                    timeout=20,
                )
                await self.client.start_notify(CHAR_UUID, self._notification)
        except BaseException:
            with suppress(BleakError, TimeoutError, OSError):
                await self.disconnect()
            raise

    def _notification(self, _characteristic: object, data: bytearray) -> None:
        for packet in self.decoder.feed(bytes(data)):
            if packet.address not in (0, 1):
                continue
            if self.pending and self.pending[0] == (packet.function, packet.register):
                future = self.pending[1]
                if not future.done():
                    future.set_result(packet)
            self.on_packet(packet)

    def _disconnected(self, _client: BleakClient) -> None:
        if self.pending and not self.pending[1].done():
            self.pending[1].set_exception(BleakError("Instrument disconnected"))
        self.on_disconnect()

    async def request(
        self,
        function: int,
        register: int,
        payload: bytes = b"",
        *,
        response: tuple[int, int] | None = None,
    ) -> Packet:
        async with self.lock:
            if not self.connected:
                raise BleakError("Wake the instrument and wait for a Bluetooth connection")
            future: asyncio.Future[Packet] = asyncio.get_running_loop().create_future()
            self.pending = (response or (function, register), future)
            try:
                async with asyncio.timeout(15):
                    assert self.client is not None
                    await self.client.write_gatt_char(
                        CHAR_UUID, encode(function, register, payload), response=True
                    )
                    return await future
            finally:
                self.pending = None
                if not future.done():
                    future.cancel()
                elif not future.cancelled():
                    future.exception()  # Retrieve errors even if the write failed first.

    async def disconnect(self) -> None:
        client, self.client = self.client, None
        if client:
            await client.disconnect()
