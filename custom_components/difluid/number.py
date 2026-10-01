"""Device timezone setting, exposed only after a valid response."""

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import DiFluidConfigEntry
from .entity import DiFluidControl


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DiFluidConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    added = False

    @callback
    def discover() -> None:
        nonlocal added
        if not added and "timezone" in entry.runtime_data.data["metadata"]:
            added = True
            async_add_entities([DiFluidTimezone(entry.runtime_data, "timezone")])

    entry.async_on_unload(entry.runtime_data.async_add_listener(discover))
    discover()


class DiFluidTimezone(DiFluidControl, NumberEntity):
    _attr_name = "Timezone offset"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_entity_registry_enabled_default = False
    _attr_native_min_value = -12
    _attr_native_max_value = 14
    _attr_native_step = 0.5
    _attr_native_unit_of_measurement = "h"
    _attr_mode = NumberMode.BOX
    _attr_icon = "mdi:map-clock"

    @property
    def native_value(self) -> float | None:
        value = self.coordinator.data["metadata"].get("timezone")
        return float(value) if value is not None else None

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.command("timezone", value)
