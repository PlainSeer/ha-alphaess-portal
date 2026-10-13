"""Discharge settings; changes apply to the next start/renewal command."""
from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.const import EntityCategory
from .entity import PortalEntity

SETTINGS = [('power_w', 'Discharge power', 100, 30000, 100, 'W', 'mdi:flash'), ('target_soc', 'Target state of charge', 5, 100, 1, '%', 'mdi:battery-low'), ('duration_minutes', 'Discharge duration', 1, 180, 1, 'min', 'mdi:timer-outline'), ('charge_power_w', 'Test charge power', 100, 7000, 100, 'W', 'mdi:battery-arrow-up'), ('charge_target_soc', 'Test charge target SoC', 5, 100, 1, '%', 'mdi:battery-charging'), ('charge_duration_minutes', 'Test charge duration', 1, 180, 1, 'min', 'mdi:timer-outline')]

async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([DischargeSetting(entry.runtime_data, setting) for setting in SETTINGS])

class DischargeSetting(PortalEntity, NumberEntity):
    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG
    _attr_mode = NumberMode.BOX

    def __init__(self, coordinator, setting):
        super().__init__(coordinator)
        self.key, self._attr_name, self._attr_native_min_value, self._attr_native_max_value, self._attr_native_step, self._attr_native_unit_of_measurement, self._attr_icon = setting
        self._attr_unique_id = f"alphaess_portal_{coordinator.entry.data['serial']}_{self.key}"

    @property
    def available(self):
        # These values are local HA options, not cloud telemetry.
        return True

    @property
    def native_value(self):
        return self.coordinator.setting(self.key)

    async def async_set_native_value(self, value):
        self.hass.config_entries.async_update_entry(self.coordinator.entry, options={**self.coordinator.entry.options, self.key: int(value)})
