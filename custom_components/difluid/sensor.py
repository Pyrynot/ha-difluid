"""Create result and diagnostic sensors from decoded device fields."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorEntityDescription
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import DiFluidConfigEntry
from .coordinator import DiFluidCoordinator
from .entity import DiFluidEntity
from .protocol.measurement import FIELDS


@dataclass(frozen=True, kw_only=True)
class Description(SensorEntityDescription):
    source: str = "values"


_MAIN = {
    "concentration_model_display0": Description(
        key="concentration_model_display0",
        name="Brix",
        native_unit_of_measurement="°Bx",
        suggested_display_precision=1,
        icon="mdi:water-percent",
    ),
    "temperature_prism": Description(
        key="temperature_prism",
        name="Sample temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        suggested_display_precision=1,
    ),
    "refra_real_liquid": Description(
        key="refra_real_liquid",
        name="Refractive index",
        suggested_display_precision=5,
        icon="mdi:water",
    ),
    "bat_power": Description(
        key="bat_power",
        name="Battery",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.BATTERY,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
}
# Device-reported internal fields are opt-in diagnostics, without invented units.
DESCRIPTIONS = [
    _MAIN.get(key)
    or Description(
        key=key,
        name=key.replace("_", " ").capitalize(),
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    )
    for key, _ in FIELDS
    if key != "timestamp"
] + [
    Description(
        key="received_at",
        name="Last measurement",
        source="sample",
        device_class=SensorDeviceClass.TIMESTAMP,
    ),
    Description(
        key="device_time",
        name="Measurement device time",
        source="sample",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    Description(
        key="status", name="Status", source="root", entity_category=EntityCategory.DIAGNOSTIC
    ),
    Description(
        key="last_error",
        name="Last error code",
        source="root",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    *[
        Description(
            key=key, name=name, source="metadata", entity_category=EntityCategory.DIAGNOSTIC
        )
        for key, name in (
            ("firmware", "Firmware"),
            ("profile_index", "Profile index"),
            ("profile_name", "Profile"),
            ("profile_unit", "Profile unit"),
        )
    ],
    Description(
        key="device_clock",
        name="Device clock",
        source="metadata",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DiFluidConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    added: set[str] = set()

    @callback
    def discover() -> None:
        entities = []
        for description in DESCRIPTIONS:
            source = (
                coordinator.data
                if description.source == "root"
                else coordinator.data.get(description.source) or {}
            )
            if description.key not in added and description.key in source:
                added.add(description.key)
                entities.append(DiFluidSensor(coordinator, description))
        if entities:
            async_add_entities(entities)

    entry.async_on_unload(coordinator.async_add_listener(discover))
    discover()


class DiFluidSensor(DiFluidEntity, SensorEntity):
    entity_description: Description

    def __init__(self, coordinator: DiFluidCoordinator, description: Description) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> str | int | float | datetime | None:
        description = self.entity_description
        source = (
            self.coordinator.data
            if description.source == "root"
            else self.coordinator.data.get(description.source) or {}
        )
        value = source.get(description.key)
        if value is not None and description.device_class == SensorDeviceClass.TIMESTAMP:
            return datetime.fromisoformat(value)
        if description.key in ("refra_real_liquid", "refra_display") and value is not None:
            return round(float(value), 5)
        return value if isinstance(value, (str, int, float)) else None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self.entity_description.source != "values":
            return None
        sample = self.coordinator.data["sample"]
        return {"measurement_id": sample["id"]} if sample else None
