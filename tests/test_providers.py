# Copyright (C) 2026 Vicente José Leiva Escárate
# SPDX-License-Identifier: GPL-3.0-or-later

import unittest

from app.models import Location
from app.providers.base import ProviderError
from app.providers.met_norway import MetNorwayProvider
from app.providers.nws import NwsProvider
from app.providers.open_meteo import OpenMeteoProvider


LOCATION = Location(
    "Villarrica, Araucanía, Chile",
    -39.28,
    -72.23,
    "CL",
    "Chile",
    "Araucanía",
    "America/Santiago",
)


class ProviderParsingTestCase(unittest.TestCase):
    def test_open_meteo_parses_hourly_daily_air_and_signal(self):
        times = [f"2026-08-11T{hour:02d}:00" for hour in range(24)]
        data = {
            "timezone": "America/Santiago",
            "current": {
                "time": times[0],
                "temperature_2m": 10,
                "apparent_temperature": 9,
                "relative_humidity_2m": 80,
                "weather_code": 95,
                "wind_speed_10m": 20,
                "wind_gusts_10m": 75,
                "wind_direction_10m": 180,
                "pressure_msl": 1012,
            },
            "hourly": {
                "time": times,
                "temperature_2m": [10] * 24,
                "weather_code": [95] + [3] * 23,
                "precipitation_probability": [60] * 24,
                "precipitation": [1] * 24,
                "wind_speed_10m": [20] * 24,
                "wind_gusts_10m": [75] * 24,
                "visibility": [10000] * 24,
            },
            "daily": {
                "time": ["2026-08-11", "2026-08-12"],
                "temperature_2m_max": [14, 15],
                "temperature_2m_min": [7, 8],
                "weather_code": [95, 3],
                "precipitation_probability_max": [80, 10],
                "precipitation_sum": [55, 0],
                "wind_speed_10m_max": [30, 20],
                "wind_gusts_10m_max": [75, 35],
                "uv_index_max": [2, 3],
                "sunrise": ["2026-08-11T07:30", "2026-08-12T07:29"],
                "sunset": ["2026-08-11T18:10", "2026-08-12T18:11"],
            },
        }
        air = {
            "current": {
                "time": times[0],
                "us_aqi": 24,
                "european_aqi": 18,
                "pm2_5": 4,
                "pm10": 8,
            }
        }
        result = OpenMeteoProvider.parse(LOCATION, data, air)
        self.assertEqual(result.current.condition_code, "thunderstorm")
        self.assertEqual(len(result.hourly), 24)
        self.assertEqual(len(result.daily), 2)
        self.assertEqual(result.air_quality.us_aqi, 24)
        self.assertGreaterEqual(len(result.alerts), 3)
        self.assertTrue(all(not alert.official for alert in result.alerts))

    def test_open_meteo_keeps_partial_day_and_omits_empty_air_quality(self):
        data = {
            "timezone": "America/Santiago",
            "current": {
                "time": "2026-08-11T12:00",
                "temperature_2m": 12,
                "weather_code": 3,
            },
            "hourly": {"time": [], "temperature_2m": []},
            "daily": {
                "time": ["2026-08-11"],
                "temperature_2m_max": [15],
                "temperature_2m_min": [None],
                "weather_code": [3],
            },
        }
        result = OpenMeteoProvider.parse(
            LOCATION,
            data,
            {"current": {"time": "2026-08-11T12:00", "us_aqi": None}},
        )
        self.assertEqual(len(result.daily), 1)
        self.assertEqual(result.daily[0].temperature_max_c, 15)
        self.assertIsNone(result.daily[0].temperature_min_c)
        self.assertIsNone(result.air_quality)

    def test_met_norway_parses_compact_timeseries(self):
        data = {
            "properties": {
                "timeseries": [
                    {
                        "time": "2026-08-11T12:00:00Z",
                        "data": {
                            "instant": {
                                "details": {
                                    "air_temperature": 11,
                                    "relative_humidity": 70,
                                    "wind_speed": 3,
                                    "wind_from_direction": 200,
                                    "air_pressure_at_sea_level": 1014,
                                }
                            },
                            "next_1_hours": {
                                "summary": {"symbol_code": "partlycloudy_day"},
                                "details": {"precipitation_amount": 0.2},
                            },
                        },
                    },
                    {
                        "time": "2026-08-11T13:00:00Z",
                        "data": {
                            "instant": {"details": {"air_temperature": 13, "wind_speed": 4}},
                            "next_1_hours": {
                                "summary": {"symbol_code": "rain"},
                                "details": {"precipitation_amount": 1.0},
                            },
                        },
                    },
                ]
            }
        }
        result = MetNorwayProvider.parse(LOCATION, data)
        self.assertEqual(result.current.temperature_c, 11)
        self.assertEqual(result.current.condition_code, "partly-cloudy")
        self.assertEqual(len(result.hourly), 2)
        self.assertEqual(len(result.daily), 1)

    def test_met_norway_uses_long_range_periods(self):
        data = {
            "properties": {
                "timeseries": [
                    {
                        "time": "2026-08-15T12:00:00Z",
                        "data": {
                            "instant": {"details": {"air_temperature": 7}},
                            "next_6_hours": {
                                "summary": {"symbol_code": "rain"},
                                "details": {"precipitation_amount": 4.5},
                            },
                        },
                    }
                ]
            }
        }
        result = MetNorwayProvider.parse(LOCATION, data)
        self.assertEqual(result.current.condition_code, "rain")
        self.assertEqual(result.daily[0].precipitation_sum_mm, 4.5)

    def test_met_norway_splits_long_precipitation_at_local_midnight(self):
        location = Location("UTC", 0, 0, timezone="UTC")
        data = {
            "properties": {
                "timeseries": [
                    {
                        "time": "2026-08-11T21:00:00Z",
                        "data": {
                            "instant": {"details": {"air_temperature": 10}},
                            "next_6_hours": {
                                "summary": {"symbol_code": "rain"},
                                "details": {"precipitation_amount": 6},
                            },
                        },
                    },
                    {
                        "time": "2026-08-12T03:00:00Z",
                        "data": {
                            "instant": {"details": {"air_temperature": 9}},
                            "next_6_hours": {
                                "summary": {"symbol_code": "rain"},
                                "details": {"precipitation_amount": 6},
                            },
                        },
                    },
                ]
            }
        }
        result = MetNorwayProvider.parse(location, data)
        self.assertEqual(result.daily[0].precipitation_sum_mm, 3.0)
        self.assertEqual(result.daily[1].precipitation_sum_mm, 9.0)

    def test_nws_preserves_official_alert(self):
        daily = {
            "properties": {
                "periods": [
                    {
                        "startTime": "2026-08-11T06:00:00-04:00",
                        "temperature": 80,
                        "temperatureUnit": "F",
                        "shortForecast": "Sunny",
                        "windSpeed": "5 mph",
                        "probabilityOfPrecipitation": {"value": 10},
                    },
                    {
                        "startTime": "2026-08-11T18:00:00-04:00",
                        "temperature": 60,
                        "temperatureUnit": "F",
                        "shortForecast": "Clear",
                        "windSpeed": "3 mph",
                        "probabilityOfPrecipitation": {"value": 5},
                    },
                ]
            }
        }
        hourly = {"properties": {"periods": daily["properties"]["periods"]}}
        alerts = {
            "features": [
                {
                    "id": "https://api.weather.gov/alerts/1",
                    "properties": {
                        "event": "Tornado Warning",
                        "description": "Official NWS warning",
                        "severity": "Extreme",
                        "senderName": "NWS",
                    },
                }
            ]
        }
        us_location = Location("Miami, Florida, United States", 25.76, -80.19, "US")
        result = NwsProvider.parse(us_location, daily, hourly, alerts)
        self.assertEqual(len(result.alerts), 1)
        self.assertTrue(result.alerts[0].official)
        self.assertEqual(result.alerts[0].title, "Tornado Warning")
        self.assertAlmostEqual(NwsProvider._wind_kmh("5 to 15 mph"), 24.14016)

    def test_nws_does_not_convert_missing_temperature_to_fake_cold(self):
        periods = [
            {
                "startTime": "2026-08-11T06:00:00-04:00",
                "temperature": None,
                "temperatureUnit": "F",
                "shortForecast": "Unknown",
            },
            {
                "startTime": "2026-08-11T07:00:00-04:00",
                "temperature": 68,
                "temperatureUnit": "F",
                "shortForecast": "Sunny",
            },
        ]
        result = NwsProvider.parse(
            Location("Miami", 25.76, -80.19, "US"),
            {"properties": {"periods": periods}},
            {"properties": {"periods": periods}},
        )
        self.assertEqual(len(result.hourly), 1)
        self.assertAlmostEqual(result.current.temperature_c, 20.0)
        self.assertTrue(result.current.is_forecast)

    def test_nws_partial_daily_period_keeps_missing_minimum(self):
        period = {
            "startTime": "2026-08-11T06:00:00-04:00",
            "temperature": 80,
            "temperatureUnit": "F",
            "shortForecast": "Sunny",
            "isDaytime": True,
        }
        result = NwsProvider.parse(
            Location("Miami", 25.76, -80.19, "US"),
            {"properties": {"periods": [period]}},
            {"properties": {"periods": [period]}},
        )
        self.assertIsNotNone(result.daily[0].temperature_max_c)
        self.assertIsNone(result.daily[0].temperature_min_c)

    def test_nws_rejects_untrusted_forecast_endpoint(self):
        with self.assertRaises(ProviderError):
            NwsProvider._forecast_endpoint("https://evil.example/forecast")

    def test_nws_alert_outage_does_not_hide_forecast(self):
        class Client:
            def get_json(self, url, params=None):
                if "/points/" in url:
                    return {
                        "properties": {
                            "forecast": "https://api.weather.gov/gridpoints/X/1,1/forecast",
                            "forecastHourly": "https://api.weather.gov/gridpoints/X/1,1/forecast/hourly",
                        }
                    }
                if "/alerts/active" in url:
                    raise ProviderError("alerts unavailable")
                return {
                    "properties": {
                        "periods": [
                            {
                                "startTime": "2026-08-11T06:00:00-04:00",
                                "temperature": 68,
                                "temperatureUnit": "F",
                                "shortForecast": "Sunny",
                            }
                        ]
                    }
                }

        result = NwsProvider(Client()).fetch(
            Location("Miami", 25.76, -80.19, "US")
        )
        self.assertAlmostEqual(result.current.temperature_c, 20.0)
        self.assertEqual(len(result.alerts), 1)
        self.assertEqual(result.alerts[0].kind, "service-notice")
        self.assertFalse(result.alerts[0].official)

    def test_open_meteo_rejects_missing_current_temperature(self):
        with self.assertRaises(ProviderError):
            OpenMeteoProvider.parse(
                LOCATION,
                {"current": {"time": "2026-08-11T12:00", "weather_code": 0}},
            )

    def test_open_meteo_preserves_missing_apparent_temperature(self):
        result = OpenMeteoProvider.parse(
            LOCATION,
            {
                "timezone": "America/Santiago",
                "current": {
                    "time": "2026-08-11T12:00",
                    "temperature_2m": 12,
                    "weather_code": 0,
                },
            },
        )
        self.assertIsNone(result.current.apparent_temperature_c)

    def test_open_meteo_rejects_implausible_current_temperature(self):
        with self.assertRaises(ProviderError):
            OpenMeteoProvider.parse(
                LOCATION,
                {
                    "current": {
                        "time": "2026-08-11T12:00",
                        "temperature_2m": 200,
                        "weather_code": 0,
                    }
                },
            )


if __name__ == "__main__":
    unittest.main()
