# Copyright (C) 2026 Vicente José Leiva Escárate
# SPDX-License-Identifier: GPL-3.0-or-later

"""Maps provider-specific weather codes into a stable Meteo vocabulary."""

from __future__ import annotations

from typing import Dict, Tuple

from app.i18n import N_

CONDITIONS: Dict[str, Tuple[str, str]] = {
    "clear": (N_("Clear sky"), "weather-clear-symbolic"),
    "mostly-clear": (N_("Mostly clear"), "weather-few-clouds-symbolic"),
    "partly-cloudy": (N_("Partly cloudy"), "weather-few-clouds-symbolic"),
    "cloudy": (N_("Cloudy"), "weather-overcast-symbolic"),
    "fog": (N_("Fog"), "weather-fog-symbolic"),
    "drizzle": (N_("Drizzle"), "weather-showers-scattered-symbolic"),
    "rain": (N_("Rain"), "weather-showers-symbolic"),
    "heavy-rain": (N_("Heavy rain"), "weather-showers-symbolic"),
    "snow": (N_("Snow"), "weather-snow-symbolic"),
    "heavy-snow": (N_("Heavy snow"), "weather-snow-symbolic"),
    "showers": (N_("Rain showers"), "weather-showers-scattered-symbolic"),
    "snow-showers": (N_("Snow showers"), "weather-snow-symbolic"),
    "thunderstorm": (N_("Thunderstorm"), "weather-storm-symbolic"),
    "unknown": (N_("Unknown conditions"), "weather-severe-alert-symbolic"),
}


def condition_label(code: str) -> str:
    return CONDITIONS.get(code, CONDITIONS["unknown"])[0]


def condition_icon(code: str) -> str:
    return CONDITIONS.get(code, CONDITIONS["unknown"])[1]


def from_wmo(code: int) -> str:
    if code == 0:
        return "clear"
    if code == 1:
        return "mostly-clear"
    if code == 2:
        return "partly-cloudy"
    if code == 3:
        return "cloudy"
    if code in (45, 48):
        return "fog"
    if code in (51, 53, 55, 56, 57):
        return "drizzle"
    if code in (61, 63, 66, 80, 81):
        return "showers" if code >= 80 else "rain"
    if code in (65, 67, 82):
        return "heavy-rain"
    if code in (71, 73, 77):
        return "snow"
    if code == 75:
        return "heavy-snow"
    if code in (85, 86):
        return "snow-showers"
    if code in (95, 96, 99):
        return "thunderstorm"
    return "unknown"


def from_met_symbol(symbol: str) -> str:
    value = symbol.lower().replace("_day", "").replace("_night", "").replace("_polartwilight", "")
    if value in {"clearsky"}:
        return "clear"
    if value in {"fair"}:
        return "mostly-clear"
    if value in {"partlycloudy"}:
        return "partly-cloudy"
    if value in {"cloudy"}:
        return "cloudy"
    if "fog" in value:
        return "fog"
    if "thunder" in value:
        return "thunderstorm"
    if "heavyrain" in value:
        return "heavy-rain"
    if "rain" in value or "sleet" in value:
        return "rain"
    if "heavysnow" in value:
        return "heavy-snow"
    if "snow" in value:
        return "snow"
    return "unknown"


def from_nws_text(text: str) -> str:
    value = text.lower()
    if "thunder" in value or "tornado" in value:
        return "thunderstorm"
    if "heavy rain" in value:
        return "heavy-rain"
    if "rain" in value or "shower" in value:
        return "showers"
    if "snow" in value or "blizzard" in value:
        return "snow"
    if "fog" in value or "mist" in value:
        return "fog"
    if "partly" in value or "mostly sunny" in value or "mostly clear" in value:
        return "partly-cloudy"
    if "cloud" in value or "overcast" in value:
        return "cloudy"
    if "sun" in value or "clear" in value:
        return "clear"
    return "unknown"
