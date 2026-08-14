# Copyright (C) 2026 Vicente José Leiva Escárate
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import os
from pathlib import Path

APP_DIR_NAME = "meteo"


def _xdg_path(variable: str, fallback: Path) -> Path:
    value = os.environ.get(variable)
    return Path(value).expanduser() if value else fallback


def data_dir() -> Path:
    return _xdg_path("XDG_DATA_HOME", Path.home() / ".local" / "share") / APP_DIR_NAME


def cache_dir() -> Path:
    return _xdg_path("XDG_CACHE_HOME", Path.home() / ".cache") / APP_DIR_NAME


def config_dir() -> Path:
    return _xdg_path("XDG_CONFIG_HOME", Path.home() / ".config") / APP_DIR_NAME


def custom_providers_path() -> Path:
    return data_dir() / "custom-providers.json"


def custom_translations_dir() -> Path:
    return data_dir() / "translations"

