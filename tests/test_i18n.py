# Copyright (C) 2026 Vicente José Leiva Escárate
# SPDX-License-Identifier: GPL-3.0-or-later

import json
import tempfile
import unittest
from pathlib import Path

from app.i18n import TranslationManager, localized_date_label, translations


class TranslationManagerTestCase(unittest.TestCase):
    def test_daily_date_uses_selected_app_translation(self):
        previous = translations._custom_messages
        try:
            translations._custom_messages = {"Thu": "Jue", "Aug": "Ago"}
            self.assertEqual(localized_date_label("2026-08-13"), "Jue 13 Ago")
        finally:
            translations._custom_messages = previous

    def test_loads_safe_custom_language_pack(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "eo.json").write_text(
                json.dumps(
                    {
                        "code": "eo",
                        "name": "Esperanto",
                        "messages": {"Weather": "Vetero"},
                    }
                ),
                encoding="utf-8",
            )
            manager = TranslationManager()
            manager.configure(str(root / "locale"), root, "eo")
            self.assertIn(("eo", "Esperanto"), manager.languages())
            self.assertEqual(manager.gettext("Weather"), "Vetero")

    def test_rejects_path_traversal_language_code(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "unsafe.json").write_text(
                json.dumps(
                    {
                        "code": "../../unsafe",
                        "name": "Unsafe",
                        "messages": {"Weather": "Bad"},
                    }
                ),
                encoding="utf-8",
            )
            manager = TranslationManager()
            manager.configure(str(root / "locale"), root, "../../unsafe")
            self.assertEqual(manager.language, "system")
            self.assertNotIn(("../../unsafe", "Unsafe"), manager.languages())

    def test_ignores_translation_with_incompatible_format_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "eo.json").write_text(
                json.dumps(
                    {
                        "code": "eo",
                        "name": "Esperanto",
                        "messages": {
                            "High {high} · Low {low}": "Alta {high}",
                            "Weather": "Vetero",
                        },
                    }
                ),
                encoding="utf-8",
            )
            manager = TranslationManager()
            manager.configure(str(root / "locale"), root, "eo")
            self.assertEqual(
                manager.gettext("High {high} · Low {low}"),
                "High {high} · Low {low}",
            )
            self.assertEqual(manager.gettext("Weather"), "Vetero")

    def test_ignores_translation_with_changed_format_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "eo.json").write_text(
                json.dumps(
                    {
                        "code": "eo",
                        "name": "Esperanto",
                        "messages": {
                            "Value {count:.1f}": "Valoro {count:not-a-format}",
                            "Item {name!s}": "Ero {name!r}",
                        },
                    }
                ),
                encoding="utf-8",
            )
            manager = TranslationManager()
            manager.configure(str(root / "locale"), root, "eo")
            self.assertEqual(
                manager.gettext("Value {count:.1f}"),
                "Value {count:.1f}",
            )
            self.assertEqual(manager.gettext("Item {name!s}"), "Item {name!s}")

    def test_ignores_non_object_translation_pack(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "eo.json").write_text("[]", encoding="utf-8")
            manager = TranslationManager()
            manager.configure(str(root / "locale"), root, "eo")
            self.assertEqual(manager.gettext("Weather"), "Weather")

    def test_ignores_custom_language_with_an_oversized_name(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "eo.json").write_text(
                json.dumps(
                    {
                        "code": "eo",
                        "name": "x" * 81,
                        "messages": {"Weather": "Vetero"},
                    }
                ),
                encoding="utf-8",
            )
            manager = TranslationManager()
            manager.configure(str(root / "locale"), root, "eo")
            self.assertNotIn("eo", dict(manager.languages()))
            self.assertEqual(manager.gettext("Weather"), "Weather")


if __name__ == "__main__":
    unittest.main()
