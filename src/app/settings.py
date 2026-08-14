# Copyright (C) 2026 Vicente José Leiva Escárate
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import json
import locale
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.models import Location
from app.paths import config_dir
from app.storage import atomic_write_text

try:
    from gi.repository import Gio
except (ImportError, ValueError):
    Gio = None


APP_ID = "io.github.sylith_technologies.Meteo"
DEFAULTS: Dict[str, Any] = {
    "saved-locations": "[]",
    "active-location-key": "",
    "enabled-providers": ["open-meteo"],
    "provider-mode": "open-meteo",
    "unit-system": "auto",
    "color-scheme": "system",
    "language": "system",
    "update-interval": 30,
    "show-forecast-signals": True,
    "seen-alert-ids": [],
}


class SettingsManager:
    """GSettings-backed preferences with a JSON fallback for source tests."""

    def __init__(self, fallback_path: Optional[Path] = None):
        self._settings = None
        if Gio is not None:
            try:
                schema_source = Gio.SettingsSchemaSource.get_default()
                schema = schema_source.lookup(APP_ID, True) if schema_source else None
                if schema is not None:
                    self._settings = Gio.Settings.new_full(schema, None, None)
            except Exception:
                self._settings = None
        self._fallback_path = fallback_path or (config_dir() / "settings.json")
        self._fallback = self._load_fallback()

    def _load_fallback(self) -> Dict[str, Any]:
        try:
            value = json.loads(self._fallback_path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    def _save_fallback(self) -> None:
        atomic_write_text(
            self._fallback_path,
            json.dumps(self._fallback, ensure_ascii=False, indent=2),
        )

    def _get(self, key: str) -> Any:
        if self._settings:
            default = DEFAULTS[key]
            if isinstance(default, bool):
                return self._settings.get_boolean(key)
            if isinstance(default, int):
                return self._settings.get_int(key)
            if isinstance(default, list):
                return list(self._settings.get_strv(key))
            return self._settings.get_string(key)
        return self._fallback.get(key, DEFAULTS[key])

    def _set(self, key: str, value: Any) -> None:
        if self._settings:
            default = DEFAULTS[key]
            if isinstance(default, bool):
                self._settings.set_boolean(key, bool(value))
            elif isinstance(default, int):
                self._settings.set_int(key, int(value))
            elif isinstance(default, list):
                self._settings.set_strv(key, list(value))
            else:
                self._settings.set_string(key, str(value))
            return
        self._fallback[key] = value
        self._save_fallback()

    def locations(self) -> List[Location]:
        try:
            values = json.loads(self._get("saved-locations"))
            return [Location.from_dict(value) for value in values if isinstance(value, dict)][:5]
        except (ValueError, TypeError, json.JSONDecodeError, KeyError):
            return []

    def save_location(self, location: Location) -> bool:
        locations = [item for item in self.locations() if item.key != location.key]
        if len(locations) >= 5:
            return False
        locations.insert(0, location)
        self._set(
            "saved-locations",
            json.dumps([item.to_dict() for item in locations[:5]], ensure_ascii=False),
        )
        self._set("active-location-key", location.key)
        return True

    def remove_location(self, key: str) -> None:
        locations = [item for item in self.locations() if item.key != key]
        self._set("saved-locations", json.dumps([item.to_dict() for item in locations]))
        if self._get("active-location-key") == key:
            self._set("active-location-key", locations[0].key if locations else "")

    def clear_locations(self) -> None:
        self._set("saved-locations", "[]")
        self._set("active-location-key", "")

    def active_location(self) -> Optional[Location]:
        locations = self.locations()
        active_key = self._get("active-location-key")
        return next((item for item in locations if item.key == active_key), locations[0] if locations else None)

    def set_active_location(self, key: str) -> None:
        if any(location.key == key for location in self.locations()):
            self._set("active-location-key", key)

    def enabled_providers(self) -> List[str]:
        value = self._get("enabled-providers")
        if not isinstance(value, (list, tuple)):
            return ["open-meteo"]
        providers = [
            item
            for item in value
            if isinstance(item, str) and 0 < len(item) <= 80
        ]
        return list(dict.fromkeys(providers))[:16] or ["open-meteo"]

    def set_enabled_providers(self, providers: List[str]) -> None:
        unique = list(dict.fromkeys(providers))
        self._set("enabled-providers", unique or ["open-meteo"])

    @property
    def provider_mode(self) -> str:
        return str(self._get("provider-mode"))

    @provider_mode.setter
    def provider_mode(self, value: str) -> None:
        self._set("provider-mode", value)

    @property
    def unit_system(self) -> str:
        value = str(self._get("unit-system"))
        return value if value in {"auto", "metric", "imperial"} else "auto"

    @unit_system.setter
    def unit_system(self, value: str) -> None:
        self._set("unit-system", value if value in {"auto", "metric", "imperial"} else "auto")

    def resolved_unit_system(self) -> str:
        if self.unit_system != "auto":
            return self.unit_system
        locale_name = locale.getlocale()[0] or ""
        country = locale_name.split("_")[-1].upper() if "_" in locale_name else ""
        return "imperial" if country in {"US", "LR", "MM"} else "metric"

    @property
    def color_scheme(self) -> str:
        value = str(self._get("color-scheme"))
        return value if value in {"system", "light", "dark"} else "system"

    @color_scheme.setter
    def color_scheme(self, value: str) -> None:
        self._set("color-scheme", value if value in {"system", "light", "dark"} else "system")

    @property
    def language(self) -> str:
        return str(self._get("language"))

    @language.setter
    def language(self, value: str) -> None:
        self._set("language", value)

    def resolved_language(self) -> str:
        if self.language != "system":
            return self.language if self.language in {"en", "es", "pt", "fr"} else "en"
        locale_name = locale.getlocale()[0] or "en"
        language = locale_name.split("_", 1)[0].split("-", 1)[0].lower()
        return language if language in {"en", "es", "pt", "fr"} else "en"

    @property
    def update_interval_minutes(self) -> int:
        try:
            value = int(self._get("update-interval"))
        except (TypeError, ValueError):
            value = int(DEFAULTS["update-interval"])
        return min(180, max(10, value))

    @property
    def show_forecast_signals(self) -> bool:
        value = self._get("show-forecast-signals")
        return value if isinstance(value, bool) else bool(DEFAULTS["show-forecast-signals"])

    @show_forecast_signals.setter
    def show_forecast_signals(self, value: bool) -> None:
        self._set("show-forecast-signals", value)

    def seen_alert_ids(self) -> List[str]:
        value = self._get("seen-alert-ids")
        if not isinstance(value, (list, tuple)):
            return []
        return [item[:500] for item in value if isinstance(item, str)][:50]

    def mark_alerts_seen(self, alert_ids: List[str]) -> None:
        combined = list(dict.fromkeys(alert_ids + self.seen_alert_ids()))
        self._set("seen-alert-ids", combined[:50])

    def reset_preferences(self) -> None:
        location_keys = {"saved-locations", "active-location-key"}
        if self._settings:
            for key in DEFAULTS:
                if key not in location_keys:
                    self._settings.reset(key)
            return
        for key in DEFAULTS:
            if key not in location_keys:
                self._fallback.pop(key, None)
        self._save_fallback()

    def reset(self) -> None:
        if self._settings:
            for key in DEFAULTS:
                self._settings.reset(key)
        self._fallback = {}
        try:
            self._fallback_path.unlink()
        except FileNotFoundError:
            pass
