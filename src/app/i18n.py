# Copyright (C) 2026 Vicente José Leiva Escárate
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import gettext
import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from string import Formatter
from typing import Dict, List, Tuple


def N_(message: str) -> str:
    """Marks a string for extraction while deferring translation to the UI."""

    return message


BUILTIN_LANGUAGES = {
    "system": N_("System language"),
    "en": N_("English"),
    "es": N_("Spanish"),
    "pt": N_("Portuguese"),
    "fr": N_("French"),
}
LANGUAGE_CODE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,31}$")


def _format_signature(message: str) -> Counter:
    """Returns every replacement field, including its formatting contract."""

    return Counter(
        (field, format_spec, conversion)
        for _literal, field, format_spec, conversion in Formatter().parse(message)
        if field is not None
    )


class TranslationManager:
    def __init__(self):
        self.localedir = Path("/usr/share/locale")
        self.custom_directory = Path.home() / ".local" / "share" / "meteo" / "translations"
        self.language = "system"
        self._translation = gettext.NullTranslations()
        self._custom_messages: Dict[str, str] = {}

    def configure(self, localedir: str, custom_directory: Path, language: str) -> None:
        self.localedir = Path(localedir)
        self.custom_directory = custom_directory
        self.set_language(language)

    def set_language(self, language: str) -> None:
        if language != "system" and not LANGUAGE_CODE.fullmatch(language):
            language = "system"
        self.language = language
        selected = None if language == "system" else [language]
        self._translation = gettext.translation(
            "meteo",
            localedir=str(self.localedir),
            languages=selected,
            fallback=True,
        )
        self._custom_messages = self._load_custom(language)

    def _load_custom(self, language: str) -> Dict[str, str]:
        if language in BUILTIN_LANGUAGES or language == "system":
            return {}
        path = self.custom_directory / f"{language}.json"
        try:
            if path.stat().st_size > 1_000_000:
                return {}
            payload = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                return {}
            code = payload.get("code", language)
            name = payload.get("name", code)
            if (
                not isinstance(code, str)
                or code != language
                or not isinstance(name, str)
                or not 0 < len(name.strip()) <= 80
            ):
                return {}
            messages = payload.get("messages", {})
            if not isinstance(messages, dict):
                return {}
            safe_messages: Dict[str, str] = {}
            for key, value in messages.items():
                if not isinstance(key, str) or not isinstance(value, str):
                    continue
                if len(key) > 8_192 or len(value) > 8_192:
                    continue
                try:
                    source_fields = _format_signature(key)
                    translated_fields = _format_signature(value)
                except ValueError:
                    continue
                if source_fields == translated_fields:
                    safe_messages[key] = value
            return safe_messages
        except (OSError, json.JSONDecodeError, TypeError):
            return {}

    def gettext(self, message: str) -> str:
        return self._custom_messages.get(message, self._translation.gettext(message))

    def ngettext(self, singular: str, plural: str, number: int) -> str:
        selected = singular if number == 1 else plural
        if selected in self._custom_messages:
            return self._custom_messages[selected]
        return self._translation.ngettext(singular, plural, number)

    def languages(self) -> List[Tuple[str, str]]:
        result = [(code, self.gettext(name)) for code, name in BUILTIN_LANGUAGES.items()]
        if self.custom_directory.is_dir():
            for path in sorted(self.custom_directory.glob("*.json")):
                try:
                    if path.stat().st_size > 1_000_000:
                        continue
                    payload = json.loads(path.read_text(encoding="utf-8"))
                    if not isinstance(payload, dict):
                        continue
                    code = str(payload.get("code", path.stem))
                    raw_name = payload.get("name", code)
                    if not isinstance(raw_name, str):
                        continue
                    name = raw_name.strip()
                    if (
                        code == path.stem
                        and LANGUAGE_CODE.fullmatch(code)
                        and 0 < len(name) <= 80
                        and code not in dict(result)
                    ):
                        result.append((code, name))
                except (OSError, json.JSONDecodeError, TypeError):
                    continue
        return result


translations = TranslationManager()
_ = translations.gettext
ngettext = translations.ngettext


def localized_date_label(value: str) -> str:
    """Formats an ISO date with Meteo's selected language, not the OS locale."""

    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return value
    weekdays = (_("Mon"), _("Tue"), _("Wed"), _("Thu"), _("Fri"), _("Sat"), _("Sun"))
    months = (
        _("Jan"), _("Feb"), _("Mar"), _("Apr"), _("May"), _("Jun"),
        _("Jul"), _("Aug"), _("Sep"), _("Oct"), _("Nov"), _("Dec"),
    )
    return f"{weekdays[parsed.weekday()]} {parsed.day:02d} {months[parsed.month - 1]}"
