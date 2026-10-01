"""Local Bluetooth support for DiFluid instruments."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import Event, HomeAssistant

    from .coordinator import DiFluidCoordinator

type DiFluidConfigEntry = ConfigEntry[DiFluidCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: DiFluidConfigEntry) -> bool:
    from homeassistant.const import EVENT_HOMEASSISTANT_STOP

    from .const import PLATFORMS
    from .coordinator import DiFluidCoordinator

    coordinator = entry.runtime_data = DiFluidCoordinator(hass, entry)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await coordinator.start()

    async def shutdown(_event: Event) -> None:
        await coordinator.stop()

    entry.async_on_unload(hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, shutdown))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: DiFluidConfigEntry) -> bool:
    from .const import PLATFORMS

    if unloaded := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        await entry.runtime_data.stop()
    return unloaded


async def async_remove_entry(hass: HomeAssistant, entry: DiFluidConfigEntry) -> None:
    from homeassistant.helpers.storage import Store

    from .const import DOMAIN

    await Store(hass, 1, f"{DOMAIN}.{entry.entry_id}").async_remove()
