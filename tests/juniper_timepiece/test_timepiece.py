import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import juniper_timepiece.timepiece as timepiece
from juniper_timepiece.timepiece import (
    _get_cached_sun_events,
    get_clock_data,
    get_location_config,
)


def test_get_location_config_from_file(tmp_path, monkeypatch):
    """Test loading configuration directly from an existing config.json file."""
    config_data = {
        "latitude": 29.4241,
        "longitude": -98.4936,
        "city": "San Antonio Station",
    }
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps(config_data))

    monkeypatch.setattr(timepiece, "CONFIG_FILE", str(config_file))
    cfg = get_location_config()

    assert cfg["latitude"] == 29.4241
    assert cfg["longitude"] == -98.4936
    assert cfg["city"] == "San Antonio Station"


@patch("requests.get")
def test_get_location_config_fallback(mock_get, tmp_path, monkeypatch):
    """Test fallback geolocation API when config file does not exist."""
    non_existent_file = tmp_path / "non_existent_config.json"
    monkeypatch.setattr(timepiece, "CONFIG_FILE", str(non_existent_file))

    mock_response = MagicMock()
    mock_response.json.return_value = {
        "status": "success",
        "lat": 30.2672,
        "lon": -97.7431,
        "city": "Austin",
    }
    mock_get.return_value = mock_response

    cfg = get_location_config()
    assert cfg["latitude"] == 30.2672
    assert cfg["longitude"] == -97.7431
    assert cfg["city"] == "Austin"


def test_get_clock_data_structure():
    """Verify that get_clock_data returns all expected keys and nested objects."""
    data = get_clock_data()

    required_keys = [
        "server_time",
        "tick",
        "is_pm",
        "location",
        "season_progress",
        "moon_progress",
        "standard",
        "roman",
        "solar",
        "tidal",
    ]
    for key in required_keys:
        assert key in data

    for clock_type in ["standard", "roman", "solar", "tidal"]:
        assert "h" in data[clock_type]
        assert "m" in data[clock_type]
        assert "s" in data[clock_type]


def test_get_clock_data_value_ranges():
    """Verify that returned clock hands and progress values fall within valid bounds."""
    data = get_clock_data()

    assert 0.0 <= data["season_progress"] <= 1.0
    assert 0.0 <= data["moon_progress"] <= 1.0

    for clock_type in ["standard", "roman", "solar", "tidal"]:
        h = data[clock_type]["h"]
        m = data[clock_type]["m"]
        s = data[clock_type]["s"]

        assert 0.0 <= h < 12.0
        assert 0.0 <= m < 60.0
        assert 0.0 <= s < 60.0


def test_get_clock_data_with_fixed_timestamp():
    """Ensure get_clock_data produces deterministic outputs when given a fixed timestamp."""
    fixed_time = datetime(2026, 6, 21, 12, 0, 0, tzinfo=timezone.utc)
    data = get_clock_data(now_utc=fixed_time)

    assert data["server_time"] == fixed_time.timestamp()
    assert data["tick"] == int(fixed_time.timestamp())


def test_solar_events_lru_caching():
    """Verify that repeated calls for the same calendar date hit the LRU cache."""
    _get_cached_sun_events.cache_clear()

    date_key = "2026-10-07"
    lat, lon = 29.42, -98.49

    _get_cached_sun_events(date_key, lat, lon)
    info_first = _get_cached_sun_events.cache_info()
    assert info_first.hits == 0

    _get_cached_sun_events(date_key, lat, lon)
    info_second = _get_cached_sun_events.cache_info()
    assert info_second.hits == 1
