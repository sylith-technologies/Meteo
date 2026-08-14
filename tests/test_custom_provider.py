# Copyright (C) 2026 Vicente José Leiva Escárate
# SPDX-License-Identifier: GPL-3.0-or-later

import unittest
from unittest.mock import patch

from app.models import Location
from app.providers.base import ProviderError
from app.providers.custom import (
    CustomProvider,
    CustomProviderConfig,
    extract_path,
    validate_resolved_custom_host,
    validate_custom_url,
    validate_optional_https_url,
)
from app.providers.registry import ProviderRegistry


class CustomProviderTestCase(unittest.TestCase):
    def test_rejects_insecure_and_private_endpoints(self):
        with self.assertRaises(ValueError):
            validate_custom_url("http://example.org/weather")
        with self.assertRaises(ValueError):
            validate_custom_url("https://127.0.0.1/weather")
        with self.assertRaises(ValueError):
            validate_custom_url("https://localhost/weather")
        with self.assertRaises(ValueError):
            validate_custom_url("https://example.org/{token}")
        with self.assertRaises(ValueError):
            validate_optional_https_url("file:///etc/passwd")

    @patch("app.providers.custom.socket.getaddrinfo")
    def test_rejects_hostname_resolving_to_private_address(self, getaddrinfo):
        getaddrinfo.return_value = [
            (2, 1, 6, "", ("192.168.1.20", 443)),
        ]
        with self.assertRaises(ProviderError):
            validate_resolved_custom_host("https://weather.example/data")

    def test_rejects_executable_or_invalid_mapping_syntax(self):
        with self.assertRaises(ValueError):
            CustomProviderConfig.from_dict(
                {
                    "id": "custom-invalid",
                    "name": "Invalid",
                    "url": "https://example.org/weather",
                    "mapping": {"temperature": "data.values[*].temperature"},
                }
            )

    def test_restricted_dotted_path_supports_array_index(self):
        payload = {"data": {"values": [{"temperature": 12.5}]}}
        self.assertEqual(extract_path(payload, "data.values[0].temperature"), 12.5)
        self.assertIsNone(extract_path(payload, "data.values[*].temperature"))

    def test_normalizes_fahrenheit_and_mph(self):
        config = CustomProviderConfig.from_dict(
            {
                "id": "custom-example",
                "name": "Example",
                "url": "https://example.org/weather?lat={lat}&lon={lon}",
                "mapping": {
                    "temperature": "current.temp",
                    "wind_speed": "current.wind",
                    "wind_gust": "current.gust",
                    "condition": "current.condition",
                },
                "condition_map": {"sunny": "clear"},
                "temperature_unit": "fahrenheit",
                "wind_unit": "mph",
            }
        )
        provider = CustomProvider(config)
        location = Location("Test", 0, 0)
        result = provider.parse(
            location,
            {"current": {"temp": 68, "wind": 10, "gust": 20, "condition": "Sunny"}},
        )
        self.assertAlmostEqual(result.current.temperature_c, 20)
        self.assertAlmostEqual(result.current.wind_speed_kmh, 16.09344)
        self.assertAlmostEqual(result.current.wind_gust_kmh, 32.18688)
        self.assertEqual(result.current.condition_code, "clear")

    def test_missing_apparent_temperature_remains_missing(self):
        provider = CustomProvider(
            CustomProviderConfig.from_dict(
                {
                    "id": "custom-example",
                    "name": "Example",
                    "url": "https://example.org/weather?lat={lat}&lon={lon}",
                    "mapping": {"temperature": "current.temperature"},
                    "attribution": "Example data",
                }
            )
        )
        bundle = provider.parse(
            Location("Test", -33.45, -70.66, "CL"),
            {"current": {"temperature": 18}},
        )
        self.assertIsNone(bundle.current.apparent_temperature_c)

    def test_rejects_nonfinite_weight_and_implausible_temperature(self):
        base = {
            "id": "custom-example",
            "name": "Example",
            "url": "https://example.org/weather",
            "mapping": {"temperature": "current.temp"},
        }
        with self.assertRaises(ValueError):
            CustomProviderConfig.from_dict({**base, "weight": float("nan")})
        provider = CustomProvider(CustomProviderConfig.from_dict(base))
        with self.assertRaises(ProviderError):
            provider.parse(Location("Test", 0, 0), {"current": {"temp": 200}})

    def test_custom_networking_is_disabled_by_default(self):
        registry = ProviderRegistry()
        self.assertTrue(all(not item.metadata.experimental for item in registry.all()))


if __name__ == "__main__":
    unittest.main()
