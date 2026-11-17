"""Weather beacon for a WLED lamp, fed by Home Assistant's hourly forecast. Stdlib only. Leaves the lamp alone while it is off.
MODE=glance (default): one colour + effect for the most significant weather in the next HOURS (see GLANCE).
MODE=gradient: the next HOURS painted across every LED, start of the strip = this hour.
Every TREND_EVERY s it flashes red/green/blue for warmer/same/colder over the window, in TREND_STYLE.
Status page on PORT; POST /style/<name|next> switches TREND_STYLE live.
Demos: `beacon.py demo` (every look, 10 s each), `demo-trend`, `demo-blend [warmer|same|colder]`.
Env: HA_URL, HA_TOKEN, WLED_HOST, [WEATHER_ENTITY=weather.forecast_home] [MODE=glance] [HOURS=3] [INTERVAL=600]
     [TREND_EVERY=60] [TREND_DEG=3] [TREND_STYLE=flash] [PORT=8080] [DRY_RUN=1]"""
import datetime, json, os, sys, time, urllib.request

E = os.environ.get
MODE, HOURS, INTERVAL, ENTITY = E("MODE", "glance"), int(E("HOURS", "3")), int(E("INTERVAL", "600")), E("WEATHER_ENTITY", "weather.forecast_home")

# Glance looks, most significant first: the first row matching any hour in the window wins.
# (HA conditions, WLED effect, palette, [fg, bg] colours, speed, intensity). Names are resolved against the lamp's own lists.
GLANCE = [
    ({"lightning", "lightning-rainy"}, "Lightning", "* Colors 1&2", [(200, 120, 255), (25, 0, 50)], 180, 160),
    ({"snowy", "snowy-rainy", "hail"}, "Twinklefox", "* Colors 1&2", [(255, 255, 255), (0, 40, 90)], 60, 180),
    ({"pouring"}, "Rain", "* Colors 1&2", [(0, 60, 255), (0, 0, 30)], 220, 200),
    ({"rainy"}, "Rain", "* Colors 1&2", [(0, 110, 255), (0, 0, 20)], 110, 90),
    ({"windy", "windy-variant"}, "Running", "* Colors 1&2", [(0, 200, 150), (0, 30, 25)], 200, 60),
    ({"fog"}, "Breathe", "* Colors 1&2", [(110, 110, 110), (10, 10, 10)], 30, 128),
    ({"cloudy"}, "Candle Multi", "Cloud", [(130, 130, 160), (0, 0, 0)], 60, 100),
    ({"partlycloudy"}, "Fade", "* Colors 1&2", [(255, 190, 60), (110, 110, 140)], 15, 128),
    ({"clear-night"}, "Twinkle", "* Colors 1&2", [(255, 255, 220), (5, 5, 40)], 40, 40),
    ({"sunny"}, "Solid", "* Colors 1&2", [(255, 150, 0), (0, 0, 0)], 128, 128),
]
TREND_EVERY, TREND_DEG = int(E("TREND_EVERY", "60")), float(E("TREND_DEG", "3"))  # degrees in HA's temperature unit
TREND_HOURS = 12  # how far ahead the trend looks; independent of the look window
TREND = {"warmer": (255, 0, 0), "same": (0, 255, 0), "colder": (0, 60, 255)}  # red/green/blue; green = no change, as on the original Weatherball
# HA's catch-all "exceptional" (not an alert) or a condition HA adds later: slow red blink = "beacon can't tell"
UNKNOWN = ({"exceptional"}, "Blink", "* Colors 1&2", [(255, 0, 0), (0, 0, 0)], 60, 128)
COLORS = {c: fg for conds, _, _, (fg, _), *_ in GLANCE for c in conds}  # gradient mode uses each look's main colour


def http(url, body=None, headers={}):
    r = urllib.request.Request(url, data=json.dumps(body).encode() if body is not None else None,
                               headers={"Content-Type": "application/json", **headers})
    return json.load(urllib.request.urlopen(r, timeout=15))


