"""R2 PP encrypted framing, validated against real FF01 notifications.

The level-one key is a public protocol constant in the manufacturer's client,
not a user credential. No app, account, or network handshake is required.
"""

import struct
from dataclasses import dataclass

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

_KEY = bytes.fromhex("00102030405060708090a0b0c0d0e0f0")
_IV = bytes(range(16))
_START = b"\xda\xda"
_END = b"\x0a\x0a"
_ESCAPE = 0xFA
_RESERVED = (0xDA, 0x0A, _ESCAPE)
MAX_FRAME_SIZE = 4096


def crc16(data: bytes) -> int:
    """CRC-16/MODBUS used for the decrypted header and payload."""
    crc = 0xFFFF
    for value in data:
        crc ^= value
        for _ in range(8):
            crc = (crc >> 1) ^ (0xA001 if crc & 1 else 0)
    return crc


@dataclass(frozen=True, slots=True)
class Packet:
    """Validated protocol packet; register is little endian on the wire."""

    address: int
    function: int
    register: int
    payload: bytes


def encode(function: int, register: int, payload: bytes = b"") -> bytes:
    """Encode an explicitly requested device command with level-one encryption."""
    if len(payload) > 1024:
        raise ValueError("Command payload too large")
    plain = struct.pack("<BBHH", 0, function, register, len(payload)) + payload
    plain += struct.pack("<H", crc16(plain))
    # The vendor client zero-fills to eight bytes, then uses AES PKCS7 padding.
    plain += b"\0" * (-len(plain) % 8)
    padding = 16 - len(plain) % 16
    plain += bytes([padding]) * padding
    encryptor = Cipher(algorithms.AES(_KEY), modes.CBC(_IV)).encryptor()
    body = encryptor.update(plain) + encryptor.finalize() + b"\x01"
    body += bytes([sum(body) & 0xFF])
    escaped = bytearray()
    for value in body:
        if value in _RESERVED:
            escaped.append(_ESCAPE)
        escaped.append(value)
    return _START + escaped + _END


def decode(raw: bytes) -> Packet:
    """Validate escaping, outer checksum, encryption, length, and inner CRC."""
    if not raw.startswith(_START) or not raw.endswith(_END):
        raise ValueError("Invalid frame delimiters")
    body = bytearray()
    escape = False
    for value in raw[2:-2]:
        if escape:
            if value not in _RESERVED:
                raise ValueError("Invalid escaped byte")
            body.append(value)
            escape = False
        elif value == _ESCAPE:
            escape = True
        elif value in _RESERVED:
            raise ValueError("Unescaped reserved byte")
        else:
            body.append(value)
    if escape or len(body) < 18:
        raise ValueError("Incomplete frame")
    if sum(body[:-1]) & 0xFF != body[-1]:
        raise ValueError("Invalid frame checksum")
    if body[-2] & 3 != 1:
        raise ValueError("Unsupported encryption level")
    ciphertext = bytes(body[:-2])
    if len(ciphertext) % 16:
        raise ValueError("Invalid ciphertext length")
    decryptor = Cipher(algorithms.AES(_KEY), modes.CBC(_IV)).decryptor()
    plain = decryptor.update(ciphertext) + decryptor.finalize()
    address, function, register, length = struct.unpack_from("<BBHH", plain)
    end = 6 + length
    if end + 2 > len(plain):
        raise ValueError("Invalid payload length")
    if crc16(plain[:end]) != struct.unpack_from("<H", plain, end)[0]:
        raise ValueError("Invalid payload CRC")
    return Packet(address, function, register, plain[6:end])


class Decoder:
    """Bounded stream reassembly independent of BLE packet boundaries."""

    def __init__(self) -> None:
        self._buffer = bytearray()
        self.errors = 0

    def reset(self) -> None:
        self._buffer.clear()

    def feed(self, data: bytes) -> list[Packet]:
        self._buffer.extend(data)
        packets: list[Packet] = []
        while self._buffer:
            start = self._buffer.find(_START)
            if start < 0:
                self._buffer[:] = b"\xda" if self._buffer[-1] == 0xDA else b""
                break
            del self._buffer[:start]
            # An escaped final 0A followed by the terminator is FA 0A 0A 0A.
            # Searching for 0A 0A directly would cut that valid frame short.
            end = next_start = -1
            index = 2
            while index + 1 < len(self._buffer):
                if self._buffer[index] == _ESCAPE:
                    index += 2
                    continue
                if self._buffer[index : index + 2] == _END:
                    end = index
                    break
                if self._buffer[index : index + 2] == _START:
                    next_start = index
                    break
                index += 1
            if next_start >= 0 and (end < 0 or next_start < end):
                del self._buffer[:next_start]
                self.errors += 1
                continue
            if end < 0:
                if len(self._buffer) > MAX_FRAME_SIZE:
                    self.reset()
                    self.errors += 1
                break
            raw = bytes(self._buffer[: end + 2])
            del self._buffer[: end + 2]
            if len(raw) > MAX_FRAME_SIZE:
                self.errors += 1
                continue
            try:
                packets.append(decode(raw))
            except ValueError:
                self.errors += 1
        return packets
