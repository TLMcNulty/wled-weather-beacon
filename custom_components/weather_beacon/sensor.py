from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from .looks import ahead, pick, trend, why


async def async_setup_entry(hass, entry, async_add_entities):
    b = entry.runtime_data
    async_add_entities([LookSensor(b), TrendSensor(b)])


class BeaconSensor(SensorEntity):
    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, beacon, key):
        self.b = beacon
        self._attr_translation_key = key
        self._attr_unique_id = f"{beacon.entry.entry_id}_{key}"
        self._attr_device_info = beacon.device

    async def async_added_to_hass(self):
        self.async_on_remove(async_dispatcher_connect(self.hass, self.b.signal, self.async_write_ha_state))

    @property
    def window(self):
        return self.b.full[:self.b.hours]


class LookSensor(BeaconSensor):
    """State: the weather the lamp is showing. Attributes: its WLED effect and the next 12 hours of looks."""
    _attr_icon = "mdi:lightbulb-on"

    def __init__(self, beacon):
        super().__init__(beacon, "look")

    @property
    def native_value(self):
        conds = [h["condition"] for h in self.window]
        return why(conds, pick(conds)) if conds else None

    @property
    def extra_state_attributes(self):
        conds = [h["condition"] for h in self.window]
        return {"effect": pick(conds)[1] if conds else None, "ahead": ahead(self.b.full, self.b.hours)}


class TrendSensor(BeaconSensor):
    _attr_icon = "mdi:thermometer"

    def __init__(self, beacon):
        super().__init__(beacon, "trend")

    @property
    def native_value(self):
        return trend(self.window) if self.window else None
