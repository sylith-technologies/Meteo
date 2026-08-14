# Copyright (C) 2026 Vicente José Leiva Escárate
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import Optional


def temperature(value_c: Optional[float], system: str, decimals: int = 0) -> str:
    if value_c is None:
        return "—"
    value = value_c * 9.0 / 5.0 + 32.0 if system == "imperial" else value_c
    suffix = "°F" if system == "imperial" else "°C"
    return f"{value:.{decimals}f}{suffix}"


def speed(value_kmh: Optional[float], system: str) -> str:
    if value_kmh is None:
        return "—"
    if system == "imperial":
        return f"{value_kmh / 1.609344:.1f} mph"
    return f"{value_kmh:.1f} km/h"


def precipitation(value_mm: Optional[float], system: str) -> str:
    if value_mm is None:
        return "—"
    if system == "imperial":
        return f"{value_mm / 25.4:.2f} in"
    return f"{value_mm:.1f} mm"


def visibility(value_km: Optional[float], system: str) -> str:
    if value_km is None:
        return "—"
    if system == "imperial":
        return f"{value_km / 1.609344:.1f} mi"
    return f"{value_km:.1f} km"

