"""Observe HA Bluetooth discoveries. Read an API token from stdin, never log it."""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import time

import aiohttp


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://supervisor/core/api/websocket")
    parser.add_argument("--seconds", type=int, default=600)
    parser.add_argument("--match", default=r"difluid|^r2[ _-]|^dft[ _-]")
    args = parser.parse_args()
    token = sys.stdin.read().strip()
    pattern = re.compile(args.match, re.IGNORECASE)
    async with aiohttp.ClientSession() as session:
        async with session.ws_connect(args.url, headers={"Authorization": f"Bearer {token}"}) as ws:
            await ws.receive_json()
            await ws.send_json({"type": "auth", "access_token": token})
            if (await ws.receive_json()).get("type") != "auth_ok":
                raise RuntimeError("HA authentication failed")
            await ws.send_json({"id": 1, "type": "bluetooth/subscribe_advertisements"})
            print(json.dumps({"status": "listening", "time": time.time()}), flush=True)
            end = time.monotonic() + args.seconds
            while time.monotonic() < end:
                try:
                    msg = await ws.receive_json(timeout=min(10, end - time.monotonic()))
                except TimeoutError:
                    continue
                if msg.get("type") != "event":
                    if msg.get("success") is False:
                        raise RuntimeError(msg.get("error"))
                    continue
                for adv in msg["event"].get("add", []):
                    if pattern.search(adv.get("name", "")):
                        print(json.dumps(adv), flush=True)


if __name__ == "__main__":
    asyncio.run(main())
