# Copyright (C) 2026 Vicente José Leiva Escárate
# SPDX-License-Identifier: GPL-3.0-or-later

import json
import stat
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from app.models import (
    CurrentConditions,
    DailyForecast,
    HourlyForecast,
    Location,
    ProviderMetadata,
    WeatherBundle,
    WeatherReport,
)
from app.providers.base import ProviderError
from app.services.cache import WeatherCache
from app.services.diagnostics import build_issue_body, collect_diagnostics
from app.services.weather import RequestCancelled, WeatherService
from app.settings import SettingsManager


def report(location):
    bundle = WeatherBundle(
        provider_id="open-meteo",
        provider_name="Open-Meteo",
        location=location,
        retrieved_at="2026-08-11T12:00:00+00:00",
        timezone="America/Santiago",
        current=CurrentConditions(
            observed_at="2026-08-11T08:00",
            temperature_c=10,
            apparent_temperature_c=9,
            condition_code="clear",
        ),
    )
    return WeatherReport(display=bundle, sources=[bundle])


class PersistenceAndDiagnosticsTestCase(unittest.TestCase):
    def test_location_model_rejects_nonfinite_or_out_of_range_coordinates(self):
        for latitude, longitude in ((float("nan"), 0), (91, 0), (0, 181)):
            with self.assertRaises(ValueError):
                Location("Invalid", latitude, longitude)

    @patch("app.settings.Gio")
    def test_settings_use_json_fallback_when_schema_is_unavailable(self, gio):
        gio.SettingsSchemaSource.get_default.return_value.lookup.return_value = None
        with tempfile.TemporaryDirectory() as directory:
            settings = SettingsManager(Path(directory) / "settings.json")
            settings.language = "fr"
            self.assertIsNone(settings._settings)
            self.assertEqual(settings.language, "fr")

    def test_malformed_fallback_preferences_return_safe_defaults(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            path.write_text(
                json.dumps(
                    {
                        "enabled-providers": "open-meteo",
                        "unit-system": "invalid",
                        "color-scheme": "invalid",
                        "update-interval": "not-a-number",
                        "show-forecast-signals": "false",
                        "seen-alert-ids": "not-a-list",
                    }
                ),
                encoding="utf-8",
            )
            settings = SettingsManager(path)
            settings._settings = None
            self.assertEqual(settings.enabled_providers(), ["open-meteo"])
            self.assertEqual(settings.unit_system, "auto")
            self.assertEqual(settings.color_scheme, "system")
            self.assertEqual(settings.update_interval_minutes, 30)
            self.assertTrue(settings.show_forecast_signals)
            self.assertEqual(settings.seen_alert_ids(), [])

    def test_persistent_cache_roundtrip(self):
        with tempfile.TemporaryDirectory() as directory:
            location = Location("Villarrica", -39.28, -72.23, "CL")
            cache = WeatherCache(Path(directory), fresh_seconds=600)
            cache.store(location, "consensus", ["open-meteo"], report(location))
            loaded, stale = cache.load(location, "consensus", ["open-meteo"])
            self.assertFalse(stale)
            self.assertTrue(loaded.from_cache)
            self.assertEqual(loaded.display.location.name, "Villarrica")
            cache.clear_location(location)
            self.assertIsNone(
                cache.load(location, "consensus", ["open-meteo"])
            )

    def test_failed_refresh_marks_even_a_young_cache_offline(self):
        class FailingProvider:
            metadata = ProviderMetadata(
                provider_id="open-meteo",
                name="Failing provider",
                attribution="",
                attribution_url="",
                license_name="test",
                coverage="test",
                forecast_days=1,
            )

            def supports(self, _location):
                return True

            def fetch(self, _location):
                raise ProviderError("simulated network failure")

            def weight_for(self, _location):
                return 1.0

        class Registry:
            provider = FailingProvider()

            def select(self, provider_ids):
                return [self.provider] if "open-meteo" in provider_ids else []

        with tempfile.TemporaryDirectory() as directory:
            location = Location("Villarrica", -39.28, -72.23, "CL")
            cache = WeatherCache(Path(directory), fresh_seconds=600)
            cache.store(location, "consensus", ["open-meteo"], report(location))
            service = WeatherService(Registry(), cache)

            loaded = service.load(
                location,
                ["open-meteo"],
                mode="consensus",
                force_refresh=True,
            )

            self.assertTrue(loaded.from_cache)
            self.assertTrue(loaded.display.stale)
            self.assertTrue(all(source.stale for source in loaded.sources))
            self.assertIn("open-meteo", loaded.errors)

    def test_settings_keep_only_five_locations(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = SettingsManager(Path(directory) / "settings.json")
            # Force fallback even on systems where a schema happens to exist.
            settings._settings = None
            results = [
                settings.save_location(Location(f"Place {index}", index, index))
                for index in range(7)
            ]
            self.assertEqual(len(settings.locations()), 5)
            self.assertEqual(results, [True, True, True, True, True, False, False])
            self.assertEqual(settings.active_location().name, "Place 4")
            settings.clear_locations()
            self.assertEqual(settings.locations(), [])

    def test_cache_files_are_private_and_atomic(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "weather"
            location = Location("Villarrica", -39.28, -72.23, "CL")
            cache = WeatherCache(root)
            cache.store(location, "open-meteo", ["open-meteo"], report(location))
            path = next(root.glob("*.json"))
            self.assertEqual(stat.S_IMODE(root.stat().st_mode), 0o700)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            self.assertEqual(list(root.glob("*.tmp")), [])

    def test_cache_older_than_offline_limit_is_deleted(self):
        with tempfile.TemporaryDirectory() as directory:
            location = Location("Villarrica", -39.28, -72.23, "CL")
            cache = WeatherCache(Path(directory), max_offline_seconds=60)
            cache.store(location, "open-meteo", ["open-meteo"], report(location))
            path = next(Path(directory).glob("*.json"))
            payload = json.loads(path.read_text(encoding="utf-8"))
            with patch("app.services.cache.time.time", return_value=payload["stored_at"] + 61):
                self.assertIsNone(cache.load(location, "open-meteo", ["open-meteo"]))
            self.assertFalse(path.exists())

    def test_stale_cache_removes_expired_forecast_entries(self):
        with tempfile.TemporaryDirectory() as directory:
            now = datetime.now(timezone.utc)
            location = Location("UTC test", 0, 0, timezone="UTC")
            value = report(location)
            value.display.hourly = [
                HourlyForecast(
                    time=(now - timedelta(hours=4)).isoformat(),
                    temperature_c=10,
                    condition_code="clear",
                ),
                HourlyForecast(
                    time=(now + timedelta(hours=4)).isoformat(),
                    temperature_c=12,
                    condition_code="clear",
                ),
            ]
            value.display.daily = [
                DailyForecast(
                    date=(now.date() - timedelta(days=3)).isoformat(),
                    temperature_max_c=12,
                    temperature_min_c=5,
                    condition_code="clear",
                ),
                DailyForecast(
                    date=(now.date() + timedelta(days=1)).isoformat(),
                    temperature_max_c=13,
                    temperature_min_c=6,
                    condition_code="clear",
                ),
            ]
            value.sources = [value.display]
            cache = WeatherCache(Path(directory), fresh_seconds=0)
            cache.store(location, "open-meteo", ["open-meteo"], value)
            loaded, stale = cache.load(location, "open-meteo", ["open-meteo"])
            self.assertTrue(stale)
            self.assertEqual(len(loaded.display.hourly), 1)
            self.assertEqual(len(loaded.display.daily), 1)

    def test_latest_cache_survives_provider_preference_change(self):
        with tempfile.TemporaryDirectory() as directory:
            location = Location("Villarrica", -39.28, -72.23, "CL")
            cache = WeatherCache(Path(directory))
            cache.store(location, "open-meteo", ["open-meteo"], report(location))
            loaded, _stale = cache.load_latest(location)
            self.assertEqual(loaded.display.provider_id, "open-meteo")

    def test_cancelled_request_never_recreates_cache(self):
        class Provider:
            metadata = ProviderMetadata(
                provider_id="open-meteo",
                name="Provider",
                attribution="",
                attribution_url="",
                license_name="test",
                coverage="test",
                forecast_days=1,
            )

            def supports(self, _location):
                return True

            def fetch(self, location):
                return report(location).display

            def weight_for(self, _location):
                return 1.0

        class Registry:
            provider = Provider()

            def select(self, provider_ids):
                return [self.provider] if "open-meteo" in provider_ids else []

        with tempfile.TemporaryDirectory() as directory:
            location = Location("Villarrica", -39.28, -72.23, "CL")
            cache = WeatherCache(Path(directory))
            service = WeatherService(Registry(), cache)
            checks = iter((False, False, True))
            with self.assertRaises(RequestCancelled):
                service.load(
                    location,
                    ["open-meteo"],
                    mode="open-meteo",
                    force_refresh=True,
                    is_cancelled=lambda: next(checks, True),
                )
            self.assertEqual(list(Path(directory).glob("*.json")), [])

    def test_cache_generation_blocks_store_after_clear(self):
        with tempfile.TemporaryDirectory() as directory:
            location = Location("Villarrica", -39.28, -72.23, "CL")
            cache = WeatherCache(Path(directory))
            generation = cache.write_generation()
            cache.clear()
            stored = cache.store(
                location,
                "open-meteo",
                ["open-meteo"],
                report(location),
                expected_generation=generation,
            )
            self.assertFalse(stored)
            self.assertEqual(list(Path(directory).glob("*.json")), [])

    def test_reset_preferences_keeps_locations(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = SettingsManager(Path(directory) / "settings.json")
            settings._settings = None
            settings.save_location(Location("Place", 1, 2))
            settings.unit_system = "imperial"
            settings.language = "fr"

            settings.reset_preferences()

            self.assertEqual(settings.unit_system, "auto")
            self.assertEqual(settings.language, "system")
            self.assertEqual(settings.active_location().name, "Place")

    @patch("app.settings.locale.getlocale", return_value=("es_CL", "UTF-8"))
    def test_system_language_is_used_for_location_search(self, _getlocale):
        with tempfile.TemporaryDirectory() as directory:
            settings = SettingsManager(Path(directory) / "settings.json")
            settings._settings = None
            self.assertEqual(settings.resolved_language(), "es")

    def test_diagnostics_exclude_identifiers_and_location(self):
        diagnostics = collect_diagnostics("0.1.0-alpha")
        body = build_issue_body("It failed", diagnostics).lower()
        self.assertNotIn("**hostname:**", body)
        self.assertNotIn("mac address:", body)
        self.assertNotIn("latitude", body)
        self.assertIn("did not automatically collect an ip address", body)


if __name__ == "__main__":
    unittest.main()
