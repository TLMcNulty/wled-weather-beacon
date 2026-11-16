from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.const import STATE_ON
from homeassistant.core import callback
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.event import async_track_state_change_event

from .looks import GLANCE, TREND, UNKNOWN, ahead, pick, trend, why


async def async_setup_entry(hass, entry, async_add_entities):
    b = entry.runtime_data
    async_add_entities([LookSensor(b), TrendSensor(b), SummarySensor(b)])


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
    _attr_device_class = SensorDeviceClass.ENUM  # states stay HA condition ids; translations give the display names
    _attr_options = sorted({c for row in [*GLANCE, UNKNOWN] for c in row[0]})

    def __init__(self, beacon):
        super().__init__(beacon, "look")

    @property
    def native_value(self):
        conds = [h["condition"] for h in self.window]
        look = why(conds, pick(conds)) if conds else None
        return look if look in self.options else None  # a condition HA adds later reads as Unknown

    @property
    def extra_state_attributes(self):
        conds = [h["condition"] for h in self.window]
        return {"effect": pick(conds)[1] if conds else None, "ahead": ahead(self.b.full, self.b.hours)}


class TrendSensor(BeaconSensor):
    _attr_icon = "mdi:thermometer"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = list(TREND)

    def __init__(self, beacon):
        super().__init__(beacon, "trend")

    @property
    def native_value(self):
        return trend(self.window) if self.window else None


# shortcut: English only; the Look/Trend sensors stay translatable. Move these into translations if the summary text needs other languages.
LOOK_NAMES = {"clear-night": "Clear, night", "cloudy": "Cloudy", "exceptional": "Exceptional", "fog": "Fog", "hail": "Hail",
              "lightning": "Lightning", "lightning-rainy": "Lightning, rainy", "partlycloudy": "Partly cloudy", "pouring": "Pouring",
              "rainy": "Rainy", "snowy": "Snowy", "snowy-rainy": "Snowy, rainy", "sunny": "Sunny", "windy": "Windy",
              "windy-variant": "Windy, cloudy"}
LOOK_ICONS = {c: f"mdi:weather-{c.replace('partlycloudy', 'partly-cloudy').replace('clear-night', 'night')}" for c in LOOK_NAMES}
LOOK_ICONS["exceptional"] = "mdi:alert-circle-outline"
HUES = [(15, "red"), (45, "orange"), (70, "yellow"), (160, "green"), (200, "teal"), (260, "blue"), (290, "purple"), (345, "pink"), (361, "red")]


def colour_name(hs):
    """Rough name for a light's hs_color: pale colours are white, the rest by hue band."""
    if not hs or hs[1] < 20:
        return "white"
    return next(n for top, n in HUES if hs[0] < top)


def lamp_text(state):
    if state is None:
        return "Lamp not found"
    if state.state != STATE_ON:
        return f"Lamp {state.state}"
    return f"{state.attributes.get('effect') or 'Solid'} {colour_name(state.attributes.get('hs_color'))}"


class SummarySensor(BeaconSensor):
    """One line for a dashboard tile: look, trend and what the lamp is showing; the icon follows the look."""

    def __init__(self, beacon):
        super().__init__(beacon, "summary")
        self.light = None

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        # the lamp's WLED light: same MAC as this beacon's unique id
        mac = (dr.CONNECTION_NETWORK_MAC, dr.format_mac(self.b.entry.unique_id or ""))
        ents = er.async_get(self.hass)
        self.light = next((e.entity_id for d in dr.async_get(self.hass).async_get_devices(connections={mac})
                           for e in er.async_entries_for_device(ents, d.id) if e.domain == "light"), None)
        if self.light:
            self.async_on_remove(async_track_state_change_event(self.hass, self.light, callback(lambda _: self.async_write_ha_state())))

    @property
    def _look(self):
        conds = [h["condition"] for h in self.window]
        return why(conds, pick(conds)) if conds else None

    @property
    def native_value(self):
        if not self.window:
            return None
        look = LOOK_NAMES.get(self._look, "Unknown")
        lamp = lamp_text(self.hass.states.get(self.light) if self.light else None)
        return f"{look} · {trend(self.window).capitalize()} · {lamp}"

    @property
    def icon(self):
        return LOOK_ICONS.get(self._look, "mdi:weather-cloudy-alert")


assert colour_name([60, 13]) == "white" and colour_name([214, 100]) == "blue" and colour_name([350, 90]) == "red"
assert LOOK_ICONS["partlycloudy"] == "mdi:weather-partly-cloudy" and LOOK_ICONS["clear-night"] == "mdi:weather-night"
