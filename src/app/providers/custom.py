# Copyright (C) 2026 Vicente José Leiva Escárate
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import ipaddress
import math
import re
import socket
import urllib.parse
from dataclasses import dataclass
from datetime import datetime, timezone
from string import Formatter
from typing import Any, Dict, Optional

from app.models import CurrentConditions, Location, ProviderMetadata, WeatherBundle
from app.providers.base import ProviderError, WeatherProvider
from app.providers.http import JsonHttpClient, http_client


_PATH_PART = re.compile(r"^(?P<name>[A-Za-z_][A-Za-z0-9_-]*)(?:\[(?P<index>\d+)\])?$")
_CANONICAL_CONDITIONS = {
    "clear", "mostly-clear", "partly-cloudy", "cloudy", "fog", "drizzle",
    "rain", "heavy-rain", "snow", "heavy-snow", "showers", "snow-showers",
    "thunderstorm", "unknown",
}
_URL_FIELDS = {"lat", "lon", "latitude", "longitude"}
_MAPPING_FIELDS = {
    "temperature",
    "apparent_temperature",
    "condition",
    "humidity",
    "pressure",
    "wind_speed",
    "wind_gust",
    "wind_direction",
    "precipitation",
    "visibility",
    "observed_at",
}


def _validate_mapping_path(path: str) -> None:
    if not path or any(not _PATH_PART.fullmatch(part) for part in path.split(".")):
        raise ValueError(f"Invalid custom provider field path: {path!r}")


@dataclass(frozen=True)
class CustomProviderConfig:
    provider_id: str
    name: str
    url: str
    mapping: Dict[str, str]
    condition_map: Dict[str, str]
    attribution: str
    attribution_url: str
    weight: float = 0.5
    temperature_unit: str = "celsius"
    wind_unit: str = "kmh"
    country_codes: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, value: Dict[str, Any]) -> "CustomProviderConfig":
        provider_id = str(value.get("id", "custom")).strip().lower()
        if not re.fullmatch(r"custom-[a-z0-9-]{1,48}", provider_id):
            raise ValueError("Custom provider id must start with 'custom-'")
        name = str(value.get("name", "")).strip()
        if not name or len(name) > 80:
            raise ValueError("Custom provider name is required")
        url = str(value.get("url", "")).strip()
        if len(url) > 2_048:
            raise ValueError("Custom provider URL is too long")
        validate_custom_url(url)
        mapping = value.get("mapping")
        if not isinstance(mapping, dict) or "temperature" not in mapping:
            raise ValueError("Custom provider mapping requires a temperature path")
        normalized_mapping = {
            str(key): str(path)
            for key, path in mapping.items()
            if str(key) in _MAPPING_FIELDS
        }
        for path in normalized_mapping.values():
            _validate_mapping_path(path)
        weight = float(value.get("weight", 0.5))
        if not math.isfinite(weight):
            raise ValueError("Custom provider weight must be finite")
        weight = min(2.0, max(0.1, weight))
        temperature_unit = str(value.get("temperature_unit", "celsius")).lower()
        wind_unit = str(value.get("wind_unit", "kmh")).lower()
        if temperature_unit not in {"celsius", "fahrenheit"}:
            raise ValueError("Temperature unit must be 'celsius' or 'fahrenheit'")
        if wind_unit not in {"kmh", "mph", "ms"}:
            raise ValueError("Wind unit must be 'kmh', 'mph' or 'ms'")
        attribution_url = str(value.get("attribution_url", "")).strip()
        validate_optional_https_url(attribution_url)
        country_codes_value = value.get("country_codes", [])
        if not isinstance(country_codes_value, list):
            raise ValueError("Custom provider country_codes must be a list")
        country_codes = tuple(str(code).upper() for code in country_codes_value)
        if any(not re.fullmatch(r"[A-Z]{2}", code) for code in country_codes):
            raise ValueError("Custom provider country codes must use ISO alpha-2 form")
        condition_map = value.get("condition_map") or {}
        if not isinstance(condition_map, dict):
            raise ValueError("Custom provider condition_map must be an object")
        return cls(
            provider_id=provider_id,
            name=name,
            url=url,
            mapping=normalized_mapping,
            condition_map={
                str(key).lower(): str(condition)
                for key, condition in condition_map.items()
                if str(condition) in _CANONICAL_CONDITIONS
            },
            attribution=str(
                value.get("attribution", "User-configured provider")
            )[:240],
            attribution_url=attribution_url,
            weight=weight,
            temperature_unit=temperature_unit,
            wind_unit=wind_unit,
            country_codes=country_codes,
        )


def validate_optional_https_url(url: str) -> None:
    if not url:
        return
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Attribution URL must be an ordinary HTTPS URL")


def validate_custom_url(url: str) -> None:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError("Custom provider URL must use HTTPS")
    if parsed.username or parsed.password:
        raise ValueError("Credentials must not be embedded in a provider URL")
    hostname = parsed.hostname.rstrip(".").lower()
    if (
        hostname == "localhost"
        or hostname.endswith(".localhost")
        or hostname.endswith(".local")
    ):
        raise ValueError("Local network hostnames are not allowed")
    try:
        fields = [
            field_name
            for _literal, field_name, _format_spec, _conversion in Formatter().parse(url)
            if field_name
        ]
    except ValueError as error:
        raise ValueError("Custom provider URL contains invalid placeholders") from error
    if any(field not in _URL_FIELDS for field in fields):
        raise ValueError("URL placeholders are limited to lat, lon, latitude and longitude")
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        address = None
    if address and not address.is_global:
        raise ValueError("Non-public network addresses are not allowed")


