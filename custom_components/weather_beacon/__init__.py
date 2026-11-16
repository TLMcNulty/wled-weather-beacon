"""WLED Weather Beacon: show Home Assistant's hourly forecast on a WLED lamp."""
import asyncio
from datetime import timedelta
import logging
import time

import aiohttp

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.start import async_at_started

from .looks import MODES, TREND, TREND_STYLES, glance_seg, gradient, pick, trend

DOMAIN = "weather_beacon"
PLATFORMS = [Platform.NUMBER, Platform.SELECT, Platform.SENSOR]
FORECAST_EVERY, TREND_EVERY = timedelta(minutes=10), timedelta(seconds=60)
_LOGGER = logging.getLogger(__name__)


class Beacon:
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry):
        self.hass, self.entry = hass, entry
        self.host, self.weather, self.hours = entry.data["host"], entry.data["weather"], int(entry.data["hours"])
        self.session = async_get_clientsession(hass)
        self.style, self.mode = TREND_STYLES[0], MODES[0]  # overwritten by the restored select entities
        self.full, self.last, self.lock = [], None, asyncio.Lock()
        self.trend_minutes, self.last_blink = 1, 0.0  # minutes overwritten by the restored number entity
        self.signal = f"{DOMAIN}_{entry.entry_id}"
        self.device = DeviceInfo(identifiers={(DOMAIN, entry.entry_id)}, name=entry.title, manufacturer="WLED Weather Beacon")

    async def wled(self, path, body=None):
        method = self.session.get if body is None else self.session.post
        async with method(f"http://{self.host}/json/{path}", json=body, timeout=aiohttp.ClientTimeout(total=10)) as r:
            r.raise_for_status()
            return await r.json(content_type=None)

    async def refresh(self, *_):
        """Fetch the forecast, update the sensors, repaint the lamp."""
        try:
            resp = await self.hass.services.async_call("weather", "get_forecasts", {"type": "hourly"}, blocking=True,
                                                       target={"entity_id": self.weather}, return_response=True)
            self.full = resp[self.weather]["forecast"]
            async_dispatcher_send(self.hass, self.signal)
            await self.paint()
        except Exception as e:  # HA weather or lamp offline: log and retry next round
            self.last = None  # the lamp may have lost power and rebooted to its own preset: repaint once it answers
            _LOGGER.warning("weather beacon refresh failed: %s", e)

    async def paint(self):
        if not self.full:
            return
        if not (await self.wled("state"))["on"]:
            self.last = None  # leave the lamp alone while it's off; repaint when it comes back on
            return
        conds = [h["condition"] for h in self.full[:self.hours]]
        if self.mode == "gradient":
            leds = gradient(conds, (await self.wled("info"))["leds"]["count"])
            # shortcut: one request for the whole strip; WLED's JSON buffer caps out around ~1000 LEDs, chunk "i" beyond that
            seg = {"id": 0, "start": 0, "stop": len(leds), "fx": 0, "i": leds}
        else:
            seg = glance_seg(pick(conds), await self.wled("eff"), await self.wled("pal"))
        if seg != self.last:  # resending restarts the effect, so only send changes
            async with self.lock:
                await self.wled("state", {"seg": [seg]})
            self.last = seg
            _LOGGER.debug("look -> %s (%s) for %s", conds, self.mode, self.host)

    async def pulse(self, now=None, force=False):
        """The warmer/same/colder signal: every trend_minutes, or now when force (a style preview)."""
        if self.last is None:
            return await self.refresh()  # lamp was off or never painted: check every round so it lights up promptly
        if self.style == "off":
            return
        if not force and time.monotonic() - self.last_blink < self.trend_minutes * 60 - 5:  # 5 s slack for timer jitter
            return
        self.last_blink = time.monotonic()
        try:
            async with self.lock:
                await self.blink(TREND[trend(self.full[:self.hours])], self.last)
        except Exception as e:
            self.last = None  # as in refresh: repaint the look when the lamp is back
            _LOGGER.warning("weather beacon trend signal failed: %s", e)

    async def blink(self, rgb, restore):
        """Show the trend colour over the look in self.style, then put the look back. tt = WLED transition in 100 ms."""
        post = lambda body: self.wled("state", body)
        solid = lambda c: [{"id": 0, "frz": False, "fx": 0, "col": [list(c), [0, 0, 0]]}]
        style = "fade" if self.style == "overlay" and "col" not in restore else self.style  # gradient has no background
        if style == "fade":  # two slow crossfades
            for _ in range(2):
                await post({"tt": 6, "seg": solid(rgb)}); await asyncio.sleep(1.0)
                await post({"tt": 6, "seg": [restore]}); await asyncio.sleep(1.0)
        elif style == "dip":  # dim the look, pop the colour at full brightness, dim, back up
            bri = (await self.wled("state"))["bri"]
            low = max(bri // 5, 5)
            await post({"tt": 5, "bri": low}); await asyncio.sleep(0.7)
            await post({"tt": 2, "bri": bri, "seg": solid(rgb)}); await asyncio.sleep(0.4)
            for col in [(0, 0, 0), rgb] * 3:  # rapid blinks of the trend colour
                await post({"tt": 0, "seg": solid(col)}); await asyncio.sleep(0.12)
            await asyncio.sleep(0.3)
            await post({"tt": 5, "bri": low, "seg": [restore]}); await asyncio.sleep(0.7)
            await post({"tt": 5, "bri": bri})
        elif style == "overlay":  # effect keeps running; its background fades to the trend colour at 25%
            await post({"tt": 8, "seg": [{"id": 0, "col": [restore["col"][0], [c // 4 for c in rgb]]}]})
            await asyncio.sleep(4)
            await post({"tt": 8, "seg": [restore]})
        else:  # flash: three hard blinks
            for col in [rgb, (0, 0, 0)] * 3:
                await post({"tt": 0, "seg": solid(col)}); await asyncio.sleep(0.35)
            await post({"seg": [restore]})


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    beacon = entry.runtime_data = Beacon(hass, entry)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)  # restores the selects before the first paint
    entry.async_on_unload(async_track_time_interval(hass, beacon.refresh, FORECAST_EVERY))
    entry.async_on_unload(async_track_time_interval(hass, beacon.pulse, TREND_EVERY))
    # the weather entity may not exist until HA has finished starting; runs at once if HA is already up
    # @callback: a plain lambda is run in a worker thread, where creating the task fails
    entry.async_on_unload(async_at_started(hass, callback(lambda _: entry.async_create_background_task(
        hass, beacon.refresh(), f"{DOMAIN} first refresh"))))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
