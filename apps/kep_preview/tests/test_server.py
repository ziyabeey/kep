"""Exercise the real HTTP boundary without any external network or providers."""
import http.client
import json
import threading
import unittest
from unittest.mock import patch

from apps.kep_preview.server import Handler, make_server


class HTTPBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.logs = patch.object(Handler, "log_message", lambda *_: None)
        cls.logs.start()
        cls.server = make_server(port=0)
        cls.port = cls.server.server_port
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)
        cls.logs.stop()

    def request(self, method, path, payload=None, headers=None, raw=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        request_headers = dict(headers or {})
        if payload is not None:
            raw = json.dumps(payload).encode()
            request_headers.setdefault("Content-Type", "application/json")
        connection.request(method, path, body=raw, headers=request_headers)
        response = connection.getresponse()
        body = response.read()
        result = response.status, dict(response.getheaders()), body
        connection.close()
        return result

    def test_ui_to_real_core_keeps_unknown_price_and_hours(self):
        status, _, raw = self.request("GET", "/api/bootstrap")
        bootstrap = json.loads(raw)
        self.assertEqual(status, 200)
        self.assertTrue(bootstrap["initial"]["decision"]["selected"])
        status, _, raw = self.request("POST", "/api/discover", {
            "category": "discover", "open_now": True, "budget": 500,
        })
        response = json.loads(raw)
        self.assertEqual(status, 200)
        self.assertEqual(response["decision"]["action"], "REFRESH")
        self.assertEqual(response["decision"]["selected"], [])
        self.assertFalse(response["meta"]["model_used"])

    def test_host_and_cross_origin_requests_are_rejected(self):
        status, _, _ = self.request("GET", "/api/bootstrap", headers={"Host": "evil.invalid"})
        self.assertEqual(status, 403)
        status, _, _ = self.request("POST", "/api/discover", {},
                                    headers={"Origin": "https://evil.invalid"})
        self.assertEqual(status, 403)
        status, _, _ = self.request("POST", "/api/discover", {},
                                    headers={"Origin": f"http://127.0.0.1:{self.port}"})
        self.assertEqual(status, 200)

    def test_static_allowlist_never_serves_repository_files(self):
        for path in ("/../README.md", "/%2e%2e/README.md", "/labs/core/data/raw/istanbul_places_excerpt.json"):
            with self.subTest(path=path):
                self.assertEqual(self.request("GET", path)[0], 404)

    def test_only_bounded_json_objects_are_accepted(self):
        for raw in (b"[]", b'{"budget":NaN}', b'{"budget":Infinity}', b"{bad"):
            with self.subTest(raw=raw):
                self.assertEqual(self.request("POST", "/api/discover", raw=raw,
                                              headers={"Content-Type": "application/json"})[0], 400)
        self.assertEqual(self.request("POST", "/api/discover", raw=b"{}",
                                      headers={"Content-Type": "text/plain"})[0], 415)
        self.assertEqual(self.request("POST", "/api/chat", {"message": "x" * 17000})[0], 413)

    def test_client_cannot_override_source_rights(self):
        self.assertEqual(self.request("POST", "/api/discover", {
            "rights_scope": "approved", "consumer_publish": True,
        })[0], 400)

    def test_malformed_unicode_and_extreme_json_still_return_http(self):
        for path, payload, expected in (
            ("/api/chat", {"message": "\ud800"}, 200),
            ("/api/discover", {"\ud800": 0}, 400),
        ):
            with self.subTest(path=path):
                status, _, body = self.request("POST", path, payload)
                self.assertEqual(status, expected)
                self.assertIsInstance(json.loads(body), dict)
        self.assertEqual(self.request("POST", "/api/discover", raw=b"{}", headers={
            "Content-Type": "application/json", "Content-Length": "9" * 5000,
        })[0], 413)
        self.assertEqual(self.request("POST", "/api/discover",
            raw=b'{"budget":' + b"[" * 1200 + b"0" + b"]" * 1200 + b"}",
            headers={"Content-Type": "application/json"})[0], 400)

    def test_static_page_has_local_script_and_boundary_headers(self):
        status, headers, body = self.request("GET", "/")
        self.assertEqual(status, 200)
        self.assertIn(b"app.js", body)
        self.assertIn("script-src 'self'", headers["Content-Security-Policy"])
        self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(headers["Referrer-Policy"], "strict-origin-when-cross-origin")

    def test_incomplete_plan_never_emits_departure_advice(self):
        status, _, body = self.request("POST", "/api/plan", {
            "date": "2026-10-20",
            "stops": [
                {"id": "a", "label": "Maslak", "arrival": "16:00", "duration_minutes": None},
                {"id": "b", "label": "Levent", "arrival": "17:00", "duration_minutes": 0},
            ],
            "travel_minutes": [None], "arrival_buffer_minutes": 15,
        })
        data = json.loads(body)
        self.assertEqual(status, 200)
        self.assertEqual(data["status"], "needs_input")
        self.assertFalse(data["traffic_live"])
        self.assertIsNone(data["legs"][0]["latest_departure"])


if __name__ == "__main__":
    unittest.main()
