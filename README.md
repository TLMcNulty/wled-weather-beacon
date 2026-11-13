# WLED Weather Beacon

Turn a WLED lamp into a weather beacon: look at it and know what the next few hours will do. No screen, no app.

It reads Home Assistant's hourly forecast and shows **one effect and colour** for the most significant weather in the next 3 hours. Every minute it adds a quick **red / green / blue** flash for warmer, about the same, or colder. It takes its idea from the old city weather beacons: Boston's [Berkeley Building](https://en.wikipedia.org/wiki/Berkeley_Building) and the Minneapolis [Weatherball](https://www.mprnews.org/story/2017/12/07/friday-clipper-ahead-remember-the-weatherball).

- **What it is:** a single Python file with only the standard library and no dependencies.
- **What it needs:** Home Assistant (any weather integration with an hourly forecast) and a WLED lamp (tested on WLED 0.15.4).
- **How it talks to them:** it uses HA's REST API and WLED's JSON API. HA's WLED integration isn't needed.
- **Status page:** it serves a small page showing the lamp's state and what the lamp will show over the next 12 hours.

## The looks

The forecast window is checked from the top of this table down, and the first match wins. Sunny now but pouring in two hours means you see *pouring*.

| Weather | WLED effect | Colours |
|---|---|---|
| Thunder (`lightning`, `lightning-rainy`) | Lightning | violet flashes on deep purple |
| Snow (`snowy`, `snowy-rainy`, `hail`) | Twinklefox | white on dark blue |
| Heavy rain (`pouring`) | Rain, fast | blue |
| Rain (`rainy`) | Rain, slow | lighter blue |
| Wind (`windy`, `windy-variant`) | Running | teal |
| Fog (`fog`) | Breathe | dim grey |
| Cloudy (`cloudy`) | Palette, "Cloud" palette | cloud blues and whites |
| Partly cloudy (`partlycloudy`) | Fade | amber ↔ grey |
| Clear night (`clear-night`) | Twinkle | warm white stars on navy |
| Sunny (`sunny`) | Solid | amber |
| Anything else (`exceptional`, new conditions) | Blink, slow | red: "the beacon can't tell", **not** an alert |

All of these live in the `GLANCE` table at the top of `beacon.py`, one line per look. Effects and palettes are given by name and looked up on the lamp, so the table works across WLED builds.

### Temperature trend

Every `TREND_EVERY` seconds, the lamp compares the temperature at the end of the window with the temperature now:

- **Red:** warmer (by `TREND_DEG` or more)
- **Green:** about the same
- **Blue:** colder

`TREND_STYLE` sets how the flash blends with the look:

| Style | What it does |
|---|---|
| `flash` | three hard blinks |
| `fade` | two slow crossfades to the trend colour and back |
| `dip` | dims the look, pops the trend colour at full brightness, blinks it rapidly three times, then dims back to the forecast (default) |
| `overlay` | keeps the effect running and tints its background with the trend colour at 25%; doesn't show on looks that use a WLED palette, such as cloudy |
| `off` | no trend flash |

### Gradient mode

`MODE=gradient` paints the forecast across every LED instead. The start of the strip is this hour, and each hour blends into the next. It looks nice, but you can't read it at a glance as easily as one look.

## Install as a Home Assistant integration (recommended)

This option works on any Home Assistant install and needs no token or container.

1. **Install it.** Either:
   - **HACS:** go to HACS → ⋮ → Custom repositories, add this repo's URL with type **Integration**, then install *WLED Weather Beacon*.
   - **Manually:** copy `custom_components/weather_beacon` into your HA `config/custom_components/` folder.
2. Restart Home Assistant.
3. Go to **Settings → Devices & services → Add integration → WLED Weather Beacon**. Enter the lamp's IP, pick a weather entity, and choose the window (default 3 hours).

You get a device with these entities:

| Entity | What it is |
|---|---|
| `sensor.…_look` | the weather the lamp is showing. Its attributes hold the WLED effect, plus `ahead`, the next 12 hours of looks and trends, ready for a markdown card |
| `sensor.…_trend` | `warmer`, `same` or `colder` |
| `select.…_trend_style` | `dip` (default), `flash`, `fade`, `overlay` or `off`. Changing it previews the style on the lamp. Kept across restarts |
| `select.…_mode` | `glance` or `gradient` |
| `number.…_trend_signal_interval` | minutes between trend signals, 1–60 (default 1). It's on the device page under *Configuration* and kept across restarts |

The forecast is fetched every 10 minutes. The trend signal plays every *Trend signal interval* minutes. Changing the trend style always previews it straight away.

## Or run it standalone (Docker)


1. In Home Assistant, go to your **Profile → Security → Long-lived access tokens** and create a token named `weather-beacon`.
2. Find your lamp's IP address. It's in the WLED app, or in HA under the WLED device. Giving it a fixed address in your router helps.
3. Copy `.env.example` to `.env` and fill in `HA_URL`, `HA_TOKEN` and `WLED_HOST`. If your weather entity isn't `weather.forecast_home`, set `WEATHER_ENTITY` too.
4. Do a test run that prints what it would do without touching the lamp:
   ```sh
   set -a; . ./.env; set +a
   DRY_RUN=1 python3 beacon.py
   ```
5. Run it:
   ```sh
   docker compose up -d
   ```
   Or skip Docker and run `python3 beacon.py` with the same environment variables.
6. Open the status page at `http://<host>:8099`.

The beacon leaves the lamp alone while it's off. Turn the lamp on and it picks up the forecast look within a minute.

## Testing the beta

This is a test release, and feedback is very welcome.

1. **Get beta versions:** in HACS, open *WLED Weather Beacon* → ⋮ → **Redownload**, and turn on **Show beta versions**. Updates then appear as an update badge; install them and restart HA.
2. **Turn on debug logging** so you can see what the beacon tells the lamp:
   ```yaml
   logger:
     logs:
       custom_components.weather_beacon: debug
   ```
3. **Report problems** with the *Bug report* issue template. It asks for:
   - your Home Assistant, WLED and weather-integration versions
   - the Look and Trend sensor states
   - the log lines

**Known limits:**
- **Forecast:** it needs a weather entity with an **hourly** forecast. met.no, Home Assistant's default, has one; some integrations only offer daily forecasts.
- **Segments:** only the lamp's first WLED segment is used, and the beacon replaces whatever effect the lamp was running.
- **Tested so far:** a 24-LED strip only. Large strips (over about 1,000 LEDs) and 2D matrices are untested, especially in gradient mode.
- **Older Home Assistant:** not yet tested before 2026.10.

## Tuning and demos

```sh
python3 beacon.py demo                  # every look for 10 s each
python3 beacon.py demo-trend            # the red, green and blue flashes over the current look
python3 beacon.py demo-blend warmer     # each TREND_STYLE in turn
./style                                 # switch the running beacon to the next TREND_STYLE and preview it
./style dip                             # ...or pick one (BEACON=http://host:8099 if it runs elsewhere)
```

A style switched with `./style` lasts until the beacon restarts. To keep a style permanently, set `TREND_STYLE` in `.env`.

## Settings

| Variable | Default | |
|---|---|---|
| `HA_URL`, `HA_TOKEN` | required | Home Assistant URL and long-lived token |
| `WLED_HOST` | required | lamp IP or hostname |
| `WEATHER_ENTITY` | `weather.forecast_home` | needs an hourly forecast |
| `MODE` | `glance` | `glance` or `gradient` |
| `HOURS` | `3` | forecast window in hours |
| `INTERVAL` | `600` | seconds between forecast fetches |
| `TREND_EVERY` | `60` | seconds between trend flashes; `0` turns them off |
| `TREND_DEG` | `3` | change in HA's temperature unit that counts as warmer or colder |
| `TREND_STYLE` | `dip` | `flash`, `fade`, `dip`, `overlay` or `off` |
| `PORT` | `8080` | status page port inside the container |

## Notes and gotchas

- **Frozen segment:** writing per-LED colours (gradient mode) freezes the WLED segment (`frz: true`). If WLED is frozen, later effect changes are accepted but the lamp stays dark or stuck. Every glance write sends `frz: false` to clear it.
- **Only changes are sent:** the beacon sends a new look only when the look changes, because resending the same state restarts the effect and makes it stutter.
- **No login on the status page:** anyone who can reach port 8099 can see the forecast and switch the trend style. Keep it on your LAN.
- **Only the first WLED segment is used:** if your lamp has several segments, merge them into one in WLED first.

## Credits

The looks borrow from Boston's Berkeley Building beacon, the Minneapolis Weatherball and WCCO Weather Watcher, [ugobriasco/weather-lamp](https://github.com/ugobriasco/weather-lamp), [kmetz/WeatherLEDs](https://github.com/kmetz/WeatherLEDs) and [jgrahamc/totoro](https://github.com/jgrahamc/totoro).

Built with heavy use of LLM coding chatbots, primarily Claude.
