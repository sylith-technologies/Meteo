# Copyright (C) 2026 Vicente José Leiva Escárate
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import replace
from typing import Callable, Dict, Iterable, List, Optional

from app.domain.consensus import ConsensusEngine
from app.models import Location, WeatherBundle, WeatherReport
from app.providers.base import WeatherProvider
from app.providers.registry import ProviderRegistry
from app.services.cache import WeatherCache


class WeatherUnavailable(RuntimeError):
    pass


class RequestCancelled(RuntimeError):
    pass


class WeatherService:
    def __init__(
        self,
        registry: ProviderRegistry,
        cache: Optional[WeatherCache] = None,
    ):
        self.registry = registry
        self.cache = cache or WeatherCache()

    def providers_for(self, location: Location) -> List[WeatherProvider]:
        return [provider for provider in self.registry.all() if provider.supports(location)]

    @staticmethod
    def _offline_report(
        cached: WeatherReport,
        errors: Optional[Dict[str, str]] = None,
    ) -> WeatherReport:
        """Marks a network-fallback report as offline even if the cache is young."""

        cached.display = replace(cached.display, stale=True)
        cached.sources = [replace(source, stale=True) for source in cached.sources]
        cached.errors.update(errors or {})
        cached.from_cache = True
        return cached

    def load(
        self,
        location: Location,
        enabled_provider_ids: Iterable[str],
        mode: str = "consensus",
        force_refresh: bool = False,
        is_cancelled: Optional[Callable[[], bool]] = None,
    ) -> WeatherReport:
        cancelled = is_cancelled or (lambda: False)
        if cancelled():
            raise RequestCancelled("Weather request was cancelled")
        cache_generation = self.cache.write_generation()
        enabled = list(dict.fromkeys(enabled_provider_ids))
        if mode != "consensus":
            enabled = [mode]

        if not force_refresh:
            cached = self.cache.load(location, mode, enabled, allow_stale=False)
            if cached:
                return cached[0]

        providers = [
            provider
            for provider in self.registry.select(enabled)
            if provider.supports(location)
        ]
        if not providers:
            cached = self.cache.load(location, mode, enabled, allow_stale=True)
            if not cached:
                cached = self.cache.load_latest(location)
            if cached:
                return self._offline_report(cached[0])
            raise WeatherUnavailable("No enabled provider covers this location")

        results: List[WeatherBundle] = []
        errors: Dict[str, str] = {}
        with ThreadPoolExecutor(max_workers=min(4, len(providers))) as executor:
            futures = {executor.submit(provider.fetch, location): provider for provider in providers}
            for future in as_completed(futures):
                if cancelled():
                    for pending in futures:
                        pending.cancel()
                    raise RequestCancelled("Weather request was cancelled")
                provider = futures[future]
                try:
                    results.append(future.result())
                except Exception as error:
                    errors[provider.metadata.provider_id] = str(error)[:240]

        if not results:
            cached = self.cache.load(location, mode, enabled, allow_stale=True)
            if not cached:
                cached = self.cache.load_latest(location)
            if cached:
                return self._offline_report(cached[0], errors)
            raise WeatherUnavailable("All weather providers failed")

        if cancelled():
            raise RequestCancelled("Weather request was cancelled")

        order = {provider_id: index for index, provider_id in enumerate(enabled)}
        results.sort(key=lambda bundle: order.get(bundle.provider_id, 999))
        if mode == "consensus":
            provider_by_id = {provider.metadata.provider_id: provider for provider in providers}
            weighted = [
                (bundle, provider_by_id[bundle.provider_id].weight_for(location))
                for bundle in results
            ]
            display = ConsensusEngine.calculate(weighted)
        else:
            display = results[0]

        report = WeatherReport(display=display, sources=results, errors=errors, mode=mode)
        if cancelled():
            raise RequestCancelled("Weather request was cancelled")
        self.cache.store(
            location,
            mode,
            enabled,
            report,
            expected_generation=cache_generation,
        )
        return report
