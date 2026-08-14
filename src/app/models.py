# Copyright (C) 2026 Vicente José Leiva Escárate
# SPDX-License-Identifier: GPL-3.0-or-later

"""Normalized, provider-independent domain models used by Meteo."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class Location:
    name: str
    latitude: float
    longitude: float
    country_code: str = ""
    country: str = ""
    admin1: str = ""
    timezone: str = "auto"

    def __post_init__(self) -> None:
        try:
            latitude = float(self.latitude)
            longitude = float(self.longitude)
        except (TypeError, ValueError) as error:
            raise ValueError("Location coordinates are invalid") from error
        if (
            not math.isfinite(latitude)
            or not math.isfinite(longitude)
            or not -90.0 <= latitude <= 90.0
            or not -180.0 <= longitude <= 180.0
        ):
            raise ValueError("Location coordinates are invalid")
        object.__setattr__(self, "latitude", latitude)
        object.__setattr__(self, "longitude", longitude)
        normalized_name = " ".join(str(self.name or "").split())[:240]
        object.__setattr__(self, "name", normalized_name or "Unknown location")
        object.__setattr__(self, "country_code", str(self.country_code).upper()[:8])
        object.__setattr__(self, "country", str(self.country)[:120])
        object.__setattr__(self, "admin1", str(self.admin1)[:120])
        object.__setattr__(self, "timezone", str(self.timezone)[:120])

    @property
    def key(self) -> str:
        return f"{self.latitude:.4f},{self.longitude:.4f}"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: Dict[str, Any]) -> "Location":
        return cls(
            name=value.get("name", "Unknown location"),
            latitude=value["latitude"],
            longitude=value["longitude"],
            country_code=value.get("country_code", ""),
            country=value.get("country", ""),
            admin1=value.get("admin1", ""),
            timezone=value.get("timezone", "auto"),
        )


@dataclass
class CurrentConditions:
    observed_at: str
    temperature_c: float
    apparent_temperature_c: Optional[float]
    condition_code: str
    humidity_percent: Optional[float] = None
    pressure_hpa: Optional[float] = None
    wind_speed_kmh: Optional[float] = None
    wind_gust_kmh: Optional[float] = None
    wind_direction_deg: Optional[float] = None
    precipitation_mm: Optional[float] = None
    visibility_km: Optional[float] = None
    is_forecast: bool = False


@dataclass
class HourlyForecast:
    time: str
    temperature_c: float
    condition_code: str
    precipitation_probability: Optional[float] = None
    precipitation_mm: Optional[float] = None
    wind_speed_kmh: Optional[float] = None
    wind_gust_kmh: Optional[float] = None


@dataclass
class DailyForecast:
    date: str
    temperature_max_c: Optional[float]
    temperature_min_c: Optional[float]
    condition_code: str
    precipitation_probability: Optional[float] = None
    precipitation_sum_mm: Optional[float] = None
    wind_speed_max_kmh: Optional[float] = None
    wind_gust_max_kmh: Optional[float] = None
    uv_index_max: Optional[float] = None
    sunrise: Optional[str] = None
    sunset: Optional[str] = None
    source_count: int = 1
    confidence_percent: Optional[int] = None


@dataclass
class AirQuality:
    observed_at: str
    us_aqi: Optional[float] = None
    european_aqi: Optional[float] = None
    pm2_5: Optional[float] = None
    pm10: Optional[float] = None
    ozone: Optional[float] = None
    nitrogen_dioxide: Optional[float] = None
    provider_name: str = ""
    attribution_url: str = ""


@dataclass
class WeatherAlert:
    alert_id: str
    title: str
    description: str
    severity: str
    urgency: str = "unknown"
    onset: Optional[str] = None
    expires: Optional[str] = None
    instruction: Optional[str] = None
    source_name: str = ""
    source_url: str = ""
    official: bool = False
    kind: str = "official"


@dataclass(frozen=True)
class ProviderMetadata:
    provider_id: str
    name: str
    attribution: str
    attribution_url: str
    license_name: str
    coverage: str
    forecast_days: int
    base_weight: float = 1.0
    official_country_codes: tuple[str, ...] = ()
    experimental: bool = False


@dataclass
class WeatherBundle:
    provider_id: str
    provider_name: str
    location: Location
    retrieved_at: str
    timezone: str
    current: CurrentConditions
    hourly: List[HourlyForecast] = field(default_factory=list)
    daily: List[DailyForecast] = field(default_factory=list)
    air_quality: Optional[AirQuality] = None
    alerts: List[WeatherAlert] = field(default_factory=list)
    attribution: str = ""
    attribution_url: str = ""
    source_ids: List[str] = field(default_factory=list)
    is_consensus: bool = False
    confidence_percent: Optional[int] = None
    stale: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: Dict[str, Any]) -> "WeatherBundle":
        return cls(
            provider_id=str(value["provider_id"]),
            provider_name=str(value["provider_name"]),
            location=Location.from_dict(value["location"]),
            retrieved_at=str(value["retrieved_at"]),
            timezone=str(value.get("timezone", "auto")),
            current=CurrentConditions(**value["current"]),
            hourly=[HourlyForecast(**item) for item in value.get("hourly", [])],
            daily=[DailyForecast(**item) for item in value.get("daily", [])],
            air_quality=AirQuality(**value["air_quality"]) if value.get("air_quality") else None,
            alerts=[WeatherAlert(**item) for item in value.get("alerts", [])],
            attribution=str(value.get("attribution", "")),
            attribution_url=str(value.get("attribution_url", "")),
            source_ids=list(value.get("source_ids", [])),
            is_consensus=bool(value.get("is_consensus", False)),
            confidence_percent=value.get("confidence_percent"),
            stale=bool(value.get("stale", False)),
        )


@dataclass
class WeatherReport:
    display: WeatherBundle
    sources: List[WeatherBundle]
    errors: Dict[str, str] = field(default_factory=dict)
    mode: str = "consensus"
    from_cache: bool = False
