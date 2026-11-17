# Changelog

## 0.1.0-beta.3

- The trend now shows where the temperature heads over the next 12 hours: the first hour `TREND_DEG` or more away from now (the next peak or trough) sets warmer or colder; smaller wiggles read as same. It used to compare only the ends of the look window. The `ahead` timeline uses the same rule.

## 0.1.0-beta.2

- **Summary** sensor: one line for a dashboard tile (look · trend · what the lamp is showing, e.g. `Clear, night · Same · Twinkle white`); its icon follows the look, and it follows the lamp's WLED light live.
- **Look** and **Trend** are enum sensors with display names (`Clear, night`, `Colder`); the stored states are unchanged, so automations keep working. **Trend style** and **Mode** options are capitalised too.
- Follows a lamp that gets a new IP address (WLED zeroconf announcement, matched by MAC).
- Repaints the look when the lamp comes back after losing power.
- Cloudy look: Candle Multi on the Cloud palette.
- Fixed: the first refresh after Home Assistant starts no longer fails; the sensors used to read unknown for about a minute.
- Removed the GitHub Actions workflow.

## 0.1.0-beta.1

The first test release.

- **Home Assistant integration** (HACS or manual install):
  - UI setup: lamp address, weather entity, forecast window
  - **Look** sensor, with a 12-hour `ahead` timeline attribute
  - **Trend** sensor
  - **Trend style** and **Mode** selects, kept across restarts
- **Glance mode:** one WLED effect and colour for the most significant weather in the window.
- **Temperature trend signal** every 60 s: red warmer, green same, blue colder. Styles are `dip` (default: dim, pop, rapid blinks, dim back), `flash`, `fade`, `overlay` and `off`.
- **Trend signal interval** setting: 1–60 minutes between signals, kept across restarts.
- **Gradient mode:** the forecast painted across every LED.
- **Standalone Docker version** (`beacon.py`) with a small status page, for people who'd rather not install an integration.

Tested on Home Assistant 2026.10.2 with WLED 0.15.4 (ESP32-C3, 24-LED RGBW strip) and met.no. Not yet tested on older Home Assistant versions, large LED counts or 2D matrices.
