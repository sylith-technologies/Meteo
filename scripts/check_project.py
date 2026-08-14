#!/usr/bin/env python3
# Copyright (C) 2026 Vicente José Leiva Escárate
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import configparser
import gettext
import json
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_ID = "io.github.sylith_technologies.Meteo"
METADATA_MESSAGES = (
    "Clear weather forecasts from multiple providers",
    "weather;forecast;temperature;rain;alerts;",
    "Clear, multi-provider weather forecasts for Linux",
    (
        "Meteo presents current conditions, a 48-hour outlook and a 15-day "
        "forecast in a responsive GNOME interface."
    ),
    (
        "Open-Meteo, MET Norway and the U.S. National Weather Service are kept "
        "visibly separate. An experimental weighted consensus is available when "
        "at least two compatible sources respond."
    ),
    (
        "Official warnings retain their original authority and are never averaged "
        "with model-derived forecast signals."
    ),
    (
        "First public alpha with privacy-safe local storage, truthful missing-data "
        "handling, bounded offline cache, provider isolation, weather and air "
        "quality, and an experimental opt-in consensus."
    ),
)


def fail(message: str) -> None:
    raise SystemExit(f"ERROR: {message}")


def validate_xml() -> None:
    schema = ROOT / "data" / f"{APP_ID}.gschema.xml"
    metainfo = ROOT / "data" / f"{APP_ID}.metainfo.xml.in"
    ET.parse(schema)
    root = ET.parse(metainfo).getroot()
    if root.findtext("id") != APP_ID:
        fail("AppStream id does not match APP_ID")
    if root.findtext("project_license") != "GPL-3.0-or-later":
        fail("AppStream must declare GPL-3.0-or-later")
    language_attribute = "{http://www.w3.org/XML/1998/namespace}lang"
    release_languages = {
        paragraph.attrib.get(language_attribute)
        for paragraph in root.findall("releases/release/description/p")
        if paragraph.attrib.get(language_attribute)
    }
    if release_languages != {"es", "pt", "fr"}:
        fail("AppStream release notes must include Spanish, Portuguese and French")


def validate_desktop() -> None:
    parser = configparser.ConfigParser(interpolation=None, strict=True)
    parser.optionxform = str
    parser.read(ROOT / "data" / f"{APP_ID}.desktop.in", encoding="utf-8")
    entry = parser["Desktop Entry"]
    if entry.get("Exec") != "meteo":
        fail("Desktop Exec must match the installed launcher")
    if entry.get("Icon") != APP_ID:
        fail("Desktop icon must match APP_ID")


def validate_manifest() -> None:
    manifest = json.loads((ROOT / f"{APP_ID}.json").read_text(encoding="utf-8"))
    if manifest.get("id") != APP_ID or manifest.get("command") != "meteo":
        fail("Flatpak id or command is inconsistent")
    if manifest.get("runtime-version") != "50":
        fail("Flatpak must target the maintained GNOME 50 runtime")
    config_options = manifest.get("modules", [{}])[0].get("config-opts", [])
    if "-Dnative_core=enabled" not in config_options:
        fail("Flatpak must enable the non-reserved native_core Meson option")


def validate_meson_options() -> None:
    options = (ROOT / "meson_options.txt").read_text(encoding="utf-8")
    core_build = (ROOT / "core-rs" / "meson.build").read_text(encoding="utf-8")
    if "'rust_core'" in options:
        fail("rust_core uses a Meson-reserved language prefix")
    if "'native_core'" not in options or "get_option('native_core')" not in core_build:
        fail("native_core Meson option is inconsistent")


def validate_version() -> None:
    expected = "0.1.0-alpha"
    meson = (ROOT / "meson.build").read_text(encoding="utf-8")
    config = (ROOT / "src" / "app" / "config.py").read_text(encoding="utf-8")
    cargo = (ROOT / "core-rs" / "Cargo.toml").read_text(encoding="utf-8")
    user_agent = (ROOT / "src" / "app" / "providers" / "http.py").read_text(encoding="utf-8")
    metadata = ET.parse(ROOT / "data" / f"{APP_ID}.metainfo.xml.in").getroot()
    if f"version: '{expected}'" not in meson:
        fail("Meson project version is inconsistent")
    if f'VERSION = "{expected}"' not in config:
        fail("Source configuration version is inconsistent")
    if f'version = "{expected}"' not in cargo:
        fail("Rust core version is inconsistent")
    if f"Meteo/{expected}" not in user_agent:
        fail("HTTP user-agent version is inconsistent")
    if metadata.find("releases/release").attrib.get("version") != expected:
        fail("Latest AppStream release version is inconsistent")


def validate_licence() -> None:
    licence = (ROOT / "LICENSE").read_text(encoding="utf-8")
    cargo = (ROOT / "core-rs" / "Cargo.toml").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    if "GNU GENERAL PUBLIC LICENSE" not in licence or "Version 3, 29 June 2007" not in licence:
        fail("LICENSE must contain the complete GNU GPL version 3 text")
    if 'license = "GPL-3.0-or-later"' not in cargo:
        fail("Rust metadata must declare GPL-3.0-or-later")
    if "GPL-3.0-or-later" not in readme:
        fail("README must state the permanent licence")


def validate_removed_stubs() -> None:
    removed = [
        "src/app/providers/google_weather.py",
        "src/app/providers/red_meteo_chile.py",
        "src/app/providers/free_weather_api.py",
    ]
    existing = [path for path in removed if (ROOT / path).exists()]
    if existing:
        fail(f"Removed provider stubs returned: {existing}")


def validate_translations() -> None:
    sources = [
        ROOT / line.strip()
        for line in (ROOT / "po" / "POTFILES.in").read_text(encoding="utf-8").splitlines()
        if line.strip().endswith(".py")
    ]
    with tempfile.TemporaryDirectory() as directory:
        template = Path(directory) / "meteo.pot"
        extraction = subprocess.run(
            [
                "xgettext",
                "--language=Python",
                "--keyword=_",
                "--keyword=N_",
                "--keyword=ngettext:1,2",
                "--from-code=UTF-8",
                f"--output={template}",
                *(str(path) for path in sources),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        if extraction.returncode:
            fail(extraction.stderr.strip() or "Could not extract source translations")

        for language in ("es", "pt", "fr"):
            catalogue = ROOT / "po" / f"{language}.po"
            compiled = Path(directory) / f"{language}.mo"
            checks = [
                ["msgfmt", "--check-format", "--check-header", "-o", str(compiled), str(catalogue)],
                ["msgcmp", str(catalogue), str(template)],
            ]
            for command in checks:
                process = subprocess.run(
                    command,
                    check=False,
                    capture_output=True,
                    text=True,
                )
                if process.returncode:
                    fail(process.stderr.strip() or f"Invalid {language} translation")
            with compiled.open("rb") as stream:
                translation = gettext.GNUTranslations(stream)
            missing_metadata = [
                message
                for message in METADATA_MESSAGES
                if translation.gettext(message) == message
            ]
            if missing_metadata:
                fail(
                    f"{language} does not translate desktop/AppStream message: "
                    f"{missing_metadata[0]}"
                )


def main() -> int:
    validate_xml()
    validate_desktop()
    validate_manifest()
    validate_meson_options()
    validate_version()
    validate_licence()
    validate_removed_stubs()
    validate_translations()
    print("Project metadata and translations are internally consistent.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
