# Copyright (C) 2026 Vicente José Leiva Escárate
# SPDX-License-Identifier: GPL-3.0-or-later

import unittest

from app.domain.conditions import from_met_symbol, from_nws_text, from_wmo
from app.units import precipitation, speed, temperature


class ConditionsAndUnitsTestCase(unittest.TestCase):
    def test_condition_normalization(self):
        self.assertEqual(from_wmo(95), "thunderstorm")
        self.assertEqual(from_met_symbol("heavyrainandthunder_day"), "thunderstorm")
        self.assertEqual(from_nws_text("Partly Cloudy"), "partly-cloudy")

    def test_unit_conversion(self):
        self.assertEqual(temperature(0, "imperial"), "32°F")
        self.assertEqual(speed(16.09344, "imperial"), "10.0 mph")
        self.assertEqual(precipitation(25.4, "imperial"), "1.00 in")


if __name__ == "__main__":
    unittest.main()
