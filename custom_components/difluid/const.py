"""Verified R2 PP protocol constants."""

from homeassistant.const import Platform

DOMAIN = "difluid"
SERVICE_UUID = "0000a0ff-0000-1000-8000-00805f9b34fb"
CHAR_UUID = "0000ff01-0000-1000-8000-00805f9b34fb"
PLATFORMS = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.EVENT,
    Platform.BUTTON,
    Platform.NUMBER,
]
