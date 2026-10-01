"""R2 PP 120-byte measurement records; field names follow device semantics."""

import math
import struct
from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha256
from types import MappingProxyType

from .codec import Packet

FIELDS: tuple[tuple[str, str], ...] = (
    ("timestamp", "Q"),
    ("temperature_chip", "f"),
    ("temperature_prism", "f"),
    ("temperature_tank", "f"),
    ("concentration_display", "f"),
    ("concentration_real_liquid", "f"),
    ("concentration_model_display0", "f"),
    ("concentration_model_display1", "f"),
    ("refra_display", "f"),
    ("refra_real_liquid", "f"),
    ("led_pwm", "B"),
    ("exp_time", "B"),
    ("bat_power", "B"),
    ("xvar_0", "f"),
    ("xvar_1", "f"),
    ("x_pos_0", "f"),
    ("y_pos_0", "f"),
    ("x_pos_1", "f"),
    ("y_pos_1", "f"),
    ("det_result", "B"),
    ("det_error_code", "B"),
    ("det_model_type", "B"),
    ("time_adjust_light", "H"),
    ("time_detect", "H"),
    ("light_posx", "H"),
    ("status_flag", "B"),
    ("interge_count", "B"),
    ("pic_fail_count", "B"),
    ("init_led_pwm", "B"),
    ("init_exp_time", "B"),
    ("concentraction_correct", "f"),
)
_STRUCT = struct.Struct("<" + "".join(kind for _, kind in FIELDS))


@dataclass(frozen=True, slots=True)
class Measurement:
    """A measurement/status record; only successful records become sample events."""

    values: Mapping[str, int | float]
    register: int
    fingerprint: str

    @property
    def successful(self) -> bool:
        return (
            self.register != 3
            and self.values["det_result"] == 0
            and self.values["det_error_code"] == 0
            and self.values["timestamp"] > 0
        )

    @property
    def identity(self) -> str:
        return f"{int(self.values['timestamp'])}:{self.fingerprint}"


def parse_measurement(packet: Packet) -> Measurement | None:
    if packet.function != 3 or packet.register not in (0, 3, 6):
        return None
    if len(packet.payload) != 120:
        raise ValueError(f"Unsupported measurement size {len(packet.payload)}")
    # V025's tail differs from the vendor app's generic PU field map. Preserve
    # those bytes in the fingerprint, but do not assign unverified meanings.
    values = dict(
        zip((name for name, _ in FIELDS), _STRUCT.unpack_from(packet.payload), strict=True)
    )
    if any(isinstance(value, float) and not math.isfinite(value) for value in values.values()):
        raise ValueError("Non-finite measurement field")
    return Measurement(
        MappingProxyType(values), packet.register, sha256(packet.payload).hexdigest()[:16]
    )
