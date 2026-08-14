# Copyright (C) 2026 Vicente José Leiva Escárate
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import hashlib
import json
import threading
import time
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Iterable, Optional, Tuple
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.models import Location, WeatherBundle, WeatherReport
from app.paths import cache_dir
from app.storage import atomic_write_text, ensure_private_directory


class WeatherCache:
    FORMAT_VERSION = 1

    def __init__(
        self,
        directory: Optional[Path] = None,
        fresh_seconds: int = 600,
        max_offline_seconds: int = 172_800,
    ):
        self.directory = directory or (cache_dir() / "weather")
        self.fresh_seconds = fresh_seconds
        self.max_offline_seconds = max_offline_seconds
        self._generation = 0
        self._write_lock = threading.Lock()

    def write_generation(self) -> int:
        with self._write_lock:
            return self._generation

    @staticmethod
    def _digest(location: Location, mode: str, providers: Iterable[str]) -> str:
        raw = f"{location.key}|{mode}|{'|'.join(sorted(providers))}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def _path(self, location: Location, mode: str, providers: Iterable[str]) -> Path:
        return self.directory / f"{self._digest(location, mode, providers)}.json"

    @staticmethod
    def _forecast_time(value: str, timezone_name: str) -> Optional[datetime]:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                try:
                    parsed = parsed.replace(tzinfo=ZoneInfo(timezone_name))
                except ZoneInfoNotFoundError:
                    parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except (TypeError, ValueError):
            return None

    @classmethod
    def _remove_expired_forecast(cls, bundle: WeatherBundle) -> WeatherBundle:
        now = datetime.now(timezone.utc)
        hourly = [
            hour
            for hour in bundle.hourly
            if (
                (parsed := cls._forecast_time(hour.time, bundle.timezone)) is not None
                and parsed >= now - timedelta(hours=1)
            )
        ]
        try:
            local_zone = ZoneInfo(bundle.timezone)
        except ZoneInfoNotFoundError:
            local_zone = timezone.utc
        today = now.astimezone(local_zone).date()
        daily = []
        for day in bundle.daily:
            try:
                if datetime.fromisoformat(day.date).date() >= today:
                    daily.append(day)
            except (TypeError, ValueError):
                continue
        return replace(bundle, hourly=hourly, daily=daily)

    def store(
        self,
        location: Location,
        mode: str,
        providers: Iterable[str],
        report: WeatherReport,
        expected_generation: Optional[int] = None,
    ) -> bool:
        path = self._path(location, mode, providers)
        payload = {
            "format": self.FORMAT_VERSION,
            "stored_at": time.time(),
            "mode": report.mode,
            "display": report.display.to_dict(),
            "sources": [source.to_dict() for source in report.sources],
            "errors": report.errors,
        }
        with self._write_lock:
            if (
                expected_generation is not None
                and expected_generation != self._generation
            ):
                return False
            ensure_private_directory(path.parent)
            atomic_write_text(path, json.dumps(payload, ensure_ascii=False))
            return True

    def load(
        self,
        location: Location,
        mode: str,
        providers: Iterable[str],
        allow_stale: bool = True,
    ) -> Optional[Tuple[WeatherReport, bool]]:
        path = self._path(location, mode, providers)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if self._is_expired(payload):
                self._unlink(path)
                return None
            return self._decode(payload, mode, allow_stale)
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
            return None

    def _decode(
        self,
        payload: Dict[str, object],
        mode: str,
        allow_stale: bool,
    ) -> Optional[Tuple[WeatherReport, bool]]:
        try:
            if payload.get("format") != self.FORMAT_VERSION:
                return None
            age = max(0.0, time.time() - float(payload["stored_at"]))
            stale = age > self.fresh_seconds
            if stale and not allow_stale:
                return None
            if stale and age > self.max_offline_seconds:
                return None
            sources = [
                replace(WeatherBundle.from_dict(value), stale=stale)
                for value in payload.get("sources", [])
            ]
            display = replace(WeatherBundle.from_dict(payload["display"]), stale=stale)
            if stale:
                sources = [self._remove_expired_forecast(source) for source in sources]
                display = self._remove_expired_forecast(display)
            return (
                WeatherReport(
                    display=display,
                    sources=sources,
                    errors=dict(payload.get("errors", {})),
                    mode=str(payload.get("mode", mode)),
                    from_cache=True,
                ),
                stale,
            )
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
            return None

    def _is_expired(self, payload: Dict[str, object]) -> bool:
        try:
            age = max(0.0, time.time() - float(payload["stored_at"]))
            return age > self.max_offline_seconds
        except (ValueError, TypeError, KeyError):
            return True

    @staticmethod
    def _unlink(path: Path) -> None:
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        except OSError:
            pass

    def load_latest(self, location: Location) -> Optional[Tuple[WeatherReport, bool]]:
        """Returns the newest still-usable cache even if provider settings changed."""

        if not self.directory.exists():
            return None
        candidates = []
        for path in self.directory.glob("*.json"):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                if self._is_expired(payload):
                    self._unlink(path)
                    continue
                cached_location = Location.from_dict(payload["display"]["location"])
                if cached_location.key == location.key:
                    candidates.append((float(payload["stored_at"]), payload))
            except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
                continue
        for _stored_at, payload in sorted(candidates, key=lambda item: item[0], reverse=True):
            decoded = self._decode(payload, str(payload.get("mode", "consensus")), True)
            if decoded:
                return decoded
        return None

    def clear(self) -> None:
        with self._write_lock:
            self._generation += 1
            if not self.directory.exists():
                return
            for path in self.directory.glob("*.json"):
                self._unlink(path)

    def clear_location(self, location: Location) -> None:
        """Deletes every cached provider/mode combination for one location."""

        with self._write_lock:
            self._generation += 1
            if not self.directory.exists():
                return
            for path in self.directory.glob("*.json"):
                try:
                    payload = json.loads(path.read_text(encoding="utf-8"))
                    cached_location = Location.from_dict(payload["display"]["location"])
                    if cached_location.key == location.key:
                        self._unlink(path)
                except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
                    continue
