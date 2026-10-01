"""Discover verified PP advertisements without sending measurement commands."""

from typing import Any

import voluptuous as vol
from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_ADDRESS

from .const import DOMAIN, SERVICE_UUID


class DiFluidConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self.address: str | None = None
        self.name = "DiFluid R2 PP"

    async def async_step_bluetooth(
        self, discovery_info: bluetooth.BluetoothServiceInfoBleak
    ) -> ConfigFlowResult:
        if (
            not (discovery_info.name or "").startswith("R2 PP ")
            or SERVICE_UUID not in discovery_info.service_uuids
        ):
            return self.async_abort(reason="not_supported")
        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()
        self.address = discovery_info.address
        self.name = discovery_info.name
        self.context["title_placeholders"] = {"name": self.name}
        return await self.async_step_confirm()

    async def async_step_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(title=self.name, data={CONF_ADDRESS: self.address})
        return self.async_show_form(step_id="confirm", description_placeholders={"name": self.name})

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        devices = {
            info.address: f"{info.name} ({info.address})"
            for info in bluetooth.async_discovered_service_info(self.hass, connectable=True)
            if (info.name or "").startswith("R2 PP ")
            and SERVICE_UUID in info.service_uuids
            and info.address not in self._async_current_ids()
        }
        if user_input is not None:
            address = user_input[CONF_ADDRESS]
            if address in devices:
                await self.async_set_unique_id(address)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=devices[address].split(" (")[0], data={CONF_ADDRESS: address}
                )
        if not devices:
            return self.async_abort(reason="no_devices_found")
        return self.async_show_form(
            step_id="user", data_schema=vol.Schema({vol.Required(CONF_ADDRESS): vol.In(devices)})
        )
