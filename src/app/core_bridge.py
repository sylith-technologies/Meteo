# Copyright (C) 2026 Vicente José Leiva Escárate
# SPDX-License-Identifier: GPL-3.0-or-later

"""Small, optional bridge to the dependency-free Rust core.

Meteo remains functional when the native library is unavailable. The fallback
is intentional for source development; official Flatpak builds include it.
"""

from __future__ import annotations

import ctypes
import math
from pathlib import Path
from typing import Iterable, Optional

try:
    from app import config
except ImportError:  # Tests can import the domain without a Meson install.
    config = None


class NativeCore:
    def __init__(self, library_path: Optional[str] = None):
        candidates = []
        if library_path:
            candidates.append(Path(library_path))
        if config and getattr(config, "CORE_LIB_PATH", ""):
            candidates.append(Path(config.CORE_LIB_PATH))
        candidates.extend(
            [
                Path(__file__).resolve().parents[2] / "build" / "core-rs" / "libmeteo_core.so",
                Path(__file__).resolve().parents[2] / "build" / "libmeteo_core.so",
            ]
        )

        self._library = None
        for candidate in candidates:
            if not candidate.is_file():
                continue
            try:
                self._library = ctypes.CDLL(str(candidate))
                break
            except OSError:
                continue

        if self._library:
            self._library.meteo_validate_coordinates.argtypes = [ctypes.c_double, ctypes.c_double]
            self._library.meteo_validate_coordinates.restype = ctypes.c_int
            self._library.meteo_weighted_mean.argtypes = [
                ctypes.POINTER(ctypes.c_double),
                ctypes.POINTER(ctypes.c_double),
                ctypes.c_size_t,
            ]
            self._library.meteo_weighted_mean.restype = ctypes.c_double

    @property
    def available(self) -> bool:
        return self._library is not None

    def validate_coordinates(self, latitude: float, longitude: float) -> bool:
        if self._library:
            return bool(self._library.meteo_validate_coordinates(latitude, longitude))
        return (
            math.isfinite(latitude)
            and math.isfinite(longitude)
            and -90.0 <= latitude <= 90.0
            and -180.0 <= longitude <= 180.0
        )

    def weighted_mean(self, values: Iterable[float], weights: Iterable[float]) -> float:
        value_list = [float(value) for value in values]
        weight_list = [max(0.0, float(weight)) for weight in weights]
        if not value_list or len(value_list) != len(weight_list):
            raise ValueError("Values and weights must be non-empty and have equal length")
        total_weight = sum(weight_list)
        if total_weight <= 0.0:
            raise ValueError("At least one weight must be positive")

        if self._library:
            length = len(value_list)
            values_array = (ctypes.c_double * length)(*value_list)
            weights_array = (ctypes.c_double * length)(*weight_list)
            result = self._library.meteo_weighted_mean(values_array, weights_array, length)
            if math.isfinite(result):
                return float(result)

        return sum(value * weight for value, weight in zip(value_list, weight_list)) / total_weight


native_core = NativeCore()
