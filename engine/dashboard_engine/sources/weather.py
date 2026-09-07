"""Source meteo (OpenWeatherMap : temps courant + previsions 3 h)."""

from __future__ import annotations

import httpx

from dashboard_engine.config import WeatherConfig
from dashboard_engine.models import ForecastPoint, Weather
from dashboard_engine.sources.base import DisabledSource, Source

CURRENT_URL = "https://api.openweathermap.org/data/2.5/weather"
FORECAST_URL = "https://api.openweathermap.org/data/2.5/forecast"

MS_TO_KPH = 3.6


def parse_current(payload: dict) -> Weather:
    """Convertit la reponse `/weather` en modele interne (fonction pure, testable)."""
    main = payload.get("main") or {}
    wind = payload.get("wind") or {}
    sys_block = payload.get("sys") or {}
    conditions = payload.get("weather") or [{}]
    first = conditions[0] if conditions else {}
    return Weather(
        city=payload.get("name") or "",
        temp_c=float(main.get("temp", 0.0)),
        feels_like_c=float(main.get("feels_like", 0.0)),
        temp_min_c=float(main.get("temp_min", 0.0)),
        temp_max_c=float(main.get("temp_max", 0.0)),
        description=(first.get("description") or "").capitalize(),
        icon=first.get("icon") or "",
        humidity=int(main.get("humidity", 0)),
        wind_kph=round(float(wind.get("speed", 0.0)) * MS_TO_KPH, 1),
        sunrise=int(sys_block.get("sunrise", 0)),
        sunset=int(sys_block.get("sunset", 0)),
    )


def parse_forecast(payload: dict, limit: int) -> list[ForecastPoint]:
    """Extrait les `limit` premiers creneaux de la reponse `/forecast`."""
    points: list[ForecastPoint] = []
    for slot in (payload.get("list") or [])[:limit]:
        conditions = slot.get("weather") or [{}]
        points.append(
            ForecastPoint(
                ts=int(slot.get("dt", 0)),
                temp_c=round(float((slot.get("main") or {}).get("temp", 0.0)), 1),
                icon=(conditions[0] if conditions else {}).get("icon") or "",
            )
        )
    return points


class WeatherSource(Source[Weather]):
    name = "weather"

    def __init__(self, config: WeatherConfig) -> None:
        super().__init__(config.interval_s, Weather())
        self._config = config
        self._client = httpx.AsyncClient(timeout=10.0)

    def _params(self) -> dict[str, str]:
        return {
            "q": self._config.city,
            "appid": self._config.api_key,
            "units": self._config.units,
            "lang": self._config.lang,
        }

    async def fetch(self) -> Weather:
        response = await self._client.get(CURRENT_URL, params=self._params())
        response.raise_for_status()
        weather = parse_current(response.json())

        if self._config.forecast_points > 0:
            forecast = await self._client.get(FORECAST_URL, params=self._params())
            if forecast.is_success:
                weather.forecast = parse_forecast(forecast.json(), self._config.forecast_points)
        return weather

    async def close(self) -> None:
        await self._client.aclose()


def build_weather_source(config: WeatherConfig) -> Source[Weather]:
    if not config.enabled:
        return DisabledSource("weather", Weather(), "module desactive en configuration")
    if not config.api_key:
        return DisabledSource("weather", Weather(), "cle API OpenWeatherMap manquante")
    return WeatherSource(config)
