# Development configuration. Meson replaces this file in installed builds.
# Copyright (C) 2026 Vicente José Leiva Escárate
# SPDX-License-Identifier: GPL-3.0-or-later

from pathlib import Path

APP_ID = "io.github.sylith_technologies.Meteo"
VERSION = "0.1.0-alpha"
PREFIX = str(Path(__file__).resolve().parents[2])
PKGDATADIR = PREFIX
LOCALEDIR = str(Path(PREFIX) / "po")
STYLESHEET_PATH = str(Path(PREFIX) / "data" / "style.css")
CORE_LIB_PATH = str(Path(PREFIX) / "build" / "core-rs" / "libmeteo_core.so")