def gradient(conds, n):
    """n hex colours: each hour gets an equal share of the strip, blending linearly into the next hour."""
    rgb = [COLORS.get(c, (255, 0, 0)) for c in conds]
    out = []
    for p in range(n):
        t = p * (len(rgb) - 1) / max(n - 1, 1)
        a, b, f = rgb[int(t)], rgb[min(int(t) + 1, len(rgb) - 1)], t - int(t)
        out.append("".join(f"{round(x + (y - x) * f):02X}" for x, y in zip(a, b)))
    return out


def pick(conds):
    return next((row for row in GLANCE if row[0] & set(conds)), UNKNOWN)


def glance_seg(row, eff, pal):
    _, fx, palette, col, sx, ix = row
    # frz: gradient mode's per-LED write freezes the segment, which leaves the lamp dark/stuck on the next effect
    return {"id": 0, "frz": False, "fx": eff.index(fx), "pal": pal.index(palette), "col": [list(c) for c in col], "sx": sx, "ix": ix}


def forecast():
    return http(f"{E('HA_URL')}/api/services/weather/get_forecasts?return_response", {"entity_id": ENTITY, "type": "hourly"},
                {"Authorization": f"Bearer {E('HA_TOKEN')}"})["service_response"][ENTITY]["forecast"]


def trend(hours):
    """Where the temperature heads next, from an hourly forecast starting now.
    The first hour within TREND_HOURS that is TREND_DEG or more away from now gives the direction: the climb to the
    next peak or the drop to the next trough. Wiggles smaller than TREND_DEG never count; a short forecast uses what it has."""
    now = hours[0]["temperature"]
    d = next((h["temperature"] - now for h in hours[1:TREND_HOURS + 1] if abs(h["temperature"] - now) >= TREND_DEG), 0)
    return "warmer" if d >= TREND_DEG else "colder" if d <= -TREND_DEG else "same"


TREND_STYLES = ("flash", "fade", "dip", "overlay")
style_now = E("TREND_STYLE", "dip")  # changed live by POST /style/<name|next>; "off" pauses the signal


import threading
lamp_lock = threading.Lock()  # the main loop and a /style preview must not blink over each other


def blink(rgb, restore, style=None):
    with lamp_lock:
        _blink(rgb, restore, style)


