# Copyright (C) 2026 Vicente José Leiva Escárate
# SPDX-License-Identifier: GPL-3.0-or-later

import json
import tempfile
import unittest
import urllib.request
import zlib
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from pathlib import Path

from app.providers.base import ProviderError
from app.providers.http import (
    ConditionalJsonClient,
    HttpStatusError,
    JsonHttpClient,
    JsonHttpResponse,
    SafeRedirectHandler,
)


class HttpSafetyTestCase(unittest.TestCase):
    def setUp(self):
        self.handler = SafeRedirectHandler()
        self.request = urllib.request.Request("https://example.org/weather")

    def test_rejects_https_downgrade(self):
        with self.assertRaises(ProviderError):
            self.handler.redirect_request(
                self.request,
                None,
                302,
                "Found",
                {},
                "http://example.org/weather",
            )

    def test_rejects_cross_origin_redirect(self):
        with self.assertRaises(ProviderError):
            self.handler.redirect_request(
                self.request,
                None,
                302,
                "Found",
                {},
                "https://other.example/weather",
            )

    def test_rejects_non_object_json_root(self):
        class Response:
            headers = {}

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self, _limit):
                return b"[]"

        class Opener:
            def open(self, _request, timeout):
                self.timeout = timeout
                return Response()

        client = JsonHttpClient()
        client._opener = Opener()
        with self.assertRaises(ProviderError):
            client.get_json("https://example.org/weather")

    def test_decodes_gzip_with_a_post_decompression_limit(self):
        payload = b'{"temperature":12}'
        compressor = zlib.compressobj(wbits=16 + zlib.MAX_WBITS)
        encoded = compressor.compress(payload) + compressor.flush()
        self.assertEqual(
            JsonHttpClient._decode_content(encoded, "gzip", 100),
            payload,
        )

        large_compressor = zlib.compressobj(wbits=16 + zlib.MAX_WBITS)
        large = large_compressor.compress(b"x" * 101) + large_compressor.flush()
        with self.assertRaises(ProviderError):
            JsonHttpClient._decode_content(large, "gzip", 100)

    def test_conditional_cache_honours_expires(self):
        class Client:
            calls = 0

            @staticmethod
            def build_url(url, _params=None):
                return url

            def get_json_response(self, _url, _params, _headers):
                self.calls += 1
                return JsonHttpResponse(
                    {"temperature": 12},
                    200,
                    {
                        "Expires": format_datetime(
                            datetime.now(timezone.utc) + timedelta(minutes=10),
                            usegmt=True,
                        ),
                        "Last-Modified": "Wed, 12 Aug 2026 12:00:00 GMT",
                    },
                )

        with tempfile.TemporaryDirectory() as directory:
            client = Client()
            cached = ConditionalJsonClient(client, Path(directory))
            self.assertEqual(cached.get_json("https://example.org/weather"), {"temperature": 12})
            self.assertEqual(cached.get_json("https://example.org/weather"), {"temperature": 12})
            self.assertEqual(client.calls, 1)

    def test_conditional_cache_revalidates_with_last_modified(self):
        class Client:
            calls = 0
            second_headers = {}

            @staticmethod
            def build_url(url, _params=None):
                return url

            def get_json_response(self, _url, _params, headers):
                self.calls += 1
                if self.calls == 1:
                    return JsonHttpResponse(
                        {"temperature": 12},
                        200,
                        {
                            "Expires": "Wed, 12 Aug 2020 12:00:00 GMT",
                            "Last-Modified": "Wed, 12 Aug 2026 12:00:00 GMT",
                        },
                    )
                self.second_headers = dict(headers)
                return JsonHttpResponse(
                    None,
                    304,
                    {
                        "Expires": format_datetime(
                            datetime.now(timezone.utc) + timedelta(minutes=10),
                            usegmt=True,
                        )
                    },
                )

        with tempfile.TemporaryDirectory() as directory:
            client = Client()
            cached = ConditionalJsonClient(client, Path(directory))
            cached.get_json("https://example.org/weather")
            result = cached.get_json("https://example.org/weather")
            self.assertEqual(result, {"temperature": 12})
            self.assertEqual(
                client.second_headers["If-Modified-Since"],
                "Wed, 12 Aug 2026 12:00:00 GMT",
            )

    def test_conditional_cache_respects_retry_after(self):
        class Client:
            calls = 0

            @staticmethod
            def build_url(url, _params=None):
                return url

            def get_json_response(self, _url, _params, _headers):
                self.calls += 1
                if self.calls == 1:
                    return JsonHttpResponse(
                        {"temperature": 12},
                        200,
                        {"Expires": "Wed, 12 Aug 2020 12:00:00 GMT"},
                    )
                raise HttpStatusError(429, {"Retry-After": "120"})

        with tempfile.TemporaryDirectory() as directory:
            client = Client()
            cached = ConditionalJsonClient(client, Path(directory))
            cached.get_json("https://example.org/weather")
            with self.assertRaises(HttpStatusError):
                cached.get_json("https://example.org/weather")
            with self.assertRaises(ProviderError):
                cached.get_json("https://example.org/weather")
            self.assertEqual(client.calls, 2)

    def test_conditional_cache_can_clear_one_entry_or_everything(self):
        class Client:
            @staticmethod
            def build_url(url, params=None):
                suffix = "" if not params else f"?place={params['place']}"
                return url + suffix

        with tempfile.TemporaryDirectory() as directory:
            cached = ConditionalJsonClient(Client(), Path(directory))
            first = cached._path(Client.build_url("https://example.org/weather", {"place": "a"}))
            second = cached._path(Client.build_url("https://example.org/weather", {"place": "b"}))
            first.write_text("{}", encoding="utf-8")
            second.write_text("{}", encoding="utf-8")
            cached.clear("https://example.org/weather", {"place": "a"})
            self.assertFalse(first.exists())
            self.assertTrue(second.exists())
            cached.clear()
            self.assertFalse(second.exists())

    def test_clear_during_request_prevents_late_http_cache_write(self):
        class Client:
            after_response = None

            @staticmethod
            def build_url(url, _params=None):
                return url

            def get_json_response(self, _url, _params, _headers):
                if self.after_response:
                    self.after_response()
                return JsonHttpResponse({"temperature": 12}, 200, {})

        with tempfile.TemporaryDirectory() as directory:
            client = Client()
            cached = ConditionalJsonClient(client, Path(directory))
            client.after_response = cached.clear
            self.assertEqual(
                cached.get_json("https://example.org/weather"),
                {"temperature": 12},
            )
            self.assertEqual(list(Path(directory).glob("*.json")), [])

    def test_malformed_conditional_metadata_is_ignored(self):
        class Client:
            calls = 0

            @staticmethod
            def build_url(url, _params=None):
                return url

            def get_json_response(self, _url, _params, _headers):
                self.calls += 1
                return JsonHttpResponse({"temperature": 14}, 200, {})

        with tempfile.TemporaryDirectory() as directory:
            client = Client()
            cached = ConditionalJsonClient(client, Path(directory))
            path = cached._path("https://example.org/weather")
            path.write_text(
                json.dumps(
                    {
                        "format": 1,
                        "expires_at": "not-a-number",
                        "retry_after": 0,
                        "payload": {"temperature": 12},
                    }
                ),
                encoding="utf-8",
            )
            self.assertEqual(
                cached.get_json("https://example.org/weather"),
                {"temperature": 14},
            )
            self.assertEqual(client.calls, 1)


if __name__ == "__main__":
    unittest.main()
