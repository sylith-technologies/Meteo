# Copyright (C) 2026 Vicente José Leiva Escárate
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import hashlib
import json
import logging
import math
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import zlib
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

from app.providers.base import ProviderError
from app.storage import atomic_write_text


USER_AGENT = "Meteo/0.1.0-alpha (+https://github.com/sylith-technologies/Meteo)"
logger = logging.getLogger(__name__)


class HttpStatusError(ProviderError):
    def __init__(self, status_code: int, headers: Mapping[str, str]):
        super().__init__(f"Provider returned HTTP {status_code}")
        self.status_code = status_code
        self.headers = dict(headers)


@dataclass(frozen=True)
class JsonHttpResponse:
    payload: Optional[Dict[str, Any]]
    status_code: int
    headers: Dict[str, str]


class SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Allows only same-origin HTTPS redirects."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        target = urllib.parse.urljoin(req.full_url, newurl)
        source_parts = urllib.parse.urlparse(req.full_url)
        target_parts = urllib.parse.urlparse(target)
        if target_parts.scheme != "https":
            raise ProviderError("Provider attempted an insecure redirect")
        if target_parts.netloc != source_parts.netloc:
            raise ProviderError("Provider attempted a cross-origin redirect")
        return super().redirect_request(req, fp, code, msg, headers, target)


class JsonHttpClient:
    def __init__(self, timeout_seconds: int = 12, max_bytes: int = 5_000_000):
        self.timeout_seconds = timeout_seconds
        self.max_bytes = max_bytes
        self._opener = urllib.request.build_opener(SafeRedirectHandler())

    @staticmethod
    def build_url(url: str, params: Optional[Mapping[str, Any]] = None) -> str:
        parts = urllib.parse.urlsplit(url)
        query_items = urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
        query_items.extend((str(key), value) for key, value in (params or {}).items())
        return urllib.parse.urlunsplit(
            (
                parts.scheme,
                parts.netloc,
                parts.path,
                urllib.parse.urlencode(query_items, doseq=True),
                "",
            )
        )

    @staticmethod
    def _decode_content(payload: bytes, content_encoding: str, limit: int) -> bytes:
        encoding = content_encoding.strip().lower()
        if encoding in {"", "identity"}:
            return payload
        if encoding not in {"gzip", "deflate"}:
            raise ProviderError("Provider returned an unsupported content encoding")

        def decompress(window_bits: int) -> bytes:
            decoder = zlib.decompressobj(window_bits)
            decoded = decoder.decompress(payload, limit + 1)
            if len(decoded) > limit or decoder.unconsumed_tail:
                raise ProviderError("Provider response exceeded the size limit")
            decoded += decoder.flush(limit + 1 - len(decoded))
            if len(decoded) > limit:
                raise ProviderError("Provider response exceeded the size limit")
            if not decoder.eof:
                raise ProviderError("Provider returned invalid compressed data")
            return decoded

        try:
            return decompress(16 + zlib.MAX_WBITS if encoding == "gzip" else zlib.MAX_WBITS)
        except zlib.error as error:
            if encoding == "deflate":
                try:
                    return decompress(-zlib.MAX_WBITS)
                except zlib.error:
                    pass
            raise ProviderError("Provider returned invalid compressed data") from error

    def get_json_response(
        self,
        url: str,
        params: Optional[Mapping[str, Any]] = None,
        headers: Optional[Mapping[str, str]] = None,
    ) -> JsonHttpResponse:
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme != "https":
            raise ProviderError("Only HTTPS provider endpoints are allowed")

        request_url = self.build_url(url, params)
        request_headers = {
            "Accept": "application/json, application/geo+json",
            "Accept-Encoding": "gzip, deflate",
            "User-Agent": USER_AGENT,
        }
        request_headers.update(headers or {})
        request = urllib.request.Request(request_url, headers=request_headers, method="GET")
        try:
            with self._opener.open(request, timeout=self.timeout_seconds) as response:
                response_headers = {str(key): str(value) for key, value in response.headers.items()}
                try:
                    content_length = int(response.headers.get("Content-Length", "0") or 0)
                except ValueError:
                    content_length = 0
                if content_length > self.max_bytes:
                    raise ProviderError("Provider response is too large")
                wire_payload = response.read(self.max_bytes + 1)
                if len(wire_payload) > self.max_bytes:
                    raise ProviderError("Provider response exceeded the size limit")
                payload = self._decode_content(
                    wire_payload,
                    response.headers.get("Content-Encoding", ""),
                    self.max_bytes,
                )
                decoded = json.loads(payload.decode("utf-8"))
                if not isinstance(decoded, dict):
                    raise ProviderError("Provider JSON root must be an object")
                status_code = int(getattr(response, "status", 200))
                if status_code == 203:
                    logger.warning(
                        "Provider returned HTTP 203; the requested API product may be deprecated"
                    )
                return JsonHttpResponse(
                    payload=decoded,
                    status_code=status_code,
                    headers=response_headers,
                )
        except urllib.error.HTTPError as error:
            error_headers = {
                str(key): str(value)
                for key, value in (error.headers.items() if error.headers else [])
            }
            if error.code == 304:
                return JsonHttpResponse(None, 304, error_headers)
            raise HttpStatusError(error.code, error_headers) from error
        except urllib.error.URLError as error:
            raise ProviderError(f"Could not reach provider: {error.reason}") from error
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ProviderError("Provider returned invalid JSON") from error

    def get_json(
        self,
        url: str,
        params: Optional[Mapping[str, Any]] = None,
        headers: Optional[Mapping[str, str]] = None,
    ) -> Dict[str, Any]:
        response = self.get_json_response(url, params, headers)
        if response.payload is None:
            raise ProviderError("Provider returned no JSON body")
        return response.payload


