#! /usr/bin/env python
import os
import json
import time
import math
import requests
from datetime import datetime, timezone
from flask import Flask, render_template
from flask_socketio import SocketIO
from skyfield.api import load, wgs84
from skyfield import almanac

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")

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
        res = requests.get('http://ip-api.com/json/', timeout=5).json()
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
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=4)
    return config

config = get_location_config()
LAT, LON = config["latitude"], config["longitude"]

ts = load.timescale()
eph = load('de421.bsp')
sun, earth, moon = eph['sun'], eph['earth'], eph['moon']
observer = earth + wgs84.latlon(LAT, LON)

def get_clock_data():
    now_utc = datetime.now(timezone.utc)
    t = ts.from_datetime(now_utc)
    
    # 1. Standard Clock
    local_now = datetime.now()
    std_sec = local_now.second + local_now.microsecond / 1e6
    std_min = local_now.minute + std_sec / 60.0
    std_hour = (local_now.hour % 12) + std_min / 60.0
    is_pm = local_now.hour >= 12

    # 2. Classical / Roman Seasonal Clock
    t0 = ts.utc(now_utc.year, now_utc.month, now_utc.day, 0, 0, 0)
    t1 = ts.utc(now_utc.year, now_utc.month, now_utc.day, 23, 59, 59)
    t_rise_fall, y_rise_fall = almanac.find_discrete(t0, t1, almanac.sunrise_sunset(eph, wgs84.latlon(LAT, LON)))
    
    rises = [tr.utc_datetime() for tr, y in zip(t_rise_fall, y_rise_fall) if y == 1]
    sets = [tr.utc_datetime() for tr, y in zip(t_rise_fall, y_rise_fall) if y == 0]

    sunrise = rises[0] if rises else now_utc.replace(hour=6, minute=0)
    sunset = sets[0] if sets else now_utc.replace(hour=18, minute=0)

    if sunrise <= now_utc <= sunset:
        day_length = (sunset - sunrise).total_seconds()
        elapsed = (now_utc - sunrise).total_seconds()
        roman_total_hours = (elapsed / day_length) * 12.0
    else:
        night_start = sunset if now_utc > sunset else sunset
        night_end = sunrise
        night_length = max(1.0, (night_end - night_start).total_seconds())
        elapsed = (now_utc - night_start).total_seconds()
        roman_total_hours = 12.0 + (elapsed / night_length) * 12.0

    rom_hour = roman_total_hours % 12.0
    rom_min = (roman_total_hours * 60.0) % 60.0
    rom_sec = (roman_total_hours * 3600.0) % 60.0

    # 3. Solar Clock
    astrometric = observer.at(t).observe(sun)
    _, ecl_lon, _ = astrometric.apparent().ecliptic_latlon()
    
    solar_year_progress = (ecl_lon.degrees % 360.0) / 360.0
    solar_time_hours = (t.gast + (LON / 15.0)) % 24.0
    sol_hour = solar_time_hours % 12.0
    sol_min = (solar_time_hours * 60.0) % 60.0
    sol_sec = (solar_time_hours * 3600.0) % 60.0

    # 4. Tidal & Moon Clock
    moon_app = observer.at(t).observe(moon).apparent()
    sun_app = observer.at(t).observe(sun).apparent()
    
    _, m_lon, _ = moon_app.ecliptic_latlon()
    _, s_lon, _ = sun_app.ecliptic_latlon()
    
    moon_phase_deg = (m_lon.degrees - s_lon.degrees) % 360.0
    moon_progress = moon_phase_deg / 360.0

    tidal_cycle_hours = ((moon_phase_deg * 2.0) % 360.0) / 360.0 * 12.0
    tide_hour = tidal_cycle_hours
    tide_min = (tidal_cycle_hours * 60.0) % 60.0
    tide_sec = (tidal_cycle_hours * 3600.0) % 60.0

    return {
        "is_pm": is_pm,
        "location": config,
        "season_progress": solar_year_progress,
        "moon_progress": moon_progress,
        "standard": {"h": std_hour, "m": std_min, "s": std_sec},
        "roman": {"h": rom_hour, "m": rom_min, "s": rom_sec},
        "solar": {"h": sol_hour, "m": sol_min, "s": sol_sec},
        "tidal": {"h": tide_hour, "m": tide_min, "s": tide_sec}
    }

@app.route('/')
def index():
    return render_template('index.html')

def background_thread():
    while True:
        data = get_clock_data()
        socketio.emit('clock_update', data)
        socketio.sleep(0.1)

@socketio.on('connect')
def connect():
    socketio.start_background_task(background_thread)

if __name__ == '__main__':
    socketio.run(app, debug=True, host='0.0.0.0', port=5008)
