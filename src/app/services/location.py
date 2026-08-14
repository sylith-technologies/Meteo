# Copyright (C) 2026 Vicente José Leiva Escárate
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import List

from app.core_bridge import native_core
from app.models import Location
from app.providers.http import JsonHttpClient, http_client


class LocationService:
    def __init__(self, client: JsonHttpClient = http_client):
        self.client = client

    def search(self, query: str, language: str = "en") -> List[Location]:
        cleaned = " ".join(query.split())[:120]
        if len(cleaned) < 2:
            return []
        payload = self.client.get_json(
            "https://geocoding-api.open-meteo.com/v1/search",
            {
                "name": cleaned,
                "count": 10,
                "language": language if language in {"en", "es", "pt", "fr"} else "en",
                "format": "json",
            },
        )
        results: List[Location] = []
        seen = set()
        for value in payload.get("results", []):
            if not isinstance(value, dict):
                continue
            try:
                latitude = float(value.get("latitude", 999.0))
                longitude = float(value.get("longitude", 999.0))
            except (TypeError, ValueError):
                continue
            if not native_core.validate_coordinates(latitude, longitude):
                continue
            name_parts = [value.get("name"), value.get("admin1"), value.get("country")]
            display_name = ", ".join(str(item)[:100] for item in name_parts if item)[:240]
            location = Location(
                name=display_name,
                latitude=latitude,
                longitude=longitude,
                country_code=str(value.get("country_code", "")).upper(),
                country=str(value.get("country", "")),
                admin1=str(value.get("admin1", "")),
                timezone=str(value.get("timezone", "auto")),
            )
            if location.key not in seen:
                results.append(location)
                seen.add(location.key)
        return results
