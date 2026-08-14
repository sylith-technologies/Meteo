# Copyright (C) 2026 Vicente José Leiva Escárate
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import math
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.domain.conditions import from_wmo
from app.i18n import N_
from app.models import (
    AirQuality,
    CurrentConditions,
    DailyForecast,
    HourlyForecast,
    Location,
    ProviderMetadata,
    WeatherAlert,
    WeatherBundle,
)
from app.providers.base import ProviderError, WeatherProvider
from app.providers.http import JsonHttpClient, http_client


class OpenMeteoProvider(WeatherProvider):
    metadata = ProviderMetadata(
        provider_id="open-meteo",
        name="Open-Meteo",
        attribution="Weather data by Open-Meteo",
        attribution_url="https://open-meteo.com/",
        license_name="CC BY 4.0",
        coverage="global",
        forecast_days=15,
        base_weight=1.0,
    )

    def __init__(self, client: JsonHttpClient = http_client):
        self.client = client

    def fetch(self, location: Location) -> WeatherBundle:
        weather_params = {
            "latitude": location.latitude,
            "longitude": location.longitude,
            "current": (
                "temperature_2m,relative_humidity_2m,apparent_temperature,"
                "precipitation,weather_code,pressure_msl,wind_speed_10m,"
                "wind_direction_10m,wind_gusts_10m"
            ),
            "hourly": (
                "temperature_2m,precipitation_probability,precipitation,weather_code,"
                "wind_speed_10m,wind_gusts_10m,visibility"
            ),
            "daily": (
                "weather_code,temperature_2m_max,temperature_2m_min,"
                "precipitation_probability_max,precipitation_sum,wind_speed_10m_max,"
                "wind_gusts_10m_max,uv_index_max,sunrise,sunset"
            ),
            "forecast_days": 15,
            "forecast_hours": 48,
            "timezone": "auto",
        }
        air_params = {
            "latitude": location.latitude,
            "longitude": location.longitude,
            "current": "us_aqi,european_aqi,pm2_5,pm10,ozone,nitrogen_dioxide",
            "timezone": "auto",
        }
        with ThreadPoolExecutor(max_workers=2) as executor:
            weather_future = executor.submit(
                self.client.get_json,
                "https://api.open-meteo.com/v1/forecast",
                weather_params,
            )
            air_future = executor.submit(
                self.client.get_json,
                "https://air-quality-api.open-meteo.com/v1/air-quality",
                air_params,
            )
            data = weather_future.result()
            try:
                air_data: Optional[Dict[str, Any]] = air_future.result()
            except Exception:
                # Air quality is optional and must never hide the weather forecast.
                air_data = None
        return self.parse(location, data, air_data)

    @staticmethod
    def _at(values: List[Any], index: int, default: Any = None) -> Any:
        return values[index] if index < len(values) else default

    @staticmethod
    def _number(
        value: Any,
        minimum: float = -math.inf,
        maximum: float = math.inf,
    ) -> Optional[float]:
        if value is None:
            return None
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        return number if math.isfinite(number) and minimum <= number <= maximum else None

    @classmethod
    def _required_number(
        cls,
        value: Any,
        field: str,
        minimum: float = -math.inf,
        maximum: float = math.inf,
    ) -> float:
        number = cls._number(value, minimum, maximum)
        if number is None:
            raise ProviderError(f"Open-Meteo did not return a valid {field}")
        return number

    @staticmethod
    def _condition(value: Any) -> str:
        try:
            return from_wmo(int(value))
        except (TypeError, ValueError):
            return from_wmo(-1)

    @classmethod
    def parse(
        cls,
        location: Location,
        data: Dict[str, Any],
        air_data: Optional[Dict[str, Any]] = None,
    ) -> WeatherBundle:
        current_data = data.get("current") or {}
        hourly_data = data.get("hourly") or {}
        daily_data = data.get("daily") or {}
        hourly_visibility = hourly_data.get("visibility") or []
        current_temperature = cls._required_number(
            current_data.get("temperature_2m"),
            "current temperature",
            -100.0,
            70.0,
        )
        apparent_temperature = cls._number(
            current_data.get("apparent_temperature"),
            -120.0,
            80.0,
        )

        current = CurrentConditions(
            observed_at=str(current_data.get("time", "")),
            temperature_c=current_temperature,
            apparent_temperature_c=apparent_temperature,
            condition_code=cls._condition(current_data.get("weather_code")),
            humidity_percent=cls._number(
                current_data.get("relative_humidity_2m"), 0.0, 100.0
            ),
            pressure_hpa=cls._number(current_data.get("pressure_msl"), 800.0, 1100.0),
            wind_speed_kmh=cls._number(current_data.get("wind_speed_10m"), 0.0, 500.0),
            wind_gust_kmh=cls._number(current_data.get("wind_gusts_10m"), 0.0, 500.0),
            wind_direction_deg=cls._number(
                current_data.get("wind_direction_10m"), 0.0, 360.0
            ),
            precipitation_mm=cls._number(current_data.get("precipitation"), 0.0, 1000.0),
            visibility_km=(
                visibility_metres / 1000.0
                if hourly_visibility
                and (
                    visibility_metres := cls._number(
                        hourly_visibility[0], 0.0, 1_000_000.0
                    )
                )
                is not None
                else None
            ),
        )

        hourly: List[HourlyForecast] = []
        times = hourly_data.get("time") or []
        for index, time_value in enumerate(times[:48]):
            temperature = cls._number(
                cls._at(hourly_data.get("temperature_2m") or [], index),
                -100.0,
                70.0,
            )
            if temperature is None:
                continue
            hourly.append(
                HourlyForecast(
                    time=str(time_value),
                    temperature_c=temperature,
                    condition_code=cls._condition(
                        cls._at(hourly_data.get("weather_code") or [], index)
                    ),
                    precipitation_probability=cls._number(
                        cls._at(hourly_data.get("precipitation_probability") or [], index),
                        0.0,
                        100.0,
                    ),
                    precipitation_mm=cls._number(
                        cls._at(hourly_data.get("precipitation") or [], index),
                        0.0,
                        1000.0,
                    ),
                    wind_speed_kmh=cls._number(
                        cls._at(hourly_data.get("wind_speed_10m") or [], index),
                        0.0,
                        500.0,
                    ),
                    wind_gust_kmh=cls._number(
                        cls._at(hourly_data.get("wind_gusts_10m") or [], index),
                        0.0,
                        500.0,
                    ),
                )
            )

        daily: List[DailyForecast] = []
        dates = daily_data.get("time") or []
        for index, date_value in enumerate(dates[:15]):
            maximum = cls._number(
                cls._at(daily_data.get("temperature_2m_max") or [], index),
                -100.0,
                70.0,
            )
            minimum = cls._number(
                cls._at(daily_data.get("temperature_2m_min") or [], index),
                -100.0,
                70.0,
            )
            if maximum is None and minimum is None:
                continue
            daily.append(
                DailyForecast(
                    date=str(date_value),
                    temperature_max_c=maximum,
                    temperature_min_c=minimum,
                    condition_code=cls._condition(
                        cls._at(daily_data.get("weather_code") or [], index)
                    ),
                    precipitation_probability=cls._number(
                        cls._at(
                            daily_data.get("precipitation_probability_max") or [],
                            index,
                        ),
                        0.0,
                        100.0,
                    ),
                    precipitation_sum_mm=cls._number(
                        cls._at(daily_data.get("precipitation_sum") or [], index),
                        0.0,
                        5000.0,
                    ),
                    wind_speed_max_kmh=cls._number(
                        cls._at(daily_data.get("wind_speed_10m_max") or [], index),
                        0.0,
                        500.0,
                    ),
                    wind_gust_max_kmh=cls._number(
                        cls._at(daily_data.get("wind_gusts_10m_max") or [], index),
                        0.0,
                        500.0,
                    ),
                    uv_index_max=cls._number(
                        cls._at(daily_data.get("uv_index_max") or [], index),
                        0.0,
                        30.0,
                    ),
                    sunrise=cls._at(daily_data.get("sunrise") or [], index),
                    sunset=cls._at(daily_data.get("sunset") or [], index),
                )
            )

        air_quality = None
        if air_data and air_data.get("current"):
            air = air_data["current"]
            candidate = AirQuality(
                observed_at=str(air.get("time", "")),
                us_aqi=cls._number(air.get("us_aqi"), 0.0, 1000.0),
                european_aqi=cls._number(air.get("european_aqi"), 0.0, 1000.0),
                pm2_5=cls._number(air.get("pm2_5"), 0.0, 100_000.0),
                pm10=cls._number(air.get("pm10"), 0.0, 100_000.0),
                ozone=cls._number(air.get("ozone"), 0.0, 100_000.0),
                nitrogen_dioxide=cls._number(
                    air.get("nitrogen_dioxide"), 0.0, 100_000.0
                ),
                provider_name="Open-Meteo / CAMS",
                attribution_url="https://open-meteo.com/en/docs/air-quality-api",
            )
            if any(
                value is not None
                for value in (
                    candidate.us_aqi,
                    candidate.european_aqi,
                    candidate.pm2_5,
                    candidate.pm10,
                    candidate.ozone,
                    candidate.nitrogen_dioxide,
                )
            ):
                air_quality = candidate

        alerts = cls._forecast_signals(location, hourly, daily)
        return WeatherBundle(
            provider_id=cls.metadata.provider_id,
            provider_name=cls.metadata.name,
            location=location,
            retrieved_at=datetime.now(timezone.utc).isoformat(),
            timezone=str(data.get("timezone", location.timezone)),
            current=current,
            hourly=hourly,
            daily=daily,
            air_quality=air_quality,
            alerts=alerts,
            attribution=cls.metadata.attribution,
            attribution_url=cls.metadata.attribution_url,
            source_ids=[cls.metadata.provider_id],
        )

    @classmethod
    def _forecast_signals(
        cls,
        location: Location,
        hourly: List[HourlyForecast],
        daily: List[DailyForecast],
    ) -> List[WeatherAlert]:
        """Creates clearly-labelled forecast signals, never official warnings."""
        signals: List[WeatherAlert] = []
        if any(hour.condition_code == "thunderstorm" for hour in hourly[:48]):
            signals.append(
                WeatherAlert(
                    alert_id=f"open-meteo-thunder-{location.key}",
                    title=N_("Thunderstorm signal in the forecast"),
                    description=N_(
                        "A forecast model indicates thunderstorm conditions within 48 hours."
                    ),
                    severity="moderate",
                    source_name="Open-Meteo",
                    source_url=cls.metadata.attribution_url,
                    official=False,
                    kind="forecast-signal",
                )
            )
        if daily and (daily[0].precipitation_sum_mm or 0.0) >= 50.0:
            signals.append(
                WeatherAlert(
                    alert_id=f"open-meteo-heavy-rain-{location.key}",
                    title=N_("Heavy rain signal in the forecast"),
                    description=N_(
                        "The forecast indicates at least 50 mm of precipitation today."
                    ),
                    severity="moderate",
                    source_name="Open-Meteo",
                    source_url=cls.metadata.attribution_url,
                    official=False,
                    kind="forecast-signal",
                )
            )
        if any((hour.wind_gust_kmh or 0.0) >= 70.0 for hour in hourly[:48]):
            signals.append(
                WeatherAlert(
                    alert_id=f"open-meteo-wind-{location.key}",
                    title=N_("Strong wind signal in the forecast"),
                    description=N_(
                        "Forecast wind gusts reach or exceed 70 km/h within 48 hours."
                    ),
                    severity="moderate",
                    source_name="Open-Meteo",
                    source_url=cls.metadata.attribution_url,
                    official=False,
                    kind="forecast-signal",
                )
            )
        return signals
