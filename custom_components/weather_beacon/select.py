from homeassistant.components.select import SelectEntity
from homeassistant.helpers.restore_state import RestoreEntity

from .looks import MODES, TREND_STYLES


async def async_setup_entry(hass, entry, async_add_entities):
    b = entry.runtime_data
    async_add_entities([BeaconSelect(b, "style", TREND_STYLES), BeaconSelect(b, "mode", MODES)])


class BeaconSelect(SelectEntity, RestoreEntity):
    """Trend style / Mode. Restored across restarts; the beacon reads the value as beacon.style / beacon.mode."""
    _attr_has_entity_name = True

    def __init__(self, beacon, key, options):
        self.b, self.key = beacon, key
        self._attr_translation_key = key
        self._attr_options = options
        self._attr_current_option = options[0]
        self._attr_unique_id = f"{beacon.entry.entry_id}_{key}"
        self._attr_device_info = beacon.device

    async def async_added_to_hass(self):
        if (s := await self.async_get_last_state()) and s.state in self.options:
            self._attr_current_option = s.state
        setattr(self.b, self.key, self._attr_current_option)

    async def async_select_option(self, option):
        self._attr_current_option = option
        setattr(self.b, self.key, option)
        self.async_write_ha_state()
        if self.key == "mode":
            await self.b.paint()
        elif self.b.last is not None:  # preview the new style now instead of waiting for the next round
            self.hass.async_create_task(self.b.pulse(force=True))
