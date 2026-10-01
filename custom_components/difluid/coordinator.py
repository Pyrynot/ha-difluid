"""Push state, reconnect lifecycle, and durable completed-measurement identity."""

import asyncio
import logging
import math
import struct
from collections.abc import Callable
from contextlib import suppress
from datetime import UTC, datetime
from typing import Any

from bleak.exc import BleakError
from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .client import DiFluidClient
from .const import DOMAIN
from .protocol.codec import Packet
from .protocol.measurement import parse_measurement

_LOGGER = logging.getLogger(__name__)
BOOT_GRACE_SECONDS = 20
RETRY_COOLDOWN_SECONDS = 60
MAX_CONNECTION_FAILURES = 3
ADVERTISEMENT_MAX_AGE = 10
STABLE_CONNECTION_SECONDS = 30
METADATA_SETTLE_SECONDS = 3


class DiFluidCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Keep listening while awake; retain the last successful sample while asleep."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(hass, _LOGGER, config_entry=entry, name=DOMAIN)
        self.entry = entry
        self.address = entry.data["address"]
        self.client = DiFluidClient(hass, self.address, self._packet, self._disconnected)
        self.data = {
            "connected": False,
            "status": "disconnected",
            "values": {},
            "metadata": {},
            "sample": None,
        }
        self.store: Store[dict[str, Any]] = Store(hass, 1, f"{DOMAIN}.{entry.entry_id}")
        self.seen: list[str] = []
        self.sample_listeners: list[Callable[[dict[str, Any]], None]] = []
        self.wake = asyncio.Event()
        self.stopped = False
        self.task: asyncio.Task[None] | None = None
        self.unsubscribe: Callable[[], None] | None = None
        self.measurement_pending = False
        self.measurement_deadline = 0.0
        self.not_before = self.hass.loop.time() + BOOT_GRACE_SECONDS
        self.connection_failures = 0
        self.connected_since: float | None = None
        self.last_advertisement: float | None = None

    async def start(self) -> None:
        if saved := await self.store.async_load():
            self.seen = saved.get("seen", [])[-64:]
            self._update(
                metadata=saved.get("metadata", {}),
                **{key: saved[key] for key in ("last_error", "last_result") if key in saved},
            )
            if sample := saved.get("sample"):
                self._update(sample=sample, values=sample["values"])
        self.unsubscribe = bluetooth.async_register_callback(
            self.hass,
            self._advertisement,
            {"address": self.address, "connectable": True},
            bluetooth.BluetoothScanningMode.ACTIVE,
        )
        self.wake.set()
        self.task = self.entry.async_create_background_task(
            self.hass, self._run(), "DiFluid connection"
        )

    @callback
    def _advertisement(
        self, _info: bluetooth.BluetoothServiceInfoBleak, _change: bluetooth.BluetoothChange
    ) -> None:
        now = self.hass.loop.time()
        if self.last_advertisement is None or now - self.last_advertisement > BOOT_GRACE_SECONDS:
            self.not_before = max(self.not_before, now + BOOT_GRACE_SECONDS)
        self.last_advertisement = now
        if not self.data["connected"]:
            self.wake.set()

    @callback
    def _disconnected(self) -> None:
        if self.stopped:
            return
        self.measurement_pending = False
        now = self.hass.loop.time()
        if self.connected_since is not None:
            if now - self.connected_since < STABLE_CONNECTION_SECONDS:
                self.connection_failures += 1
            else:
                self.connection_failures = 0
        self.connected_since = None
        self.not_before = max(self.not_before, now + RETRY_COOLDOWN_SECONDS)
        self._update(connected=False, status="disconnected")
        self.wake.set()

    def _update(self, **changes: object) -> None:
        self.async_set_updated_data({**self.data, **changes})

    def _fresh_advertisement(self) -> bool:
        info = bluetooth.async_last_service_info(self.hass, self.address, connectable=True)
        return info is not None and self.hass.loop.time() - info.time <= ADVERTISEMENT_MAX_AGE

    async def _run(self) -> None:
        while not self.stopped:
            await self.wake.wait()
            self.wake.clear()
            if self.client.connected:
                continue
            if self.connection_failures >= MAX_CONNECTION_FAILURES:
                self._update(connected=False, status="connection_blocked")
                continue
            # Advertisements and disconnect callbacks must not bypass this delay.
            # V025 has shown a boot failure with immediate HA connection attempts.
            await asyncio.sleep(max(0, self.not_before - self.hass.loop.time()))
            if self.hass.loop.time() < self.not_before:
                self.wake.set()
                continue
            if not self._fresh_advertisement():
                # Never repeatedly connect using stale cached discovery data.
                continue
            failures_before = self.connection_failures
            try:
                await self.client.connect()
                self.connected_since = self.hass.loop.time()
                self._update(connected=True, status="ready")
                await asyncio.sleep(METADATA_SETTLE_SECONDS)
                await self.refresh_metadata()
            except (BleakError, TimeoutError, OSError) as err:
                _LOGGER.debug("DiFluid connection unavailable: %s", err)
                self.connected_since = None
                self.connection_failures = max(self.connection_failures, failures_before + 1)
                with suppress(BleakError, TimeoutError, OSError):
                    await self.client.disconnect()
                self.not_before = self.hass.loop.time() + RETRY_COOLDOWN_SECONDS
                self._update(connected=False, status="disconnected")
                self.wake.set()

    async def refresh_metadata(self) -> None:
        for function, register in ((5, 11), (3, 14), (4, 1), (4, 2)):
            try:
                await self.client.request(function, register)
            except TimeoutError:
                _LOGGER.debug("Optional metadata query %s/%s timed out", function, register)

    @callback
    def _packet(self, packet: Packet) -> None:
        try:
            measurement = parse_measurement(packet)
        except ValueError as err:
            _LOGGER.debug("Unsupported measurement ignored: %s", err)
            return
        if measurement is not None:
            values = dict(measurement.values)
            status = int(values["det_result"])
            self.measurement_pending = status in (11, 12)
            self.measurement_deadline = self.hass.loop.time() + 60
            self._update(
                status={
                    0: "ready",
                    1: "calibrated",
                    2: "measurement_error",
                    3: "hardware_error",
                    11: "measuring",
                    12: "calibrating",
                }.get(status, "unknown"),
                last_result=status,
                last_error=int(values["det_error_code"]),
            )
            if not measurement.successful or measurement.identity in self.seen:
                return
            # Device time is retained separately from HA receipt time. Never use a
            # potentially incorrect device clock to backdate HA recorder history.
            try:
                device_time = datetime.fromtimestamp(values["timestamp"], UTC).isoformat()
            except ValueError, OverflowError, OSError:
                return
            sample = {
                "id": measurement.identity,
                "received_at": dt_util.utcnow().isoformat(),
                "device_time": device_time,
                "values": values,
            }
            self.seen = (self.seen + [measurement.identity])[-64:]
            self._update(values=values, sample=sample)
            self.store.async_delay_save(self._stored_data, 1)
            for listener in tuple(self.sample_listeners):
                listener(sample)
            return
        metadata = dict(self.data["metadata"])
        payload = packet.payload
        if (packet.function, packet.register) == (5, 11) and len(payload) == 32:
            metadata["firmware"] = payload.split(b"\0", 1)[0].decode("ascii", errors="replace")
        elif (packet.function, packet.register) == (3, 14) and len(payload) == 53:
            metadata.update(
                profile_index=payload[0],
                profile_name=payload[1:17].split(b"\0", 1)[0].decode("utf-8", errors="replace"),
                profile_unit=payload[17:21].split(b"\0", 1)[0].decode("utf-8", errors="replace"),
            )
        elif (packet.function, packet.register) == (4, 1) and len(payload) == 8:
            try:
                metadata["device_clock"] = datetime.fromtimestamp(
                    struct.unpack("<Q", payload)[0], UTC
                ).isoformat()
            except ValueError, OverflowError, OSError:
                return
        elif (packet.function, packet.register) == (4, 2) and len(payload) == 1:
            offset = struct.unpack("b", payload)[0]
            if not -24 <= offset <= 28:
                return
            metadata["timezone"] = offset / 2
        else:
            return
        self._update(metadata=metadata)
        self.store.async_delay_save(self._stored_data, 1)
        if "firmware" in metadata:
            registry = dr.async_get(self.hass)
            if device := registry.async_get_device(identifiers={(DOMAIN, self.address)}):
                if device.sw_version != metadata["firmware"]:
                    registry.async_update_device(device.id, sw_version=metadata["firmware"])

    def _stored_data(self) -> dict[str, Any]:
        return {
            "seen": self.seen,
            "sample": self.data["sample"],
            "metadata": self.data["metadata"],
            **{key: self.data[key] for key in ("last_error", "last_result") if key in self.data},
        }

    async def command(self, command: str, value: float | None = None) -> None:
        if not self.data["connected"]:
            raise HomeAssistantError("Wake the R2 PP and wait for it to connect")
        try:
            if command == "measure":
                if self.measurement_pending and self.hass.loop.time() < self.measurement_deadline:
                    raise HomeAssistantError("The instrument is already measuring or calibrating")
                self.measurement_pending = True
                self.measurement_deadline = self.hass.loop.time() + 60
                try:
                    response = await self.client.request(3, 0, response=(3, 9))
                    if response.payload != bytes.fromhex("0000000001000000"):
                        raise HomeAssistantError("Instrument did not accept the command")
                except BaseException:
                    self.measurement_pending = False
                    raise
            elif command == "sync_clock":
                await self.client.request(
                    4, 1, struct.pack("<Q", int(dt_util.utcnow().timestamp()))
                )
                reply = await self.client.request(4, 1)
                if (
                    len(reply.payload) != 8
                    or abs(struct.unpack("<Q", reply.payload)[0] - dt_util.utcnow().timestamp()) > 5
                ):
                    raise HomeAssistantError(
                        "Device clock readback did not confirm synchronization"
                    )
            elif command == "timezone" and value is not None:
                if (
                    not math.isfinite(value)
                    or not -12 <= value <= 14
                    or value * 2 != int(value * 2)
                ):
                    raise HomeAssistantError("Timezone must be -12 to +14 in half-hour increments")
                await self.client.request(4, 2, struct.pack("b", round(value * 2)))
                reply = await self.client.request(4, 2)
                if reply.payload != struct.pack("b", round(value * 2)):
                    raise HomeAssistantError(
                        "Device timezone readback did not match the requested offset"
                    )
            elif command == "refresh":
                await self.refresh_metadata()
        except (BleakError, TimeoutError, OSError) as err:
            raise HomeAssistantError(f"DiFluid command failed: {err}") from err

    async def stop(self) -> None:
        if self.stopped:
            return
        self.stopped = True
        if self.unsubscribe:
            self.unsubscribe()
        if self.task:
            self.task.cancel()
            with suppress(asyncio.CancelledError):
                await self.task
        with suppress(BleakError, TimeoutError, OSError):
            await self.client.disconnect()
        await self.store.async_save(self._stored_data())
