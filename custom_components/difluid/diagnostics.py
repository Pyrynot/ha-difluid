"""Diagnostics omit addresses, serial numbers, samples, and raw packets."""

from typing import Any

from homeassistant.core import HomeAssistant

from . import DiFluidConfigEntry


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: DiFluidConfigEntry
) -> dict[str, Any]:
    coordinator = entry.runtime_data
    return {
        "model": "R2 PP",
        "metadata": coordinator.data["metadata"],
        "connected": coordinator.data["connected"],
        "status": coordinator.data["status"],
        "decoder_errors": coordinator.client.decoder.errors,
        "has_measurement": coordinator.data["sample"] is not None,
    }
