from unittest.mock import patch

from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData
from homeassistant.components.bluetooth import BluetoothServiceInfoBleak
from homeassistant.config_entries import SOURCE_BLUETOOTH, SOURCE_USER

from custom_components.difluid.const import SERVICE_UUID

ADDRESS = "AA:BB:CC:DD:EE:FF"


def info(name="R2 PP Test"):
    return BluetoothServiceInfoBleak(
        name=name,
        address=ADDRESS,
        rssi=-70,
        manufacturer_data={},
        service_data={},
        service_uuids=[SERVICE_UUID],
        source="local",
        device=BLEDevice(ADDRESS, name, {}),
        advertisement=AdvertisementData(name, {}, {}, [SERVICE_UUID], None, -70, ()),
        connectable=True,
        time=0,
        tx_power=None,
    )


async def test_discover_confirm_duplicate(hass, mock_bluetooth):
    result = await hass.config_entries.flow.async_init(
        "difluid", context={"source": SOURCE_BLUETOOTH}, data=info()
    )
    assert result["type"] == "form"
    assert result["step_id"] == "confirm"
    with patch("custom_components.difluid.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
        await hass.async_block_till_done()
    assert result["type"] == "create_entry"
    assert result["data"] == {"address": ADDRESS}
    result = await hass.config_entries.flow.async_init(
        "difluid", context={"source": SOURCE_BLUETOOTH}, data=info()
    )
    assert result["reason"] == "already_configured"


async def test_reject_extract(hass, mock_bluetooth):
    result = await hass.config_entries.flow.async_init(
        "difluid", context={"source": SOURCE_BLUETOOTH}, data=info("R2 Extract")
    )
    assert result["reason"] == "not_supported"


async def test_user_empty_and_selection(hass, mock_bluetooth):
    with patch(
        "custom_components.difluid.config_flow.bluetooth.async_discovered_service_info",
        return_value=[],
    ):
        result = await hass.config_entries.flow.async_init(
            "difluid", context={"source": SOURCE_USER}
        )
    assert result["reason"] == "no_devices_found"
    with patch(
        "custom_components.difluid.config_flow.bluetooth.async_discovered_service_info",
        return_value=[info()],
    ):
        result = await hass.config_entries.flow.async_init(
            "difluid", context={"source": SOURCE_USER}
        )
        assert result["step_id"] == "user"
        with patch("custom_components.difluid.async_setup_entry", return_value=True):
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"], {"address": ADDRESS}
            )
            await hass.async_block_till_done()
        assert result["type"] == "create_entry"
