import logging
import httpx

logger = logging.getLogger(__name__)

# Simple in-memory geocoding cache
_GEO_CACHE = {}

SCHEMA = {
    "name": "weather",
    "description": "Get current weather or forecast for a city. Omit days for current weather, set 1-7 for forecast.",
    "parameters": {
        "type": "object",
        "properties": {
            "city": {
                "type": "string",
                "description": "City name, e.g. 'London' or 'New York'",
            },
            "days": {
                "type": "integer",
                "description": "Number of forecast days (1-7). Omit or set 0 for current weather only.",
            },
        },
        "required": ["city"],
    },
}


def _geocode(city):
    """Look up lat/lon for a city, with cache."""
    if city.lower() in _GEO_CACHE:
        return _GEO_CACHE[city.lower()]
    try:
        geo = httpx.get(
            "https://geocoding-api.open-meteo.com/v1/search",
            params={"name": city, "count": 1},
            timeout=10,
        ).json()
        results = geo.get("results")
        if not results:
            return None
        _GEO_CACHE[city.lower()] = results[0]
        return results[0]
    except Exception as e:
        logger.warning("Geocode failed for '%s': %s", city, e)
        return None


def run(city, days=0):
    """Free weather lookup via Open-Meteo (no API key required)."""
    try:
        location = _geocode(city)
        if not location:
            return f"Couldn't find a location named '{city}'."
        lat, lon = location["latitude"], location["longitude"]
        place = location.get("name", city)
        country = location.get("country", "")

        params = {
            "latitude": lat,
            "longitude": lon,
            "timezone": "auto",
        }

        if days and days > 0:
            params["daily"] = "temperature_2m_max,temperature_2m_min,precipitation_sum,weather_code"
            params["forecast_days"] = min(days, 7)
        else:
            params["current_weather"] = True

        wx = httpx.get(
            "https://api.open-meteo.com/v1/forecast",
            params=params,
            timeout=10,
        ).json()

        current = wx.get("current_weather")
        if current:
            return (
                f"Weather in {place}, {country}: {current.get('temperature')}°C, "
                f"wind {current.get('windspeed')} km/h."
            )

        daily = wx.get("daily")
        if daily:
            lines = [f"Forecast for {place}, {country}:"]
            for i in range(len(daily["time"])):
                lines.append(
                    f"  {daily['time'][i]}: {daily['temperature_2m_min'][i]}–{daily['temperature_2m_max'][i]}°C, "
                    f"precip {daily['precipitation_sum'][i]}mm"
                )
            return "\n".join(lines)

        return "Weather data unavailable right now."
    except Exception as e:
        logger.exception("Weather lookup failed for '%s'", city)
        return f"Weather lookup failed: {e}"
