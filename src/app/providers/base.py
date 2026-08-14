# Copyright (C) 2026 Vicente José Leiva Escárate
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from abc import ABC, abstractmethod

from app.models import Location, ProviderMetadata, WeatherBundle


class ProviderError(RuntimeError):
    pass


class CoverageError(ProviderError):
    pass


class WeatherProvider(ABC):
    metadata: ProviderMetadata

    def supports(self, location: Location) -> bool:
        return True

    def weight_for(self, location: Location) -> float:
        weight = self.metadata.base_weight
        if location.country_code.upper() in self.metadata.official_country_codes:
            weight *= 2.0
        return weight

    @abstractmethod
    def fetch(self, location: Location) -> WeatherBundle:
        raise NotImplementedError
