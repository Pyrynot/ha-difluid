"""Shared device identity and push updates."""

from homeassistant.helpers.device_registry import CONNECTION_BLUETOOTH, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import DiFluidCoordinator


class DiFluidEntity(CoordinatorEntity[DiFluidCoordinator]):
    _attr_has_entity_name = True

    def __init__(self, coordinator: DiFluidCoordinator, key: str) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.address}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.address)},
            connections={(CONNECTION_BLUETOOTH, coordinator.address)},
            manufacturer="DiFluid",
            model="R2 PP",
            name=coordinator.entry.title,
        )

    @property
    def available(self) -> bool:
        return True


class DiFluidControl(DiFluidEntity):
    @property
    def available(self) -> bool:
        return bool(self.coordinator.data["connected"])
