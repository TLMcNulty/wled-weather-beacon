import logging

import aiohttp
import voluptuous as vol

from homeassistant.config_entries import ConfigFlow
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (EntitySelector, EntitySelectorConfig, NumberSelector,
                                            NumberSelectorConfig, NumberSelectorMode)

from . import DOMAIN

_LOGGER = logging.getLogger(__name__)

SCHEMA = vol.Schema({
    vol.Required("host"): str,
    vol.Required("weather"): EntitySelector(EntitySelectorConfig(domain="weather")),
    vol.Required("hours", default=3): NumberSelector(NumberSelectorConfig(min=1, max=12, mode=NumberSelectorMode.BOX)),
})


class WeatherBeaconFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_zeroconf(self, discovery_info):
        """A WLED lamp announced itself. If it's a configured beacon (same MAC) at a new address, follow it and
        reload; HA's helper does the update. Any other WLED device is ignored, so no discovery pop-ups."""
        mac = discovery_info.properties.get("mac")
        _LOGGER.info("WLED %s announced at %s", mac, discovery_info.host)
        if mac:
            await self.async_set_unique_id(mac)
            self._abort_if_unique_id_configured(updates={"host": discovery_info.host})
        return self.async_abort(reason="not_beacon")

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            host = user_input["host"].strip().removeprefix("http://").rstrip("/")
            try:
                async with async_get_clientsession(self.hass).get(
                        f"http://{host}/json/info", timeout=aiohttp.ClientTimeout(total=10)) as r:
                    info = await r.json(content_type=None)
                name, mac = info["name"].strip(), info["mac"]
            except (aiohttp.ClientError, TimeoutError, KeyError, ValueError, TypeError):
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(mac)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=f"Weather beacon {name}",
                                               data={**user_input, "host": host, "hours": int(user_input["hours"])})
        return self.async_show_form(step_id="user", data_schema=self.add_suggested_values_to_schema(SCHEMA, user_input),
                                    errors=errors)