def _blink(rgb, restore, style=None):
    """Show the trend colour over the forecast look in one of TREND_STYLES, then put the look back.
    tt = WLED transition time in 100 ms units."""
    style = style or style_now
    w = f"http://{E('WLED_HOST')}"
    post = lambda body: http(f"{w}/json/state", body)
    solid = lambda c: [{"id": 0, "frz": False, "fx": 0, "col": [list(c), [0, 0, 0]]}]
    if style == "overlay" and "col" not in restore:
        style = "fade"  # gradient mode has no background colour to tint
    if style == "fade":  # two slow crossfades
        for _ in range(2):
            post({"tt": 6, "seg": solid(rgb)}); time.sleep(1.0)
            post({"tt": 6, "seg": [restore]}); time.sleep(1.0)
    elif style == "dip":  # dim the look, pop the colour at full brightness, dim, back up
        bri = http(f"{w}/json/state")["bri"]
        low = max(bri // 5, 5)
        post({"tt": 5, "bri": low}); time.sleep(0.7)
        post({"tt": 2, "bri": bri, "seg": solid(rgb)}); time.sleep(0.4)
        for col in [(0, 0, 0), rgb] * 3:  # rapid blinks of the trend colour
            post({"tt": 0, "seg": solid(col)}); time.sleep(0.12)
        time.sleep(0.3)
        post({"tt": 5, "bri": low, "seg": [restore]}); time.sleep(0.7)
        post({"tt": 5, "bri": bri})
    elif style == "overlay":  # effect keeps running; its background fades to the trend colour at 25%
        post({"tt": 8, "seg": [{"id": 0, "col": [restore["col"][0], [c // 4 for c in rgb]]}]}); time.sleep(4)
        post({"tt": 8, "seg": [restore]})
    else:  # flash: three hard blinks
        for col in [rgb, (0, 0, 0)] * 3:
            post({"tt": 0, "seg": solid(col)}); time.sleep(0.35)
        post({"seg": [restore]})


last, hours, full = None, [], []


def ahead(n=12):
    """What the lamp will show at each of the next n hours: (entry, look row, trend, triggering condition)."""
    out = []
    for i in range(min(n, max(len(full) - HOURS + 1, 0))):
        conds = [h["condition"] for h in full[i:i + HOURS]]
        row = pick(conds)
        out.append((full[i], row, trend(full[i:]), next((c for c in conds if c in row[0]), "unknown")))
    return out


def css(rgb):
    return "#%02x%02x%02x" % rgb


def page():
    try:
        st = http(f"http://{E('WLED_HOST')}/json/state") if E("WLED_HOST") else {}
        lamp = f"{'on' if st.get('on') else 'off'}, brightness {round(st.get('bri', 0) / 2.55)}%"
    except Exception as e:
        lamp = f"unreachable ({e.__class__.__name__})"
    rows, prev = [], None
    for h, row, tr, why in ahead():
        look = (row[1], tr)
        at = datetime.datetime.fromisoformat(h["datetime"]).astimezone().strftime("%a %H:%M")  # HA sends UTC
        swatch = "".join(f'<i style="background:{css(c)}"></i>' for c in row[3])
        mark = "" if look == prev else ' class="change"'
        rows.append(f"<tr{mark}><td>{at}</td><td>{h['condition']}</td><td>{h['temperature']}°</td>"
                    f"<td>{swatch} {why} <small>({row[1]})</small></td><td><i style=\"background:{css(TREND[tr])}\"></i> {tr}</td></tr>")
        prev = look
    now = ahead(1)
    head = (f"{now[0][3]} ({now[0][1][1]}) · trend {now[0][2]}" if now else "no forecast yet")
    return f"""<!doctype html><meta charset=utf-8><meta name=viewport content="width=device-width"><meta http-equiv=refresh content=60>
<title>Weather beacon</title><style>
:root{{color-scheme:light dark;font:15px system-ui;--line:#8884}}body{{max-width:44rem;margin:2rem auto;padding:0 1rem}}
table{{border-collapse:collapse;width:100%}}td,th{{padding:.35rem .5rem;border-bottom:1px solid var(--line);text-align:left}}
i{{display:inline-block;width:.9em;height:.9em;border-radius:50%;vertical-align:-.1em;margin-right:.15em;border:1px solid var(--line)}}
tr.change td{{font-weight:600}}small{{opacity:.7}}</style>
<h1>Weather beacon</h1><p><b>Time:</b> {time.strftime("%a %d %b, %H:%M")}<br><b>Lamp:</b> {lamp}<br><b>Showing now:</b> {head}<br><b>Mode:</b> {MODE}, {HOURS} h window,
trend signal <b>{style_now}</b> every {TREND_EVERY}s (±{TREND_DEG:g}°)</p>
<table><tr><th>Hour</th><th>Forecast</th><th>Temp</th><th>Lamp look</th><th>Trend blink</th></tr>{''.join(rows)}</table>
<p><small>Bold rows = the lamp changes. Look at each hour = most significant weather in the {HOURS} h from then.
Forecast refreshed every {INTERVAL // 60} min; page refreshes every minute.</small></p>"""


def serve():
    import http.server, threading

    class H(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            global style_now
            name = self.path.rstrip("/").rsplit("/", 1)[-1]
            cycle = TREND_STYLES + ("off",)
            if not self.path.startswith("/style/") or name not in cycle + ("next",):
                self.send_response(404); self.end_headers(); self.wfile.write(f"use /style/{{{'|'.join(cycle)}|next}}\n".encode())
                return
            style_now = cycle[(cycle.index(style_now) + 1) % len(cycle)] if name == "next" else name
            print("trend style ->", style_now, flush=True)
            if last and hours and style_now != "off":  # preview it now instead of waiting for the next round
                threading.Thread(target=blink, args=(TREND[trend(full)], last), daemon=True).start()
            self.send_response(200); self.end_headers(); self.wfile.write(f"{style_now}\n".encode())

        def do_GET(self):
            body = page().encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    srv = http.server.ThreadingHTTPServer(("", int(E("PORT", "8080"))), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()


def tick():
    global last, hours, full
    full = forecast()
    hours = full[:HOURS]
    conds = [h["condition"] for h in hours]
    if E("DRY_RUN"):
        return print(conds, "->", pick(conds)[1:], "| trend:", trend(full), [h["temperature"] for h in hours],
                     "| gradient:", gradient(conds, 6))
    w = f"http://{E('WLED_HOST')}"
    if not http(f"{w}/json/state")["on"]:
        last = None  # repaint when it comes back on
        return
    if MODE == "gradient":
        leds = gradient(conds, http(f"{w}/json/info")["leds"]["count"])
        # shortcut: one request for the whole strip; WLED's JSON buffer caps out around ~1000 LEDs, chunk "i" beyond that
        seg = {"id": 0, "start": 0, "stop": len(leds), "fx": 0, "i": leds}
    else:
        seg = glance_seg(pick(conds), http(f"{w}/json/eff"), http(f"{w}/json/pal"))
    if seg != last:  # resending restarts the effect, so only send changes
        http(f"{w}/json/state", {"seg": [seg]})
        last = seg
        print(time.strftime("%H:%M"), conds, "->", MODE if MODE == "gradient" else pick(conds)[1], flush=True)


assert gradient(["sunny", "rainy"], 2) == ["FF9600", "006EFF"] and gradient(["fog"], 3) == ["6E6E6E"] * 3
assert pick(["cloudy", "rainy", "sunny"])[1] == "Rain" and pick(["sunny"])[1] == "Solid" and pick(["new"]) is UNKNOWN
assert [trend([{"temperature": 40}, {"temperature": t}]) for t in (44, 41, 36)] == ["warmer", "same", "colder"]
assert trend([{"temperature": t} for t in (40, 42, 44, 41, 35)]) == "warmer"  # the first peak/trough wins

if sys.argv[1:2] == ["demo-blend"]:  # each TREND_STYLE with one trend colour, 5 s apart
    tick()
    for style in TREND_STYLES:
        time.sleep(2)
        print("style", style, flush=True)
        blink(TREND[sys.argv[2] if len(sys.argv) > 2 else "warmer"], last, style)
    sys.exit()

if sys.argv[1:] == ["demo-trend"]:  # each trend signal over the current forecast look, 6 s apart
    tick()
    for name, rgb in TREND.items():
        time.sleep(6)
        print("signal", name, flush=True)
        blink(rgb, last)
    sys.exit()

if sys.argv[1:] == ["demo"]:
    w = f"http://{E('WLED_HOST')}"
    eff, pal = http(f"{w}/json/eff"), http(f"{w}/json/pal")
    for row in GLANCE + [UNKNOWN]:
        print("showing", sorted(row[0]) or ["unknown"], "->", row[1], flush=True)
        http(f"{w}/json/state", {"on": True, "seg": [glance_seg(row, eff, pal)]})
        time.sleep(10)
    sys.exit()

if not E("DRY_RUN"):
    serve()
next_fetch = 0
while True:
    try:
        if time.time() >= next_fetch or last is None:  # while the lamp is off, check every round so it lights up promptly
            tick()
            next_fetch = time.time() + INTERVAL
        elif last and TREND_EVERY and style_now != "off":  # last is None while the lamp is off
            blink(TREND[trend(full)], last)
    except Exception as e:  # lamp or HA offline: log and retry next round
        print("error:", e, file=sys.stderr, flush=True)
        next_fetch = time.time() + TREND_EVERY
    if E("DRY_RUN"):
        break
    time.sleep(TREND_EVERY or INTERVAL)