class ConditionalJsonClient:
    """Persistent conditional HTTP cache for providers that require it."""

    FORMAT_VERSION = 1

    def __init__(self, client: JsonHttpClient, directory: Path):
        self.client = client
        self.directory = directory
        self._generation = 0
        self._write_lock = threading.Lock()

    @staticmethod
    def _timestamp(value: str, default: float) -> float:
        try:
            parsed = parsedate_to_datetime(value)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.timestamp()
        except (TypeError, ValueError, OverflowError):
            return default

    def _path(self, request_url: str) -> Path:
        digest = hashlib.sha256(request_url.encode("utf-8")).hexdigest()
        return self.directory / f"{digest}.json"

    @staticmethod
    def _unlink(path: Path) -> None:
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        except OSError:
            pass

    def clear(
        self,
        url: Optional[str] = None,
        params: Optional[Mapping[str, Any]] = None,
    ) -> None:
        """Clears one request entry, or every entry owned by this client."""

        with self._write_lock:
            self._generation += 1
        if url is not None:
            self._unlink(self._path(self.client.build_url(url, params)))
            return
        if self.directory.exists():
            for path in self.directory.glob("*.json"):
                self._unlink(path)

    def _write_if_current(
        self,
        path: Path,
        entry: Dict[str, Any],
        generation: int,
    ) -> None:
        with self._write_lock:
            if generation != self._generation:
                return
            atomic_write_text(path, json.dumps(entry, ensure_ascii=False))

    @staticmethod
    def _load(path: Path) -> Optional[Dict[str, Any]]:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(value, dict):
                return None
            if value.get("format") != ConditionalJsonClient.FORMAT_VERSION:
                return None
            if not isinstance(value.get("payload"), dict):
                return None
            for field in ("expires_at", "retry_after"):
                number = float(value.get(field, 0.0))
                if not math.isfinite(number) or number < 0.0:
                    return None
                value[field] = number
            if not isinstance(value.get("last_modified", ""), str):
                return None
            return value
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return None

    @staticmethod
    def _header(headers: Mapping[str, str], name: str) -> str:
        target = name.lower()
        return next((value for key, value in headers.items() if key.lower() == target), "")

    def get_json(
        self,
        url: str,
        params: Optional[Mapping[str, Any]] = None,
    ) -> Dict[str, Any]:
        request_url = self.client.build_url(url, params)
        path = self._path(request_url)
        cached = self._load(path)
        with self._write_lock:
            generation = self._generation
        now = time.time()
        if cached and now < float(cached.get("expires_at", 0.0)):
            return dict(cached["payload"])
        if cached and now < float(cached.get("retry_after", 0.0)):
            raise ProviderError("Provider rate limit is cooling down")

        request_headers: Dict[str, str] = {}
        if cached and cached.get("last_modified"):
            request_headers["If-Modified-Since"] = str(cached["last_modified"])

        try:
            response = self.client.get_json_response(url, params, request_headers)
        except HttpStatusError as error:
            if error.status_code == 429 and cached:
                retry_value = self._header(error.headers, "Retry-After")
                try:
                    retry_after = now + max(60, int(retry_value))
                except (TypeError, ValueError):
                    retry_after = self._timestamp(retry_value, now + 900)
                cached["retry_after"] = retry_after
                self._write_if_current(path, cached, generation)
            raise

        expires_at = self._timestamp(
            self._header(response.headers, "Expires"),
            now + 600,
        )
        if response.status_code == 304:
            if not cached:
                raise ProviderError("Provider returned 304 without a cached response")
            cached["expires_at"] = max(now, expires_at)
            cached["retry_after"] = 0.0
            self._write_if_current(path, cached, generation)
            return dict(cached["payload"])

        if response.payload is None:
            raise ProviderError("Provider returned no JSON body")
        entry = {
            "format": self.FORMAT_VERSION,
            "stored_at": datetime.now(timezone.utc).isoformat(),
            "expires_at": max(now, expires_at),
            "retry_after": 0.0,
            "last_modified": self._header(response.headers, "Last-Modified"),
            "payload": response.payload,
        }
        self._write_if_current(path, entry, generation)
        return dict(response.payload)


http_client = JsonHttpClient()
