from homeassistant.components.number import NumberMode, RestoreNumber
from homeassistant.const import EntityCategory, UnitOfTime


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([TrendInterval(entry.runtime_data)])


class TrendInterval(RestoreNumber):
    """Minutes between trend signals. Restored across restarts; the beacon reads it as beacon.trend_minutes."""
    _attr_has_entity_name = True
    _attr_translation_key = "trend_every"
    _attr_native_min_value, _attr_native_max_value, _attr_native_step = 1, 60, 1
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_mode = NumberMode.BOX
    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:timer-outline"

    def __init__(self, beacon):
        self.b = beacon
        self._attr_unique_id = f"{beacon.entry.entry_id}_trend_every"
        self._attr_device_info = beacon.device
        self._attr_native_value = beacon.trend_minutes

    async def async_added_to_hass(self):
        if (last := await self.async_get_last_number_data()) and last.native_value is not None:
            self._attr_native_value = last.native_value
        self.b.trend_minutes = self._attr_native_value

    async def async_set_native_value(self, value):
        self._attr_native_value = value
        self.b.trend_minutes = value
        self.async_write_ha_state()
