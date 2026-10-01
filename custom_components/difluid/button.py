"""Explicit instrument actions, never sent automatically on discovery."""

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import DiFluidConfigEntry
from .coordinator import DiFluidCoordinator
from .entity import DiFluidControl

DESCRIPTIONS = [
    ButtonEntityDescription(key="measure", name="Measure", icon="mdi:eyedropper"),
    ButtonEntityDescription(
        key="sync_clock",
        name="Synchronize clock",
        icon="mdi:clock-check-outline",
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
    ),
    ButtonEntityDescription(
        key="refresh",
        name="Refresh device information",
        icon="mdi:refresh",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DiFluidConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities(
        [DiFluidButton(entry.runtime_data, description) for description in DESCRIPTIONS]
    )


class DiFluidButton(DiFluidControl, ButtonEntity):
    def __init__(
        self, coordinator: DiFluidCoordinator, description: ButtonEntityDescription
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    async def async_press(self) -> None:
        await self.coordinator.command(self.entity_description.key)
