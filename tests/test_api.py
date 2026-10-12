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

    def request(self, method, path, body=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        try:
            headers = {"Content-Type": "application/json"} if body is not None else {}
            conn.request(method, path, json.dumps(body) if body is not None else None, headers)
            response = conn.getresponse()
            return response.status, json.loads(response.read())
        finally:
            conn.close()

    def test_health_and_snapshot_contract(self):
        status, health = self.request("GET", "/api/health")
        self.assertEqual(status, 200)
        self.assertEqual(health, {"status": "ok", "source": "simulation"})
        status, snapshot = self.request("GET", "/api/snapshot")
        self.assertEqual(status, 200)
        self.assertEqual(snapshot["tick"], 1)
        self.assertEqual(snapshot["state"], "RUNNING")
        self.assertEqual(snapshot["in_process"], 1)

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


if __name__ == "__main__":
    unittest.main()
