"""Manual, experimental private-portal charging test controls.

Never sends commands at setup, polling, or settings changes.
"""
from aiohttp import ClientError
from homeassistant.components.button import ButtonEntity
from homeassistant.exceptions import HomeAssistantError
from .entity import PortalEntity


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([
        TestChargeStartButton(entry.runtime_data),
        TestChargeStopButton(entry.runtime_data),
    ])


class TestChargeStartButton(PortalEntity, ButtonEntity):
    _attr_name = "TEST Start Portal Charge"
    _attr_icon = "mdi:battery-arrow-up"

    def __init__(self, coordinator):
        super().__init__(coordinator)
        self._attr_unique_id = f"alphaess_portal_{coordinator.entry.data['serial']}_test_charge_start"

    async def async_press(self):
        try:
            await self.coordinator.client.charge(
                power=self.coordinator.setting("charge_power_w"),
                target_soc=self.coordinator.setting("charge_target_soc"),
                duration=self.coordinator.setting("charge_duration_minutes"),
            )
        except (RuntimeError, ClientError, TimeoutError) as exc:
            raise HomeAssistantError("Experimental AlphaESS portal charge request failed") from exc
        self.coordinator.command_sent()
        await self.coordinator.async_request_refresh()


class TestChargeStopButton(PortalEntity, ButtonEntity):
    _attr_name = "TEST Stop Portal Charge (Standby)"
    _attr_icon = "mdi:stop-circle-outline"

    def __init__(self, coordinator):
        super().__init__(coordinator)
        self._attr_unique_id = f"alphaess_portal_{coordinator.entry.data['serial']}_test_charge_stop"

    async def async_press(self):
        # Same Standby request as the existing discharge stop.
        try:
            await self.coordinator.client.stop()
        except (RuntimeError, ClientError, TimeoutError) as exc:
            raise HomeAssistantError("AlphaESS portal Standby request failed") from exc
        self.coordinator.command_sent()
        await self.coordinator.async_request_refresh()
