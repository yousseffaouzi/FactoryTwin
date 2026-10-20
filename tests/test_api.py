"""Loopback HTTP regression checks for the existing demo API."""
import http.client
import json
import threading
import unittest
from http.server import ThreadingHTTPServer

import factorytwin.__main__ as api
from factorytwin.sim import ProductionLine


class ApiCompatibilityTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), api.Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)

    def setUp(self):
        with api.LOCK:
            api.SIM = ProductionLine()

    def request_details(self, method, path, body=None, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        try:
            request_headers = {"Content-Type": "application/json"} if body is not None else {}
            if headers:
                request_headers.update(headers)
            conn.request(method, path, json.dumps(body) if body is not None else None, request_headers)
            response = conn.getresponse()
            raw = response.read()
            payload = json.loads(raw) if raw else None
            response_headers = {name.lower(): value for name, value in response.getheaders()}
            return response.status, payload, response_headers
        finally:
            conn.close()

    def request(self, method, path, body=None, headers=None):
        status, payload, _ = self.request_details(method, path, body, headers)
        return status, payload

    def raw_request(self, method, path, headers=(), body=b""):
        conn = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        try:
            conn.putrequest(method, path)
            for name, value in headers:
                conn.putheader(name, value)
            conn.endheaders()
            if body:
                conn.send(body)
            response = conn.getresponse()
            raw = response.read()
            payload = json.loads(raw) if raw else None
            response_headers = {name.lower(): value for name, value in response.getheaders()}
            return response.status, payload, response_headers
        finally:
            conn.close()

    def assert_simulation_unchanged(self):
        self.assertEqual(api.SIM.tick, 0)
        self.assertEqual(api.SIM.events, [])
        self.assertEqual(api.SIM.state.value, "RUNNING")

    def test_health_and_snapshot_contract(self):
        status, health = self.request("GET", "/api/health")
        self.assertEqual(status, 200)
        self.assertEqual(health, {"status": "ok", "source": "simulation"})
        status, snapshot = self.request("GET", "/api/snapshot")
        self.assertEqual(status, 200)
        self.assertEqual(snapshot["tick"], 1)
        self.assertEqual(snapshot["state"], "RUNNING")
        self.assertEqual(snapshot["in_process"], 1)
        self.assertEqual(snapshot["sim_time_ms"], 1000)
        self.assertEqual(snapshot["events"][0]["seq"], 1)
        self.assertEqual(snapshot["events"][0]["sim_time_ms"], 1000)

    def test_control_transitions_keep_response_shape(self):
        for action, station, expected_state in (
            ("pause", None, "PAUSED"),
            ("fault", "Processing", "PAUSED"),
            ("resume", None, "FAULT"),
            ("clear_fault", None, "RUNNING"),
            ("reset", None, "RUNNING"),
        ):
            with self.subTest(action=action):
                status, snapshot = self.request("POST", "/api/control", {"action": action, "station": station})
                self.assertEqual(status, 200)
                self.assertEqual(snapshot["state"], expected_state)
                self.assertIn("stations", snapshot)
                self.assertIn("events", snapshot)
        self.assertEqual(snapshot["tick"], 0)

    def test_rejected_fault_does_not_change_state(self):
        self.request("POST", "/api/control", {"action": "fault", "station": "Feeder"})
        status, err = self.request("POST", "/api/control", {"action": "fault", "station": "Packing"})
        self.assertEqual(status, 400)
        self.assertIn("fault already active", err["error"])
        self.assertEqual(api.SIM.fault_station, "Feeder")
        self.assertEqual(len(api.SIM.events), 1)

    def test_control_requires_json_media_type_without_mutation(self):
        conn = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        try:
            body = json.dumps({"action": "pause"})
            conn.request("POST", "/api/control", body, {"Content-Type": "text/plain"})
            response = conn.getresponse()
            self.assertEqual(response.status, 415)
            self.assertEqual(json.loads(response.read()), {"error": "application/json required"})
        finally:
            conn.close()
        self.assert_simulation_unchanged()

        status, snapshot = self.request(
            "POST", "/api/control", {"action": "pause"},
            {"Content-Type": "application/json; charset=utf-8"})
        self.assertEqual(status, 200)
        self.assertEqual(snapshot["state"], "PAUSED")

    def test_control_rejects_transfer_encoding_without_mutation(self):
        status, err, _ = self.raw_request(
            "POST", "/api/control",
            (("Content-Type", "application/json"), ("Transfer-Encoding", "chunked")))
        self.assertEqual(status, 400)
        self.assertEqual(err, {"error": "transfer encoding not supported"})
        self.assert_simulation_unchanged()

    def test_control_requires_single_valid_content_length_without_mutation(self):
        status, err, _ = self.raw_request(
            "POST", "/api/control", (("Content-Type", "application/json"),))
        self.assertEqual(status, 411)
        self.assertEqual(err, {"error": "Content-Length required"})
        self.assert_simulation_unchanged()

        status, err, _ = self.raw_request(
            "POST", "/api/control",
            (("Content-Type", "application/json"), ("Content-Length", "not-a-number")))
        self.assertEqual(status, 400)
        self.assertEqual(err, {"error": "invalid request size"})
        self.assert_simulation_unchanged()

        status, err, _ = self.raw_request(
            "POST", "/api/control",
            (("Content-Type", "application/json"),
             ("Content-Length", "2"), ("Content-Length", "2")))
        self.assertEqual(status, 400)
        self.assertEqual(err, {"error": "invalid request size"})
        self.assert_simulation_unchanged()

    def test_control_invalid_json_is_stable_and_atomic(self):
        status, err, _ = self.raw_request(
            "POST", "/api/control",
            (("Content-Type", "application/json"), ("Content-Length", "1")), b"{")
        self.assertEqual(status, 400)
        self.assertEqual(err, {"error": "invalid JSON"})
        self.assert_simulation_unchanged()

    def test_security_headers_are_present_on_api_and_static_responses(self):
        status, _, headers = self.request_details("GET", "/api/health")
        self.assertEqual(status, 200)
        expected = {
            "x-content-type-options": "nosniff",
            "referrer-policy": "no-referrer",
            "x-frame-options": "DENY",
            "cross-origin-resource-policy": "same-origin",
            "content-security-policy": "base-uri 'none'; frame-ancestors 'none'; object-src 'none'",
        }
        for name, value in expected.items():
            with self.subTest(header=name):
                self.assertEqual(headers.get(name), value)

        conn = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        try:
            conn.request("GET", "/")
            response = conn.getresponse()
            self.assertEqual(response.status, 200)
            static_headers = {name.lower(): value for name, value in response.getheaders()}
            response.read()
        finally:
            conn.close()
        for name, value in expected.items():
            with self.subTest(static_header=name):
                self.assertEqual(static_headers.get(name), value)


if __name__ == "__main__":
    unittest.main()
