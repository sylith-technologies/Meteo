# Copyright (C) 2026 Vicente José Leiva Escárate
# SPDX-License-Identifier: GPL-3.0-or-later

import json
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_ID = "io.github.sylith_technologies.Meteo"


class MetadataTestCase(unittest.TestCase):
    def test_development_version_is_consistent(self):
        meson = (ROOT / "meson.build").read_text(encoding="utf-8")
        config = (ROOT / "src" / "app" / "config.py").read_text(encoding="utf-8")
        cargo = (ROOT / "core-rs" / "Cargo.toml").read_text(encoding="utf-8")
        user_agent = (ROOT / "src" / "app" / "providers" / "http.py").read_text(encoding="utf-8")
        metadata = ET.parse(ROOT / "data" / f"{APP_ID}.metainfo.xml.in").getroot()
        self.assertIn("version: '0.1.0-alpha'", meson)
        self.assertIn('VERSION = "0.1.0-alpha"', config)
        self.assertIn('version = "0.1.0-alpha"', cargo)
        self.assertIn("Meteo/0.1.0-alpha", user_agent)
        self.assertEqual(metadata.find("releases/release").attrib["version"], "0.1.0-alpha")

    def test_weather_cards_include_combined_sun_and_aqi_presentation(self):
        weather_page = (ROOT / "src" / "app" / "ui" / "weather_page.py").read_text(encoding="utf-8")
        stylesheet = (ROOT / "data" / "style.css").read_text(encoding="utf-8")
        self.assertIn("class SunTimesCard", weather_page)
        self.assertIn('"weather-fog-symbolic"', weather_page)
        self.assertIn("aqi-good", stylesheet)
        self.assertIn("metric-sun", stylesheet)

    def test_high_contrast_css_supports_declared_gtk_minimum(self):
        window = (ROOT / "src" / "app" / "ui" / "window.py").read_text(encoding="utf-8")
        stylesheet = (ROOT / "data" / "style.css").read_text(encoding="utf-8")
        self.assertNotIn("@media (prefers-contrast", stylesheet)
        self.assertIn(".high-contrast .hero-card", stylesheet)
        self.assertIn("get_high_contrast()", window)

    def test_ids_and_commands_are_consistent(self):
        manifest = json.loads((ROOT / f"{APP_ID}.json").read_text(encoding="utf-8"))
        metadata = ET.parse(ROOT / "data" / f"{APP_ID}.metainfo.xml.in").getroot()
        desktop = (ROOT / "data" / f"{APP_ID}.desktop.in").read_text(encoding="utf-8")
        self.assertEqual(manifest["id"], APP_ID)
        self.assertEqual(manifest["command"], "meteo")
        self.assertEqual(metadata.findtext("id"), APP_ID)
        self.assertIn("Exec=meteo", desktop)
        self.assertIn(f"Icon={APP_ID}", desktop)
        self.assertIn("DBusActivatable=false", desktop)

    def test_manifest_has_no_unused_python_packages(self):
        manifest_text = (ROOT / f"{APP_ID}.json").read_text(encoding="utf-8")
        self.assertNotIn("matplotlib", manifest_text.lower())
        self.assertNotIn("requests", manifest_text.lower())
        self.assertNotIn("jsonpath", manifest_text.lower())

    def test_meson_native_core_option_does_not_use_reserved_rust_prefix(self):
        options = (ROOT / "meson_options.txt").read_text(encoding="utf-8")
        core_build = (ROOT / "core-rs" / "meson.build").read_text(encoding="utf-8")
        manifest = (ROOT / f"{APP_ID}.json").read_text(encoding="utf-8")
        self.assertIn("'native_core'", options)
        self.assertIn("get_option('native_core')", core_build)
        self.assertIn("-Dnative_core=enabled", manifest)
        self.assertNotIn("'rust_core'", options)

    def test_launcher_finds_schemas_in_custom_install_prefix(self):
        source_build = (ROOT / "src" / "meson.build").read_text(encoding="utf-8")
        launcher = (ROOT / "src" / "meteo.in").read_text(encoding="utf-8")
        self.assertIn("'GSETTINGS_SCHEMA_DIR'", source_build)
        self.assertIn('export GSETTINGS_SCHEMA_DIR="@GSETTINGS_SCHEMA_DIR@"', launcher)

    def test_meson_install_excludes_nested_python_bytecode(self):
        source_build = (ROOT / "src" / "meson.build").read_text(encoding="utf-8")
        for directory in (
            "__pycache__",
            "domain/__pycache__",
            "providers/__pycache__",
            "services/__pycache__",
            "ui/__pycache__",
            "ui/widgets/__pycache__",
            "utils/__pycache__",
        ):
            self.assertIn(f"'{directory}'", source_build)

    def test_location_rows_are_activatable_with_one_click(self):
        window = (ROOT / "src" / "app" / "ui" / "window.py").read_text(encoding="utf-8")
        dialogs = (ROOT / "src" / "app" / "ui" / "dialogs.py").read_text(encoding="utf-8")
        self.assertIn("self.location_list.set_activate_on_single_click(True)", window)
        self.assertIn("self.results.set_activate_on_single_click(True)", dialogs)
        self.assertIn("row.set_activatable(True)", window)
        self.assertIn("row.set_activatable(True)", dialogs)

    def test_first_run_shows_welcome_content_when_collapsed(self):
        window = (ROOT / "src" / "app" / "ui" / "window.py").read_text(encoding="utf-8")
        welcome_method = window.split("def _show_welcome", 1)[1].split("def _rebuild_locations", 1)[0]
        self.assertIn('set_visible_child_name("welcome")', welcome_method)
        self.assertIn("self.split.set_show_content(True)", welcome_method)

    def test_bug_report_uses_the_reviewed_diagnostics_snapshot(self):
        dialogs = (ROOT / "src" / "app" / "ui" / "dialogs.py").read_text(encoding="utf-8")
        self.assertIn("self._diagnostics = collect_diagnostics", dialogs)
        self.assertIn("self.consent.set_active(False)", dialogs)
        self.assertIn("return description, dict(self._diagnostics)", dialogs)

    def test_official_alert_text_bypasses_gettext(self):
        dialogs = (ROOT / "src" / "app" / "ui" / "dialogs.py").read_text(encoding="utf-8")
        weather_page = (ROOT / "src" / "app" / "ui" / "weather_page.py").read_text(encoding="utf-8")
        self.assertIn("return value if alert.official else _(value)", dialogs)
        self.assertIn("return alert.title if alert.official else _(alert.title)", weather_page)

    def test_gpl_metadata_and_full_licence_are_consistent(self):
        metadata = ET.parse(ROOT / "data" / f"{APP_ID}.metainfo.xml.in").getroot()
        cargo = (ROOT / "core-rs" / "Cargo.toml").read_text(encoding="utf-8")
        licence = (ROOT / "LICENSE").read_text(encoding="utf-8")
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        about = (ROOT / "src" / "app" / "ui" / "window.py").read_text(encoding="utf-8")
        self.assertEqual(metadata.findtext("project_license"), "GPL-3.0-or-later")
        self.assertIn('license = "GPL-3.0-or-later"', cargo)
        self.assertIn("GNU GENERAL PUBLIC LICENSE", licence)
        self.assertIn("Version 3, 29 June 2007", licence)
        self.assertIn("GPL-3.0-or-later", readme)
        self.assertIn("Gtk.License.CUSTOM", about)
        self.assertIn("GPL-3.0-or-later", about)

    def test_distribution_keeps_required_gpl_and_removes_redundant_decision_file(self):
        self.assertTrue((ROOT / "LICENSE").is_file())
        self.assertFalse((ROOT / "legal" / "LICENSE_DECISION.md").exists())
        self.assertTrue((ROOT / "DOCS").is_dir())


if __name__ == "__main__":
    unittest.main()
