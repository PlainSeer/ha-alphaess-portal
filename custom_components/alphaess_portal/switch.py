"""Force discharge for the configured portal discharge duration."""
from aiohttp import ClientError
from homeassistant.components.switch import SwitchEntity
from homeassistant.exceptions import HomeAssistantError
from .entity import PortalEntity

async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([DischargeSwitch(entry.runtime_data), ChargeSwitch(entry.runtime_data)])

class DischargeSwitch(PortalEntity, SwitchEntity):
    _attr_name = 'AlphaESS Portal Force Discharge'
    _attr_icon = 'mdi:battery-arrow-down'

    def __init__(self, coordinator):
        super().__init__(coordinator)
        # Preserve the original switch's identity and existing automations.
        self._attr_unique_id = 'alphaess_portal_' + coordinator.entry.data['serial'] + '_force_discharge'

    @property
    def is_on(self):
        return (self.power.get('dispatch') or {}).get('source') == 'IMMEDIATE_DISCHARGE'

    @property
    def available(self):
        return super().available and self.coordinator.data.get('status') == 'Normal'

    @property
    def extra_state_attributes(self):
        dispatch = self.power.get('dispatch') or {}
        return {'dispatch_source': dispatch.get('source'), 'power_limit_kw': dispatch.get('powerLimitKw'), 'requested_power_w': self.coordinator.setting('power_w'), 'target_soc': self.coordinator.setting('target_soc'), 'duration_minutes': self.coordinator.setting('duration_minutes'), 'poll_interval_seconds': self.coordinator.update_interval.total_seconds(), 'last_checked': self.coordinator.last_checked}

    async def async_turn_on(self, **kwargs):
        try:
            await self.coordinator.client.discharge(power=self.coordinator.setting('power_w'), target_soc=self.coordinator.setting('target_soc'), duration=self.coordinator.setting('duration_minutes'))
        except (RuntimeError, ClientError, TimeoutError) as exc:
            raise HomeAssistantError('AlphaESS portal could not start discharge') from exc
        self.coordinator.command_sent()
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs):
        try:
            await self.coordinator.client.stop()
        except (RuntimeError, ClientError, TimeoutError) as exc:
            raise HomeAssistantError('AlphaESS portal could not stop discharge') from exc
        self.coordinator.command_sent()
        await self.coordinator.async_request_refresh()


class ChargeSwitch(PortalEntity, SwitchEntity):
    _attr_name = 'AlphaESS Portal Force Charge'
    _attr_icon = 'mdi:battery-arrow-up'

    def __init__(self, coordinator):
        super().__init__(coordinator)
        self._attr_unique_id = 'alphaess_portal_' + coordinator.entry.data['serial'] + '_force_charge'

    @property
    def is_on(self):
        return (self.power.get('dispatch') or {}).get('source') == 'IMMEDIATE_CHARGE'

    @property
    def available(self):
        return super().available and self.coordinator.data.get('status') == 'Normal'

    @property
    def extra_state_attributes(self):
        dispatch = self.power.get('dispatch') or {}
        return {'dispatch_source': dispatch.get('source'), 'power_limit_kw': dispatch.get('powerLimitKw'), 'requested_power_w': self.coordinator.setting('charge_power_w'), 'target_soc': self.coordinator.setting('charge_target_soc'), 'duration_minutes': self.coordinator.setting('charge_duration_minutes'), 'poll_interval_seconds': self.coordinator.update_interval.total_seconds(), 'last_checked': self.coordinator.last_checked}

    async def async_turn_on(self, **kwargs):
        try:
            await self.coordinator.client.charge(power=self.coordinator.setting('charge_power_w'), target_soc=self.coordinator.setting('charge_target_soc'), duration=self.coordinator.setting('charge_duration_minutes'))
        except (RuntimeError, ClientError, TimeoutError) as exc:
            raise HomeAssistantError('AlphaESS portal could not start charging') from exc
        self.coordinator.command_sent()
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs):
        try:
            await self.coordinator.client.stop()
        except (RuntimeError, ClientError, TimeoutError) as exc:
            raise HomeAssistantError('AlphaESS portal could not stop charging') from exc
        self.coordinator.command_sent()
        await self.coordinator.async_request_refresh()
