# Copyright (C) 2026 Vicente José Leiva Escárate
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import hashlib
import math
import re
import urllib.parse
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.domain.conditions import from_nws_text
from app.i18n import N_
from app.models import (
    CurrentConditions,
    DailyForecast,
    HourlyForecast,
    Location,
    ProviderMetadata,
    WeatherAlert,
    WeatherBundle,
)
from app.providers.base import CoverageError, ProviderError, WeatherProvider
from app.providers.http import JsonHttpClient, http_client


class NwsProvider(WeatherProvider):
    metadata = ProviderMetadata(
        provider_id="nws",
        name="US National Weather Service",
        attribution="Weather data and official alerts by the U.S. National Weather Service",
        attribution_url="https://www.weather.gov/",
        license_name="U.S. government public data",
        coverage="United States and territories",
        forecast_days=7,
        base_weight=1.0,
        official_country_codes=("US", "PR", "VI", "GU", "AS", "MP"),
    )

    def __init__(self, client: JsonHttpClient = http_client):
        self.client = client

    def supports(self, location: Location) -> bool:
        return location.country_code.upper() in self.metadata.official_country_codes

    def fetch(self, location: Location) -> WeatherBundle:
        if not self.supports(location):
            raise CoverageError("NWS is only available in the United States and its territories")
        points = self.client.get_json(
            f"https://api.weather.gov/points/{location.latitude:.4f},{location.longitude:.4f}"
        )
        properties = points.get("properties", {})
        forecast_url = self._forecast_endpoint(properties.get("forecast"))
        hourly_url = self._forecast_endpoint(properties.get("forecastHourly"))
        if not forecast_url or not hourly_url:
            raise ProviderError("NWS did not provide forecast endpoints for this location")
        with ThreadPoolExecutor(max_workers=3) as executor:
            daily_future = executor.submit(self.client.get_json, forecast_url)
            hourly_future = executor.submit(self.client.get_json, hourly_url)
            alerts_future = executor.submit(
                self.client.get_json,
                "https://api.weather.gov/alerts/active",
                {"point": f"{location.latitude:.4f},{location.longitude:.4f}"},
            )
            daily_data = daily_future.result()
            hourly_data = hourly_future.result()
            alert_feed_unavailable = False
            try:
                alerts_data = alerts_future.result()
                if not isinstance(alerts_data.get("features"), list):
                    alerts_data = {}
                    alert_feed_unavailable = True
            except Exception:
                # Official alerts are valuable, but their outage must not hide a valid forecast.
                alerts_data = {}
                alert_feed_unavailable = True
        bundle = self.parse(location, daily_data, hourly_data, alerts_data)
        if alert_feed_unavailable:
            bundle.alerts.insert(
                0,
                WeatherAlert(
                    alert_id="nws-alert-feed-unavailable",
                    title=N_("Official alert feed unavailable"),
                    description=N_(
                        "NWS weather data is available, but its active-alert request failed. Check local authorities directly."
                    ),
                    severity="unknown",
                    source_name="US National Weather Service",
                    source_url=self.metadata.attribution_url,
                    official=False,
                    kind="service-notice",
                ),
            )
        return bundle

    @staticmethod
    def _forecast_endpoint(value: Any) -> str:
        text = str(value or "")
        parsed = urllib.parse.urlparse(text)
        if (
            parsed.scheme != "https"
            or parsed.hostname != "api.weather.gov"
            or parsed.username
            or parsed.password
        ):
            raise ProviderError("NWS returned an invalid forecast endpoint")
        return text

    @staticmethod
    def _temperature_c(value: Any, unit: str) -> Optional[float]:
        try:
            temperature = float(value)
        except (TypeError, ValueError):
            return None
        if not math.isfinite(temperature):
            return None
        converted = (
            (temperature - 32.0) * 5.0 / 9.0
            if str(unit).upper() == "F"
            else temperature
        )
        return converted if -100.0 <= converted <= 70.0 else None

    @staticmethod
    def _number(value: Any, minimum: float, maximum: float) -> Optional[float]:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        return number if math.isfinite(number) and minimum <= number <= maximum else None

    @staticmethod
    def _safe_source_url(value: Any) -> str:
        text = str(value or "")
        parsed = urllib.parse.urlparse(text)
        trusted_host = bool(
            parsed.hostname
            and (
                parsed.hostname == "weather.gov"
                or parsed.hostname.endswith(".weather.gov")
            )
        )
        return (
            text
            if parsed.scheme == "https"
            and trusted_host
            and not parsed.username
            and not parsed.password
            else "https://www.weather.gov/"
        )

    @staticmethod
    def _wind_kmh(value: str) -> Optional[float]:
        matches = re.findall(r"([0-9]+(?:\.[0-9]+)?)", value or "")
        if not matches:
            return None
        speed = max(float(item) for item in matches)
        return speed * 1.609344 if "mph" in value.lower() else speed

    @staticmethod
    def _direction_degrees(value: str) -> Optional[float]:
        mapping = {
            "N": 0.0, "NNE": 22.5, "NE": 45.0, "ENE": 67.5,
            "E": 90.0, "ESE": 112.5, "SE": 135.0, "SSE": 157.5,
            "S": 180.0, "SSW": 202.5, "SW": 225.0, "WSW": 247.5,
            "W": 270.0, "WNW": 292.5, "NW": 315.0, "NNW": 337.5,
        }
        return mapping.get((value or "").upper())

    @classmethod
    def parse(
        cls,
        location: Location,
        daily_data: Dict[str, Any],
        hourly_data: Dict[str, Any],
        alerts_data: Optional[Dict[str, Any]] = None,
    ) -> WeatherBundle:
        daily_periods = daily_data.get("properties", {}).get("periods", [])
        hourly_periods = hourly_data.get("properties", {}).get("periods", [])
        if not hourly_periods:
            raise ProviderError("NWS returned no hourly forecast")

        valid_hourly = []
        for period in hourly_periods[:48]:
            temperature = cls._temperature_c(
                period.get("temperature"),
                period.get("temperatureUnit", "F"),
            )
            if temperature is not None:
                valid_hourly.append((period, temperature))
        if not valid_hourly:
            raise ProviderError("NWS returned no valid hourly temperatures")

        first, first_temp = valid_hourly[0]
        current = CurrentConditions(
            observed_at=str(first.get("startTime", "")),
            temperature_c=first_temp,
            apparent_temperature_c=None,
            condition_code=from_nws_text(str(first.get("shortForecast", ""))),
            humidity_percent=cls._number(
                (first.get("relativeHumidity") or {}).get("value"),
                0.0,
                100.0,
            ),
            wind_speed_kmh=cls._wind_kmh(str(first.get("windSpeed", ""))),
            wind_direction_deg=cls._direction_degrees(str(first.get("windDirection", ""))),
            precipitation_mm=None,
            is_forecast=True,
        )

        hourly: List[HourlyForecast] = []
        for period, period_temperature in valid_hourly:
            hourly.append(
                HourlyForecast(
                    time=str(period.get("startTime", "")),
                    temperature_c=period_temperature,
                    condition_code=from_nws_text(str(period.get("shortForecast", ""))),
                    precipitation_probability=cls._number(
                        (period.get("probabilityOfPrecipitation") or {}).get("value"),
                        0.0,
                        100.0,
                    ),
                    wind_speed_kmh=cls._wind_kmh(str(period.get("windSpeed", ""))),
                )
            )

        grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for period in daily_periods:
            date_key = str(period.get("startTime", ""))[:10]
            if date_key:
                grouped[date_key].append(period)

        daily: List[DailyForecast] = []
        for date_key in sorted(grouped)[:7]:
            periods = grouped[date_key]
            temperatures = [
                (period, cls._temperature_c(
                    period.get("temperature"),
                    period.get("temperatureUnit", "F"),
                ))
                for period in periods
            ]
            temperatures = [(period, value) for period, value in temperatures if value is not None]
            if not temperatures:
                continue
            has_day_flags = any("isDaytime" in period for period, _value in temperatures)
            if has_day_flags:
                maximum_values = [value for period, value in temperatures if period.get("isDaytime")]
                minimum_values = [value for period, value in temperatures if not period.get("isDaytime")]
                maximum = max(maximum_values) if maximum_values else None
                minimum = min(minimum_values) if minimum_values else None
            else:
                all_values = [value for _period, value in temperatures]
                maximum = max(all_values)
                minimum = min(all_values)
            rain = [
                (period.get("probabilityOfPrecipitation") or {}).get("value")
                for period in periods
            ]
            rain = [cls._number(value, 0.0, 100.0) for value in rain]
            rain = [value for value in rain if value is not None]
            wind_values = [
                cls._wind_kmh(str(period.get("windSpeed", "")))
                for period in periods
            ]
            wind_values = [value for value in wind_values if value is not None]
            representative = next(
                (period for period in periods if period.get("isDaytime")),
                periods[0],
            )
            daily.append(
                DailyForecast(
                    date=date_key,
                    temperature_max_c=maximum,
                    temperature_min_c=minimum,
                    condition_code=from_nws_text(str(representative.get("shortForecast", ""))),
                    precipitation_probability=max(rain) if rain else None,
                    wind_speed_max_kmh=max(wind_values) if wind_values else None,
                )
            )

        alerts: List[WeatherAlert] = []
        for feature in (alerts_data or {}).get("features", []):
            if not isinstance(feature, dict):
                continue
            properties = feature.get("properties") or {}
            if not isinstance(properties, dict):
                continue
            title = str(properties.get("event", "")).strip()[:240]
            if not title:
                continue
            fallback_id = hashlib.sha256(
                "|".join(
                    str(properties.get(key, ""))
                    for key in ("event", "onset", "expires", "areaDesc")
                ).encode("utf-8")
            ).hexdigest()
            alerts.append(
                WeatherAlert(
                    alert_id=str(feature.get("id") or properties.get("id") or fallback_id),
                    title=title,
                    description=str(properties.get("description", ""))[:20_000],
                    severity=str(properties.get("severity", "unknown")).lower()[:40],
                    urgency=str(properties.get("urgency", "unknown")).lower()[:40],
                    onset=properties.get("onset"),
                    expires=properties.get("expires"),
                    instruction=(
                        str(properties["instruction"])[:20_000]
                        if properties.get("instruction")
                        else None
                    ),
                    source_name=str(
                        properties.get("senderName", "US National Weather Service")
                    )[:200],
                    source_url=cls._safe_source_url(
                        properties.get("web") or feature.get("id")
                    ),
                    official=True,
                    kind="official",
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
            alerts=alerts,
            attribution=cls.metadata.attribution,
            attribution_url=cls.metadata.attribution_url,
            source_ids=[cls.metadata.provider_id],
        )
