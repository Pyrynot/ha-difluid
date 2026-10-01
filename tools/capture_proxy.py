"""Development-only GATT capture through an existing ESPHome proxy.

Run inside the HA container with access to core.config_entries. Credentials are
read locally and never printed. Commands require an explicit private command file.
Raw captures contain device identifiers: keep them outside the repository.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
from pathlib import Path

from aioesphomeapi import APIClient


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--entry-id", required=True)
    parser.add_argument("--address", required=True)
    parser.add_argument("--seconds", type=int, default=1800)
    parser.add_argument("--output", required=True)
    parser.add_argument(
        "--commands", help="Private JSONL requests: read/write/stop; no implicit writes"
    )
    args = parser.parse_args()
    address = int(args.address.replace(":", ""), 16)
    entries = json.loads(
        await asyncio.to_thread(Path("/config/.storage/core.config_entries").read_text)
    )
    entry = next(e for e in entries["data"]["entries"] if e["entry_id"] == args.entry_id)
    if entry["domain"] != "esphome":
        raise ValueError("Entry must be an ESPHome proxy")
    data = entry["data"]
    client = APIClient(
        data["host"],
        data.get("port", 6053),
        password=data.get("password", ""),
        noise_psk=data.get("noise_psk"),
        client_info="DiFluid protocol capture",
    )
    fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as output:

        def emit(kind: str, **fields: object) -> None:
            line = json.dumps(
                {"kind": kind, "time": time.time(), "monotonic": time.monotonic(), **fields}
            )
            print(line, flush=True)
            output.write(line + "\n")
            output.flush()

        await client.connect(login=True)
        connected = False
        stops = []
        stop_ads = None
        stop_connection = None
        try:
            info = await client.device_info()
            emit("proxy", name=info.name, flags=info.bluetooth_proxy_feature_flags)
            found = asyncio.get_running_loop().create_future()

            def advertisement(batch: object) -> None:
                for adv in batch.advertisements:
                    if adv.address == address and not found.done():
                        found.set_result(adv)

            stop_ads = client.subscribe_bluetooth_le_raw_advertisements(advertisement)
            emit(
                "waiting",
                message="Waiting for a fresh advertisement from the powered-on instrument",
            )
            adv = await asyncio.wait_for(found, 600)
            emit(
                "advertisement", address=args.address, address_type=adv.address_type, rssi=adv.rssi
            )

            def connection_changed(is_connected: bool, mtu: int, error: int) -> None:
                nonlocal connected
                connected = is_connected
                emit("connection", connected=is_connected, mtu=mtu, error=error)

            stop_connection = await client.bluetooth_device_connect(
                address,
                connection_changed,
                feature_flags=info.bluetooth_proxy_feature_flags,
                address_type=adv.address_type,
            )
            services = await client.bluetooth_gatt_get_services(address)
            for service in services.services:
                emit("service", uuid=service.uuid, handle=service.handle)
                for char in service.characteristics:
                    emit(
                        "characteristic",
                        uuid=char.uuid,
                        handle=char.handle,
                        properties=char.properties,
                        descriptors=[
                            {"uuid": d.uuid, "handle": d.handle} for d in char.descriptors
                        ],
                    )
                    if char.properties & 0x30:
                        stop, remove = await client.bluetooth_gatt_start_notify(
                            address,
                            char.handle,
                            lambda handle, value: emit(
                                "notify", handle=handle, hex=bytes(value).hex()
                            ),
                        )
                        stops.append((stop, remove))
                        for descriptor in char.descriptors:
                            if descriptor.uuid == "00002902-0000-1000-8000-00805f9b34fb":
                                value = b"\x01\x00" if char.properties & 0x10 else b"\x02\x00"
                                await client.bluetooth_gatt_write_descriptor(
                                    address, descriptor.handle, value
                                )
                                actual = await client.bluetooth_gatt_read(
                                    address, descriptor.handle
                                )
                                if bytes(actual) != value:
                                    raise RuntimeError(
                                        "Peripheral notification descriptor was not enabled"
                                    )
                                emit("cccd_enabled", handle=descriptor.handle, hex=value.hex())
                        emit("subscribed", handle=char.handle, uuid=char.uuid)
            emit(
                "ready",
                message="Notification subscriptions active; physical TEST can now be captured",
            )
            offset = 0
            end = time.monotonic() + args.seconds
            while time.monotonic() < end:
                if args.commands:

                    def read_commands() -> list[str]:
                        nonlocal offset
                        try:
                            with open(args.commands) as stream:
                                stream.seek(offset)
                                lines = stream.readlines()
                                offset = stream.tell()
                                return lines
                        except FileNotFoundError:
                            return []

                    for line in await asyncio.to_thread(read_commands):
                        command = json.loads(line)
                        operation = command["operation"]
                        if operation == "stop":
                            return
                        try:
                            if operation == "read":
                                result = await client.bluetooth_gatt_read(
                                    address, command["handle"]
                                )
                                emit("read", handle=command["handle"], hex=bytes(result).hex())
                            elif operation == "write":
                                payload = bytes.fromhex(command["hex"])
                                emit("write", handle=command["handle"], hex=payload.hex())
                                await client.bluetooth_gatt_write(
                                    address, command["handle"], payload, response=True
                                )
                                emit("write_ack", handle=command["handle"])
                            else:
                                raise ValueError("Unknown operation")
                        except Exception as error:
                            emit("command_error", error=str(error), operation=operation)
                await asyncio.sleep(0.25)
        finally:
            for stop, remove in stops:
                if connected:
                    await stop()
                remove()
            if connected:
                await client.bluetooth_device_disconnect(address)
            if stop_connection:
                stop_connection()
            if stop_ads:
                stop_ads()
            await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
