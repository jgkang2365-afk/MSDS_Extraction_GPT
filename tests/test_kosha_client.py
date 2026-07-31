import tempfile
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

try:
    import requests
except ModuleNotFoundError:
    requests = types.ModuleType("requests")

    class RequestException(Exception):
        pass

    class HTTPError(RequestException):
        def __init__(self, message="", response=None):
            super().__init__(message)
            self.response = response

    class Timeout(RequestException):
        pass

    class ConnectionError(RequestException):
        pass

    requests.RequestException = RequestException
    requests.HTTPError = HTTPError
    requests.Timeout = Timeout
    requests.ConnectionError = ConnectionError
    requests.Session = lambda: None
    sys.modules["requests"] = requests

if "dotenv" not in sys.modules:
    dotenv_stub = types.ModuleType("dotenv")
    dotenv_stub.load_dotenv = lambda **_kwargs: None
    sys.modules["dotenv"] = dotenv_stub

import kosha_client


CHEM_LIST_XML = b"""
<response>
  <header><resultCode>00</resultCode></header>
  <body><items><item>
    <chemId>C001</chemId>
    <chemNameKor>\xec\x97\x90\xed\x83\x84\xec\x98\xac</chemNameKor>
  </item></items></body>
</response>
"""

DETAIL_15_XML = b"""
<response>
  <header><resultCode>00</resultCode></header>
  <body><items>
    <item>
      <msdsItemNameKor>\xec\x82\xb0\xec\x97\x85\xec\x95\x88\xec\xa0\x84\xeb\xb3\xb4\xea\xb1\xb4\xeb\xb2\x95\xec\x97\x90 \xec\x9d\x98\xed\x95\x9c \xea\xb7\x9c\xec\xa0\x9c</msdsItemNameKor>
      <itemDetail>\xec\x9e\x91\xec\x97\x85\xed\x99\x98\xea\xb2\xbd\xec\xb8\xa1\xec\xa0\x95\xeb\x8c\x80\xec\x83\x81\xeb\xac\xbc\xec\xa7\x88, \xed\x8a\xb9\xec\x88\x98\xea\xb1\xb4\xea\xb0\x95\xec\xa7\x84\xeb\x8b\xa8\xeb\x8c\x80\xec\x83\x81\xeb\xac\xbc\xec\xa7\x88</itemDetail>
    </item>
    <item>
      <msdsItemNameKor>\xed\x99\x94\xed\x95\x99\xeb\xac\xbc\xec\xa7\x88\xea\xb4\x80\xeb\xa6\xac\xeb\xb2\x95\xec\x97\x90 \xec\x9d\x98\xed\x95\x9c \xea\xb7\x9c\xec\xa0\x9c</msdsItemNameKor>
      <itemDetail>\xec\x9c\xa0\xeb\x8f\x85\xeb\xac\xbc\xec\xa7\x88</itemDetail>
    </item>
  </items></body>
</response>
"""


class FakeResponse:
    def __init__(self, content=b"", status_code=200, headers=None):
        self.content = content
        self.status_code = status_code
        self.headers = headers or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}", response=self)


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, params=None, timeout=None):
        self.calls.append((url, params, timeout))
        if not self.responses:
            raise AssertionError(f"예상하지 않은 추가 API 호출: {url}")
        return self.responses.pop(0)


class KoshaClientTrafficTests(unittest.TestCase):
    def _client(self, cache_path, session, **kwargs):
        return kosha_client.KoshaAPIClient(
            cache_path=str(cache_path),
            session=session,
            request_interval=0,
            cache_ttl=86400,
            negative_cache_ttl=3600,
            daily_request_budget=0,
            **kwargs,
        )

    def test_summary_uses_two_calls_and_reuses_persistent_cache(self):
        with tempfile.TemporaryDirectory() as temp_dir, patch.object(
            kosha_client, "BASE_URL", "https://example.invalid/msdschem"
        ):
            cache_path = Path(temp_dir) / "kosha-cache.json"
            first_session = FakeSession(
                [FakeResponse(CHEM_LIST_XML), FakeResponse(DETAIL_15_XML)]
            )
            first_client = self._client(cache_path, first_session)

            first = first_client.get_full_substance_info("64-17-5", full=False)
            second = first_client.get_full_substance_info("64-17-5", full=False)

            self.assertEqual(first["product_name"], "에탄올")
            self.assertTrue(first["osh"]["is_measured"])
            self.assertTrue(first["osh"]["is_special"])
            self.assertEqual(second, first)
            self.assertEqual(len(first_session.calls), 2)
            self.assertTrue(first_session.calls[0][0].endswith("/chemlist"))
            self.assertTrue(first_session.calls[1][0].endswith("/chemdetail15"))
            self.assertFalse(
                any(url.endswith("/chemdetail01") for url, _params, _timeout in first_session.calls)
            )

            warm_session = FakeSession([])
            warm_client = self._client(cache_path, warm_session)
            warm = warm_client.get_full_substance_info("64-17-5", full=False)

            self.assertEqual(warm, first)
            self.assertEqual(warm_session.calls, [])
            self.assertEqual(warm_client.get_metrics()["persistent_cache_hits"], 1)

    def test_non_retryable_http_error_is_not_repeated(self):
        with tempfile.TemporaryDirectory() as temp_dir, patch.object(
            kosha_client, "BASE_URL", "https://example.invalid/msdschem"
        ):
            session = FakeSession([FakeResponse(status_code=401)])
            client = self._client(Path(temp_dir) / "cache.json", session)

            self.assertEqual(client.get_chem_id("64-17-5"), (None, None))
            self.assertEqual(len(session.calls), 1)
            self.assertEqual(client.get_metrics()["retries"], 0)

    def test_transient_503_retries_then_succeeds(self):
        with tempfile.TemporaryDirectory() as temp_dir, patch.object(
            kosha_client, "BASE_URL", "https://example.invalid/msdschem"
        ), patch.object(kosha_client.time, "sleep", return_value=None):
            session = FakeSession(
                [FakeResponse(status_code=503), FakeResponse(CHEM_LIST_XML)]
            )
            client = self._client(Path(temp_dir) / "cache.json", session)

            chem_id, chem_name = client.get_chem_id("64-17-5")

            self.assertEqual((chem_id, chem_name), ("C001", "에탄올"))
            self.assertEqual(len(session.calls), 2)
            self.assertEqual(client.get_metrics()["retries"], 1)

    def test_daily_budget_stops_before_extra_network_request(self):
        with tempfile.TemporaryDirectory() as temp_dir, patch.object(
            kosha_client, "BASE_URL", "https://example.invalid/msdschem"
        ):
            cache_path = Path(temp_dir) / "cache.json"
            session = FakeSession([FakeResponse(CHEM_LIST_XML)])
            client = kosha_client.KoshaAPIClient(
                cache_path=str(cache_path),
                session=session,
                request_interval=0,
                daily_request_budget=1,
            )

            with self.assertRaises(kosha_client.KoshaRequestBudgetExceeded):
                client.get_full_substance_info("64-17-5", full=False)

            self.assertEqual(len(session.calls), 1)
            self.assertEqual(client.get_metrics()["daily_requests"], 1)


if __name__ == "__main__":
    unittest.main()