def validate_resolved_custom_host(url: str) -> None:
    parsed = urllib.parse.urlparse(url)
    hostname = parsed.hostname
    if not hostname:
        raise ProviderError("Custom provider URL has no hostname")
    try:
        addresses = {
            info[4][0]
            for info in socket.getaddrinfo(
                hostname,
                parsed.port or 443,
                type=socket.SOCK_STREAM,
            )
        }
    except OSError as error:
        raise ProviderError("Custom provider hostname could not be resolved") from error
    if not addresses:
        raise ProviderError("Custom provider hostname returned no addresses")
    for value in addresses:
        try:
            address = ipaddress.ip_address(value)
        except ValueError as error:
            raise ProviderError("Custom provider resolved to an invalid address") from error
        if not address.is_global:
            raise ProviderError("Custom provider resolved to a non-public address")


def extract_path(payload: Dict[str, Any], path: str, default: Any = None) -> Any:
    current: Any = payload
    for raw_part in path.split("."):
        match = _PATH_PART.fullmatch(raw_part)
        if not match or not isinstance(current, dict):
            return default
        current = current.get(match.group("name"), default)
        index_text = match.group("index")
        if index_text is not None:
            if not isinstance(current, list) or int(index_text) >= len(current):
                return default
            current = current[int(index_text)]
        if current is default:
            return default
    return current


class CustomProvider(WeatherProvider):
    def __init__(self, config: CustomProviderConfig, client: JsonHttpClient = http_client):
        self.config = config
        self.client = client
        self.metadata = ProviderMetadata(
            provider_id=config.provider_id,
            name=config.name,
            attribution=config.attribution,
            attribution_url=config.attribution_url,
            license_name="Defined by the user",
            coverage="user-defined",
            forecast_days=0,
            base_weight=config.weight,
            official_country_codes=(),
            experimental=True,
        )

    def supports(self, location: Location) -> bool:
        return not self.config.country_codes or location.country_code in self.config.country_codes

    def fetch(self, location: Location) -> WeatherBundle:
        url = self.config.url.format(
            latitude=f"{location.latitude:.6f}",
            longitude=f"{location.longitude:.6f}",
            lat=f"{location.latitude:.6f}",
            lon=f"{location.longitude:.6f}",
        )
        validate_custom_url(url)
        validate_resolved_custom_host(url)
        payload = self.client.get_json(url)
        return self.parse(location, payload)

    def _number(self, payload: Dict[str, Any], key: str) -> Optional[float]:
        path = self.config.mapping.get(key)
        if not path:
            return None
        value = extract_path(payload, path)
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        if not math.isfinite(number):
            return None
        bounds = {
            "temperature": (-200.0, 200.0),
            "apparent_temperature": (-250.0, 250.0),
            "humidity": (0.0, 100.0),
            "pressure": (800.0, 1100.0),
            "wind_speed": (0.0, 500.0),
            "wind_gust": (0.0, 500.0),
            "wind_direction": (0.0, 360.0),
            "precipitation": (0.0, 1000.0),
            "visibility": (0.0, 1000.0),
        }
        minimum, maximum = bounds.get(key, (-1e9, 1e9))
        return number if minimum <= number <= maximum else None

    def parse(self, location: Location, payload: Dict[str, Any]) -> WeatherBundle:
        temperature = self._number(payload, "temperature")
        if temperature is None:
            raise ProviderError("Custom provider did not return a numeric temperature")
        apparent = self._number(payload, "apparent_temperature")
        wind = self._number(payload, "wind_speed")
        wind_gust = self._number(payload, "wind_gust")
        if self.config.temperature_unit == "fahrenheit":
            temperature = (temperature - 32.0) * 5.0 / 9.0
            apparent = ((apparent - 32.0) * 5.0 / 9.0) if apparent is not None else None
        if not -100.0 <= temperature <= 70.0:
            raise ProviderError("Custom provider temperature is outside supported limits")
        if apparent is not None and not -120.0 <= apparent <= 80.0:
            apparent = None
        if wind is not None:
            if self.config.wind_unit == "mph":
                wind *= 1.609344
            elif self.config.wind_unit == "ms":
                wind *= 3.6
        if wind_gust is not None:
            if self.config.wind_unit == "mph":
                wind_gust *= 1.609344
            elif self.config.wind_unit == "ms":
                wind_gust *= 3.6

        raw_condition = extract_path(payload, self.config.mapping.get("condition", ""), "unknown")
        raw_condition_text = str(raw_condition).strip().lower()
        condition = self.config.condition_map.get(raw_condition_text, raw_condition_text)
        if condition not in _CANONICAL_CONDITIONS:
            condition = "unknown"

        current = CurrentConditions(
            observed_at=str(
                extract_path(payload, self.config.mapping.get("observed_at", ""), "")
                or datetime.now(timezone.utc).isoformat()
            ),
            temperature_c=temperature,
            apparent_temperature_c=apparent,
            condition_code=condition,
            humidity_percent=self._number(payload, "humidity"),
            pressure_hpa=self._number(payload, "pressure"),
            wind_speed_kmh=wind,
            wind_gust_kmh=wind_gust,
            wind_direction_deg=self._number(payload, "wind_direction"),
            precipitation_mm=self._number(payload, "precipitation"),
            visibility_km=self._number(payload, "visibility"),
        )
        return WeatherBundle(
            provider_id=self.metadata.provider_id,
            provider_name=self.metadata.name,
            location=location,
            retrieved_at=datetime.now(timezone.utc).isoformat(),
            timezone=location.timezone,
            current=current,
            attribution=self.metadata.attribution,
            attribution_url=self.metadata.attribution_url,
            source_ids=[self.metadata.provider_id],
        )
