import os
import json
import requests
from functools import lru_cache
from datetime import datetime, timezone, timedelta
from skyfield.api import load, wgs84
from skyfield import almanac

CONFIG_FILE = 'config.json'

def get_location_config():
    """Load location from config or auto-detect via IP Geolocation."""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                cfg = json.load(f)
                if cfg.get("latitude") != 0.0 or cfg.get("longitude") != 0.0:
                    return cfg
        except Exception as e:
            print(f"Error reading config: {e}")

    print("Fetching coordinates via IP geolocation...")
    try:
        res = requests.get('http://ip-api.com/json/', timeout=3).json()
        if res.get('status') == 'success':
            lat = res.get('lat', 0.0)
            lon = res.get('lon', 0.0)
            city = res.get('city', 'Detected Location')
        else:
            lat, lon, city = 0.0, 0.0, "Unknown"
    except Exception as e:
        print(f"Geolocation failed: {e}. Defaulting to (0, 0).")
        lat, lon, city = 0.0, 0.0, "UTC Default"

    config = {"latitude": lat, "longitude": lon, "city": city}
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(config, f, indent=4)
    except Exception as e:
        print(f"Could not save config: {e}")
    return config

# Ephemeris & location setup
config = get_location_config()
LAT, LON = config["latitude"], config["longitude"]

ts = load.timescale(builtin=True)
eph = load('de421.bsp')
sun, earth, moon = eph['sun'], eph['earth'], eph['moon']
observer = earth + wgs84.latlon(LAT, LON)


@lru_cache(maxsize=16)
def _get_cached_sun_events(date_str: str, lat: float, lon: float):
    """
    Cached calculation for sunrise/sunset discrete events over a 3-day window.
    Only computes once per calendar day per coordinate set.
    """
    base_dt = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    t_start = ts.from_datetime(base_dt - timedelta(days=1.5))
    t_end = ts.from_datetime(base_dt + timedelta(days=1.5))
    
    t_events, y_events = almanac.find_discrete(
        t_start, t_end, almanac.sunrise_sunset(eph, wgs84.latlon(lat, lon))
    )

    events = sorted(
        [(tr.utc_datetime(), y) for tr, y in zip(t_events, y_events)],
        key=lambda x: x[0]
    )
    return events


@lru_cache(maxsize=32)
def _get_cached_astronomical_positions(cache_key_10s: int):
    """
    Caches heavy Skyfield planetary position vectors for 10-second blocks.
    Keeps sub-second clock calculations instantaneous (< 0.1ms).
    """
    now_utc = datetime.fromtimestamp(cache_key_10s * 10, tz=timezone.utc)
    t = ts.from_datetime(now_utc)

    app_sun = observer.at(t).observe(sun).apparent()
    ra_sun, _, _ = app_sun.radec()
    _, ecl_lon_sun, _ = app_sun.ecliptic_latlon()

    app_moon = observer.at(t).observe(moon).apparent()
    ra_moon, _, _ = app_moon.radec()
    _, ecl_lon_moon, _ = app_moon.ecliptic_latlon()

    solar_year_progress = (ecl_lon_sun.degrees % 360.0) / 360.0
    moon_phase_deg = (ecl_lon_moon.degrees - ecl_lon_sun.degrees) % 360.0
    moon_progress = moon_phase_deg / 360.0

    return {
        "ra_sun_hours": ra_sun.hours,
        "ra_moon_hours": ra_moon.hours,
        "solar_year_progress": solar_year_progress,
        "moon_progress": moon_progress
    }


def get_clock_data(now_utc: datetime = None):
    """
    Computes all astronomical and standard clock metrics with sub-second precision.
    """
    if now_utc is None:
        now_utc = datetime.now(timezone.utc)

    t = ts.from_datetime(now_utc)
    now_ts = now_utc.timestamp()

    # 1. Standard Clock
    local_now = now_utc.astimezone() if now_utc.tzinfo else now_utc
    std_sec = local_now.second + local_now.microsecond / 1e6
    std_min = local_now.minute + std_sec / 60.0
    std_hour = (local_now.hour % 12) + std_min / 60.0
    is_pm = local_now.hour >= 12

    # 2. Cached Astronomical Ephemeris Data (10s cache window)
    cache_key_10s = int(now_ts // 10)
    astro = _get_cached_astronomical_positions(cache_key_10s)

    # 3. Classical / Roman Seasonal Clock (Horae Temporales)
    date_key = now_utc.strftime("%Y-%m-%d")
    events = _get_cached_sun_events(date_key, LAT, LON)

    sunrises_before = [dt for dt, y in events if y == 1 and dt <= now_utc]
    sunsets_after = [dt for dt, y in events if y == 0 and dt > now_utc]
    sunsets_before = [dt for dt, y in events if y == 0 and dt <= now_utc]
    sunrises_after = [dt for dt, y in events if y == 1 and dt > now_utc]

    if sunrises_before and sunsets_after and sunrises_before[-1] < sunsets_after[0] and sunrises_before[-1] <= now_utc <= sunsets_after[0]:
        s_0 = sunrises_before[-1]
        t_0 = sunsets_after[0]
        day_len = max(1.0, (t_0 - s_0).total_seconds())
        elapsed = (now_utc - s_0).total_seconds()
        roman_total_hours = (elapsed / day_len) * 12.0
    else:
        if sunsets_before and sunrises_after:
            t_last_sunset = sunsets_before[-1]
            s_next_sunrise = sunrises_after[0]
            night_len = max(1.0, (s_next_sunrise - t_last_sunset).total_seconds())
            elapsed = (now_utc - t_last_sunset).total_seconds()
            roman_total_hours = 12.0 + (elapsed / night_len) * 12.0
        else:
            roman_total_hours = (now_utc.hour + now_utc.minute / 60.0 + now_utc.second / 3600.0) % 24.0

    rom_hour = roman_total_hours % 12.0
    rom_min = (roman_total_hours * 60.0) % 60.0
    rom_sec = (roman_total_hours * 3600.0) % 60.0

    # 4. Solar Clock (Local Apparent Solar Time)
    last_sidereal = t.gast + (LON / 15.0)
    hour_angle_sun = (last_sidereal - astro["ra_sun_hours"]) % 24.0
    solar_time_hours = (hour_angle_sun + 12.0) % 24.0

    sol_hour = solar_time_hours % 12.0
    sol_min = (solar_time_hours * 60.0) % 60.0
    sol_sec = (solar_time_hours * 3600.0) % 60.0

    # 5. Tidal & Moon Clock
    lunar_hour_angle = (last_sidereal - astro["ra_moon_hours"]) % 24.0
    tidal_cycle_hours = lunar_hour_angle % 12.0

    tide_hour = tidal_cycle_hours
    tide_min = (tidal_cycle_hours * 60.0) % 60.0
    tide_sec = (tidal_cycle_hours * 3600.0) % 60.0

    return {
        "server_time": now_ts,
        "tick": int(now_ts),
        "is_pm": is_pm,
        "location": config,
        "season_progress": astro["solar_year_progress"],
        "moon_progress": astro["moon_progress"],
        "standard": {"h": std_hour, "m": std_min, "s": std_sec},
        "roman": {"h": rom_hour, "m": rom_min, "s": rom_sec},
        "solar": {"h": sol_hour, "m": sol_min, "s": sol_sec},
        "tidal": {"h": tide_hour, "m": tide_min, "s": tide_sec}
    }
