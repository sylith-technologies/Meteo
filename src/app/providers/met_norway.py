# Copyright (C) 2026 Vicente José Leiva Escárate
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import math
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.domain.conditions import from_met_symbol
from app.models import (
    CurrentConditions,
    DailyForecast,
    HourlyForecast,
    Location,
    ProviderMetadata,
    WeatherBundle,
)
from app.providers.base import ProviderError, WeatherProvider
from app.paths import cache_dir
from app.providers.http import ConditionalJsonClient, JsonHttpClient, http_client


class MetNorwayProvider(WeatherProvider):
    FORECAST_URL = "https://api.met.no/weatherapi/locationforecast/2.0/compact"
    metadata = ProviderMetadata(
        provider_id="met-norway",
        name="MET Norway",
        attribution="Weather data by the Norwegian Meteorological Institute",
        attribution_url="https://api.met.no/",
        license_name="CC BY 4.0",
        coverage="global forecast; official authority in Norway",
        forecast_days=9,
        base_weight=0.95,
        official_country_codes=("NO", "SJ"),
    )

    def __init__(
        self,
        client: JsonHttpClient = http_client,
        conditional_client: Optional[ConditionalJsonClient] = None,
    ):
        self.client = client
        self.conditional_client = conditional_client or ConditionalJsonClient(
            client,
            cache_dir() / "http" / "met-norway",
        )

    def fetch(self, location: Location) -> WeatherBundle:
        data = self.conditional_client.get_json(
            self.FORECAST_URL,
            self._params(location),
        )
        return self.parse(location, data)

    @staticmethod
    def _params(location: Location) -> Dict[str, float]:
        return {
            "lat": round(location.latitude, 4),
            "lon": round(location.longitude, 4),
        }

    def clear_cache(self, location: Optional[Location] = None) -> None:
        if location is None:
            self.conditional_client.clear()
        else:
            self.conditional_client.clear(self.FORECAST_URL, self._params(location))

    @staticmethod
    def _local_time(value: str, timezone_name: str) -> datetime:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        try:
            return parsed.astimezone(ZoneInfo(timezone_name))
        except ZoneInfoNotFoundError:
            return parsed

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

    @staticmethod
    def _forecast_period(item_data: Dict[str, Any]) -> tuple[Dict[str, Any], int]:
        for key, duration in (("next_1_hours", 1), ("next_6_hours", 6), ("next_12_hours", 12)):
            period = item_data.get(key)
            if isinstance(period, dict) and period:
                return period, duration
        return {}, 0

    @staticmethod
    def _add_precipitation_by_day(
        daily_values: Dict[str, Dict[str, Any]],
        start: datetime,
        duration_hours: int,
        amount_mm: float,
    ) -> None:
        """Splits a multi-hour amount at local-midnight boundaries.

        MET gives one accumulated amount for the whole interval. A uniform
        split is the only honest daily approximation when the provider does not
        expose the sub-interval distribution.
        """

        end = start + timedelta(hours=duration_hours)
        cursor = start
        while cursor < end:
            next_midnight = datetime.combine(
                cursor.date() + timedelta(days=1),
                datetime.min.time(),
                tzinfo=cursor.tzinfo,
            )
            segment_end = min(end, next_midnight)
            fraction = (segment_end - cursor).total_seconds() / (duration_hours * 3600)
            daily_values[cursor.date().isoformat()]["precip"].append(amount_mm * fraction)
            cursor = segment_end

    @classmethod
    def parse(cls, location: Location, data: Dict[str, Any]) -> WeatherBundle:
        series = data.get("properties", {}).get("timeseries", [])
        if not series:
            raise ProviderError("MET Norway returned no forecast timeseries")

        hourly: List[HourlyForecast] = []
        daily_values: Dict[str, Dict[str, Any]] = defaultdict(
            lambda: {"temps": [], "conditions": [], "precip": [], "wind": []}
        )
        current_source = None
        precipitation_covered_until: Optional[datetime] = None

        for item in series:
            try:
                local_time = cls._local_time(item.get("time", ""), location.timezone)
            except (TypeError, ValueError):
                continue
            item_data = item.get("data", {})
            instant = item_data.get("instant", {}).get("details", {})
            next_period, period_hours = cls._forecast_period(item_data)
            symbol = next_period.get("summary", {}).get("symbol_code", "unknown")
            details = next_period.get("details", {})
            condition = from_met_symbol(symbol)
            temperature = cls._number(instant.get("air_temperature"), -100.0, 70.0)
            if temperature is None:
                continue
            precipitation = cls._number(
                details.get("precipitation_amount"), 0.0, 5000.0
            )
            wind_speed = cls._number(instant.get("wind_speed"), 0.0, 150.0)
            if current_source is None:
                current_source = (local_time, instant, next_period, temperature)

            if len(hourly) < 48:
                hourly.append(
                    HourlyForecast(
                        time=local_time.isoformat(timespec="minutes"),
                        temperature_c=temperature,
                        condition_code=condition,
                        precipitation_probability=cls._number(
                            details.get("probability_of_precipitation"),
                            0.0,
                            100.0,
                        ),
                        precipitation_mm=precipitation,
                        wind_speed_kmh=wind_speed * 3.6 if wind_speed is not None else None,
                    )
                )

            date_key = local_time.date().isoformat()
            grouped = daily_values[date_key]
            grouped["temps"].append(temperature)
            grouped["conditions"].append(condition)
            if precipitation is not None and period_hours:
                if precipitation_covered_until is None or local_time >= precipitation_covered_until:
                    cls._add_precipitation_by_day(
                        daily_values,
                        local_time,
                        period_hours,
                        precipitation,
                    )
                    precipitation_covered_until = local_time + timedelta(hours=period_hours)
            if wind_speed is not None:
                grouped["wind"].append(wind_speed * 3.6)

        if current_source is None:
            raise ProviderError("MET Norway returned no valid temperature values")
        first_time, first_instant, first_period, current_temp = current_source
        first_symbol = first_period.get("summary", {}).get("symbol_code", "unknown")
        first_wind_speed = cls._number(first_instant.get("wind_speed"), 0.0, 150.0)
        current = CurrentConditions(
            observed_at=first_time.isoformat(timespec="minutes"),
            temperature_c=current_temp,
            apparent_temperature_c=None,
            condition_code=from_met_symbol(first_symbol),
            humidity_percent=cls._number(
                first_instant.get("relative_humidity"), 0.0, 100.0
            ),
            pressure_hpa=cls._number(
                first_instant.get("air_pressure_at_sea_level"), 800.0, 1100.0
            ),
            wind_speed_kmh=(
                first_wind_speed * 3.6 if first_wind_speed is not None else None
            ),
            wind_direction_deg=cls._number(
                first_instant.get("wind_from_direction"), 0.0, 360.0
            ),
            precipitation_mm=cls._number(
                first_period.get("details", {}).get("precipitation_amount"),
                0.0,
                5000.0,
            ),
            is_forecast=True,
        )

        daily: List[DailyForecast] = []
        for date_key in sorted(daily_values)[:9]:
            values = daily_values[date_key]
            if not values["temps"]:
                continue
            conditions = values["conditions"]
            daily.append(
                DailyForecast(
                    date=date_key,
                    temperature_max_c=max(values["temps"]),
                    temperature_min_c=min(values["temps"]),
                    condition_code=Counter(conditions).most_common(1)[0][0]
                    if conditions
                    else "unknown",
                    precipitation_sum_mm=(
                        round(sum(values["precip"]), 2)
                        if values["precip"]
                        else None
                    ),
                    wind_speed_max_kmh=max(values["wind"]) if values["wind"] else None,
                )
            )

        return WeatherBundle(
            provider_id=cls.metadata.provider_id,
            provider_name=cls.metadata.name,
            location=location,
            retrieved_at=datetime.now(timezone.utc).isoformat(),
            timezone=location.timezone,
            current=current,
            hourly=hourly,
            daily=daily,
            attribution=cls.metadata.attribution,
            attribution_url=cls.metadata.attribution_url,
            source_ids=[cls.metadata.provider_id],
        )
