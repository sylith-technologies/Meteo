# Copyright (C) 2026 Vicente José Leiva Escárate
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from app.models import Location
from app.providers.base import WeatherProvider
from app.providers.custom import CustomProvider, CustomProviderConfig
from app.providers.met_norway import MetNorwayProvider
from app.providers.nws import NwsProvider
from app.providers.open_meteo import OpenMeteoProvider


class ProviderRegistry:
    def __init__(
        self,
        custom_config_path: Optional[Path] = None,
        allow_custom: bool = False,
    ):
        providers: List[WeatherProvider] = [
            OpenMeteoProvider(),
            MetNorwayProvider(),
            NwsProvider(),
        ]
        # Custom networking remains disabled in the public alpha until DNS
        # pinning can eliminate the validation/connection rebinding window.
        if allow_custom and custom_config_path:
            providers.extend(self._load_custom(custom_config_path))
        self._providers: Dict[str, WeatherProvider] = {
            provider.metadata.provider_id: provider for provider in providers
        }

    @staticmethod
    def _load_custom(path: Path) -> List[WeatherProvider]:
        if not path.is_file():
            return []
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            entries = payload.get("providers", []) if isinstance(payload, dict) else []
            return [CustomProvider(CustomProviderConfig.from_dict(entry)) for entry in entries]
        except (OSError, ValueError, TypeError, AttributeError, json.JSONDecodeError):
            return []

    def all(self) -> List[WeatherProvider]:
        return list(self._providers.values())

    def get(self, provider_id: str) -> Optional[WeatherProvider]:
        return self._providers.get(provider_id)

    def select(self, provider_ids: Iterable[str]) -> List[WeatherProvider]:
        return [self._providers[item] for item in provider_ids if item in self._providers]

    def clear_persistent_cache(self, location: Optional[Location] = None) -> None:
        for provider in self._providers.values():
            clear_cache = getattr(provider, "clear_cache", None)
            if callable(clear_cache):
                clear_cache(location)
