"""Pure beacon logic: which look and trend the forecast means. No HA or network code.
shortcut: copied from the standalone beacon.py; if both live on, make beacon.py import this file."""

# Most significant first: the first row matching any hour in the window wins.
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
# HA's catch-all "exceptional" (not an alert) or a condition HA adds later: slow red blink = "beacon can't tell"
UNKNOWN = ({"exceptional"}, "Blink", "* Colors 1&2", [(255, 0, 0), (0, 0, 0)], 60, 128)
COLORS = {c: fg for conds, _, _, (fg, _), *_ in GLANCE for c in conds}  # gradient mode uses each look's main colour
TREND = {"warmer": (255, 0, 0), "same": (0, 255, 0), "colder": (0, 60, 255)}
TREND_DEG = 3  # change in HA's temperature unit that counts as warmer/colder
TREND_HOURS = 12  # how far ahead the trend looks; independent of the look window
TREND_STYLES = ["dip", "flash", "fade", "overlay", "off"]  # first = default
MODES = ["glance", "gradient"]


def pick(conds):
    return next((row for row in GLANCE if row[0] & set(conds)), UNKNOWN)


def why(conds, row):
    """The condition in the window that triggered this look."""
    return next((c for c in conds if c in row[0]), "unknown")


def trend(hours):
    """Where the temperature heads next, from an hourly forecast starting now.
    The first hour within TREND_HOURS that is TREND_DEG or more away from now gives the direction: the climb to the
    next peak or the drop to the next trough. Wiggles smaller than TREND_DEG never count; a short forecast uses what it has."""
    now = hours[0]["temperature"]
    d = next((h["temperature"] - now for h in hours[1:TREND_HOURS + 1] if abs(h["temperature"] - now) >= TREND_DEG), 0)
    return "warmer" if d >= TREND_DEG else "colder" if d <= -TREND_DEG else "same"


def gradient(conds, n):
    """n hex colours: each hour gets an equal share of the strip, blending linearly into the next hour."""
    rgb = [COLORS.get(c, (255, 0, 0)) for c in conds]
    out = []
    for p in range(n):
        t = p * (len(rgb) - 1) / max(n - 1, 1)
        a, b, f = rgb[int(t)], rgb[min(int(t) + 1, len(rgb) - 1)], t - int(t)
        out.append("".join(f"{round(x + (y - x) * f):02X}" for x, y in zip(a, b)))
    return out


def glance_seg(row, eff, pal):
    _, fx, palette, col, sx, ix = row
    # frz: gradient mode's per-LED write freezes the segment, which leaves the lamp dark/stuck on the next effect
    return {"id": 0, "frz": False, "fx": eff.index(fx), "pal": pal.index(palette), "col": [list(c) for c in col], "sx": sx, "ix": ix}


def ahead(full, hours, n=12):
    """What the lamp will show at each of the next n hours."""
    out = []
    for i in range(min(n, max(len(full) - hours + 1, 0))):
        win = full[i:i + hours]
        conds = [h["condition"] for h in win]
        row = pick(conds)
        out.append({"time": win[0]["datetime"], "condition": win[0]["condition"], "temperature": win[0].get("temperature"),
                    "look": why(conds, row), "effect": row[1], "trend": trend(full[i:])})
    return out


assert gradient(["sunny", "rainy"], 2) == ["FF9600", "006EFF"] and gradient(["fog"], 3) == ["6E6E6E"] * 3
assert pick(["cloudy", "rainy", "sunny"])[1] == "Rain" and pick(["sunny"])[1] == "Solid" and pick(["new"]) is UNKNOWN
T = lambda *ts: trend([{"temperature": t} for t in ts])
assert [T(40, t) for t in (44, 41, 36)] == ["warmer", "same", "colder"]
assert T(40, 41, 42, 43, 44) == "warmer"  # steady rise
assert T(40, 42, 44, 41, 35, 30) == "warmer" and T(40, 38, 36, 39, 45) == "colder"  # the first peak/trough wins
assert T(40, 42, 39, 41, 38, 42) == "same"  # wiggle under TREND_DEG
assert T(*[40] * (TREND_HOURS + 1), 50) == "same" and T(*[40] * TREND_HOURS, 50) == "warmer"  # 50 is 13 h vs 12 h out
assert T(40) == "same" and T(40, 37) == "colder"  # forecast shorter than the horizon
