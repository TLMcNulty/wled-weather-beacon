# Changelog

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
