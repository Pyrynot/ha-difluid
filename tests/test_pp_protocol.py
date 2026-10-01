"""Hardware fixtures, malformed frames, and BLE stream boundaries."""

import json
import struct
from pathlib import Path

import pytest

from custom_components.difluid.protocol.codec import Decoder, Packet, decode, encode
from custom_components.difluid.protocol.measurement import parse_measurement

FIXTURE = json.loads((Path(__file__).parent / "fixtures/r2_pp/measurements.json").read_text())
STREAM = b"".join(bytes.fromhex(value) for value in FIXTURE["notifications"])


def test_hardware_values():
    measurements = [parse_measurement(p) for p in Decoder().feed(STREAM)]
    assert [m.values["det_result"] for m in measurements] == [11, 0, 11, 0]
    completed = [m for m in measurements if m.successful]
    assert len(completed) == 2
    for measurement, displayed in zip(completed, FIXTURE["displayed"], strict=True):
        assert measurement.values["concentration_model_display0"] == pytest.approx(
            displayed["brix"], abs=0.001
        )
        assert measurement.values["temperature_prism"] == pytest.approx(
            displayed["temperature"], abs=0.05
        )
        assert measurement.values["refra_real_liquid"] == pytest.approx(
            displayed["refractive_index"], abs=0.00005
        )


@pytest.mark.parametrize("width", [1, 2, 7, 20, 128, 512])
def test_fragmentation(width):
    decoder = Decoder()
    actual = []
    for offset in range(0, len(STREAM), width):
        actual.extend(decoder.feed(STREAM[offset : offset + width]))
    assert actual == Decoder().feed(STREAM)
    assert decoder.errors == 0


def test_every_split():
    for offset in range(len(STREAM)):
        decoder = Decoder()
        assert decoder.feed(STREAM[:offset]) + decoder.feed(STREAM[offset:]) == Decoder().feed(
            STREAM
        )


def test_corruption_resync_and_bounded_buffer():
    decoder = Decoder()
    corrupt = bytearray(STREAM[:136])
    corrupt[7] ^= 1
    assert decoder.feed(bytes(corrupt) + STREAM) == Decoder().feed(STREAM)
    assert decoder.errors
    assert decoder.feed(b"\xda\xda" + b"x" * 5000) == []
    assert len(decoder._buffer) <= 4096
    assert decoder.feed(STREAM) == Decoder().feed(STREAM)


@pytest.mark.parametrize("payload", [b"", b"\xda\x0a\xfa", bytes(range(256))])
def test_command_encoding(payload):
    assert decode(encode(4, 1, payload)) == Packet(0, 4, 1, payload)


def test_status_errors_and_calibration_never_samples():
    packet = Decoder().feed(STREAM)[1]
    for status, error, register in ((11, 0, 6), (12, 0, 6), (0, 2, 6), (1, 0, 3), (0, 0, 3)):
        payload = bytearray(packet.payload)
        payload[71:73] = bytes([status, error])
        assert not parse_measurement(Packet(0, 3, register, bytes(payload))).successful


def test_identical_values_at_new_time_are_distinct():
    packet = Decoder().feed(STREAM)[1]
    payload = bytearray(packet.payload)
    struct.pack_into("<Q", payload, 0, struct.unpack_from("<Q", payload)[0] + 1)
    assert (
        parse_measurement(packet).identity
        != parse_measurement(Packet(0, 3, 6, bytes(payload))).identity
    )


def test_unknown_layout_rejected():
    with pytest.raises(ValueError, match="size"):
        parse_measurement(Packet(0, 3, 6, b"x" * 117))


def test_escaped_terminal_bytes_and_all_command_registers():
    # In particular exercise an escaped checksum 0A directly before 0A0A.
    stream = b"".join(encode(4, register) for register in range(512))
    decoder = Decoder()
    packets = decoder.feed(stream)
    assert len(packets) == 512
    assert decoder.errors == 0
    assert [packet.register for packet in packets] == list(range(512))
