"""One recorder-friendly event for each distinct completed measurement."""

from typing import Any

from homeassistant.components.event import EventEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import DiFluidConfigEntry
from .entity import DiFluidEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DiFluidConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([DiFluidMeasurementEvent(entry.runtime_data, "measurement")])


class DiFluidMeasurementEvent(DiFluidEntity, EventEntity):
    _attr_name = "Measurement"
    _attr_event_types = ["measurement"]
    _attr_icon = "mdi:eyedropper"

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.coordinator.sample_listeners.append(self._sample)
        self.async_on_remove(lambda: self.coordinator.sample_listeners.remove(self._sample))

    @callback
    def _sample(self, sample: dict[str, Any]) -> None:
        values = sample["values"]
        self._trigger_event(
            "measurement",
            {
                "measurement_id": sample["id"],
                "device_time": sample["device_time"],
                "received_at": sample["received_at"],
                "brix": values["concentration_model_display0"],
                "temperature": values["temperature_prism"],
                "refractive_index": round(values["refra_real_liquid"], 5),
                "battery": values["bat_power"],
            },
        )
        self.async_write_ha_state()
