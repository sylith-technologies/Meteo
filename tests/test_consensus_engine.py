# Copyright (C) 2026 Vicente José Leiva Escárate
# SPDX-License-Identifier: GPL-3.0-or-later

import unittest

from app.domain.consensus import ConsensusEngine
from app.models import (
    CurrentConditions,
    DailyForecast,
    Location,
    WeatherAlert,
    WeatherBundle,
)


LOCATION = Location("Villarrica, Araucanía, Chile", -39.28, -72.23, "CL", "Chile")


def bundle(provider_id, temperature, condition="clear", alert=None):
    return WeatherBundle(
        provider_id=provider_id,
        provider_name=provider_id,
        location=LOCATION,
        retrieved_at="2026-08-11T12:00:00+00:00",
        timezone="America/Santiago",
        current=CurrentConditions(
            observed_at="2026-08-11T08:00",
            temperature_c=temperature,
            apparent_temperature_c=temperature - 1,
            condition_code=condition,
            humidity_percent=60,
            wind_speed_kmh=10,
            wind_direction_deg=350 if provider_id == "a" else 10,
        ),
        daily=[
            DailyForecast(
                date="2026-08-11",
                temperature_max_c=temperature + 4,
                temperature_min_c=temperature - 4,
                condition_code=condition,
                precipitation_probability=20,
            )
        ],
        alerts=[alert] if alert else [],
        source_ids=[provider_id],
    )


class ConsensusEngineTestCase(unittest.TestCase):
    def test_weighted_consensus_uses_normalized_values(self):
        result = ConsensusEngine.calculate([(bundle("a", 10), 1.0), (bundle("b", 14), 3.0)])
        self.assertTrue(result.is_consensus)
        self.assertEqual(result.source_ids, ["a", "b"])
        self.assertEqual(result.current.temperature_c, 13.0)
        self.assertAlmostEqual(result.current.wind_direction_deg, 5.0, places=0)
        self.assertEqual(result.daily[0].source_count, 2)
        self.assertGreaterEqual(result.confidence_percent, 0)
        self.assertLessEqual(result.confidence_percent, 100)

    def test_single_provider_is_not_mislabelled_as_consensus(self):
        result = ConsensusEngine.calculate([(bundle("a", 12), 1.0)])
        self.assertFalse(result.is_consensus)
        self.assertEqual(result.provider_id, "a")
        self.assertEqual(result.confidence_percent, 40)

    def test_official_alert_is_preserved_not_voted(self):
        alert = WeatherAlert(
            alert_id="official-1",
            title="Severe thunderstorm warning",
            description="Official text",
            severity="severe",
            source_name="Authority",
            official=True,
        )
        result = ConsensusEngine.calculate(
            [(bundle("a", 10, alert=alert), 1.0), (bundle("b", 11), 1.0)]
        )
        self.assertEqual(len(result.alerts), 1)
        self.assertTrue(result.alerts[0].official)
        self.assertEqual(result.alerts[0].description, "Official text")

    def test_extreme_outlier_is_filtered_with_three_sources(self):
        result = ConsensusEngine.calculate(
            [(bundle("a", 10), 1.0), (bundle("b", 11), 1.0), (bundle("c", 60), 1.0)]
        )
        self.assertLess(result.current.temperature_c, 20)

    def test_zero_mad_does_not_discard_a_reasonable_third_forecast(self):
        result = ConsensusEngine.calculate(
            [(bundle("a", 10), 1.0), (bundle("b", 10), 1.0), (bundle("c", 13), 1.0)]
        )
        self.assertEqual(result.current.temperature_c, 11.0)

    def test_missing_optional_values_remain_missing(self):
        first = bundle("a", 10)
        second = bundle("b", 12)
        first.current.apparent_temperature_c = None
        second.current.apparent_temperature_c = None
        first.daily[0].precipitation_sum_mm = None
        second.daily[0].precipitation_sum_mm = None
        result = ConsensusEngine.calculate([(first, 1.0), (second, 1.0)])
        self.assertIsNone(result.current.apparent_temperature_c)
        self.assertIsNone(result.daily[0].precipitation_sum_mm)


if __name__ == "__main__":
    unittest.main()
