"""FT-011: bounded SSE reconnect/resync behavior."""
import http.client
import json
import threading
import time
import unittest
from http.server import ThreadingHTTPServer

from factorytwin.sim import ProductionLine
from factorytwin.streaming import SnapshotStreamHub
import factorytwin.__main__ as api


class StreamHubTest(unittest.TestCase):
    def test_fresh_connection_gets_detached_resync(self):
        hub = SnapshotStreamHub(capacity=3)
        current = {"tick": 7, "nested": {"value": 1}}
        frames = hub.reconnect(None, current)
        self.assertEqual((frames[0].id, frames[0].event), (0, "resync"))
        frames[0].data["nested"]["value"] = 99
        self.assertEqual(current["nested"]["value"], 1)

    def test_reconnect_replays_only_missed_frames(self):
        hub = SnapshotStreamHub(capacity=4)
        for tick in range(1, 4):
            hub.publish({"tick": tick})
        self.assertEqual([f.id for f in hub.reconnect(1, {"tick": 99})], [2, 3])
        self.assertEqual(hub.reconnect(3, {"tick": 99}), [])

    def test_too_old_or_future_cursor_gets_resync(self):
        hub = SnapshotStreamHub(capacity=2)
        for tick in range(1, 5):
            hub.publish({"tick": tick})
        old = hub.reconnect(1, {"tick": 4})
        future = hub.reconnect(99, {"tick": 4})
        self.assertEqual((old[0].event, old[0].data["tick"]), ("resync", 4))
        self.assertEqual((future[0].event, future[0].data["tick"]), ("resync", 4))

    def test_buffer_is_bounded(self):
        hub = SnapshotStreamHub(capacity=2)
        for tick in range(1, 11):
            hub.publish({"tick": tick})
        frames = hub.reconnect(8, {"tick": 10})
        self.assertEqual([f.data["tick"] for f in frames], [9, 10])

    def test_wait_after_unblocks_on_publish(self):
        hub = SnapshotStreamHub()
        result = []
        thread = threading.Thread(target=lambda: result.extend(hub.wait_after(0, timeout=1)))
        thread.start()
        time.sleep(0.02)
        hub.publish({"tick": 1})
        thread.join(timeout=2)
        self.assertFalse(thread.is_alive())
        self.assertEqual(result[0].data["tick"], 1)

    def test_invalid_ids_rejected(self):
        hub = SnapshotStreamHub()
        for value in (-1, True, "1"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                hub.reconnect(value, {})


class SSEApiTest(unittest.TestCase):
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
            api.STREAM = SnapshotStreamHub(capacity=3)

    def request_json(self, method, path, body=None, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=3)
        try:
            payload = json.dumps(body) if body is not None else None
            final_headers = {"Content-Type": "application/json"} if body is not None else {}
            final_headers.update(headers or {})
            conn.request(method, path, payload, final_headers)
            response = conn.getresponse()
            return response.status, json.loads(response.read())
        finally:
            conn.close()

    def first_sse_event(self, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=3)
        conn.request("GET", "/api/stream", headers=headers or {})
        response = conn.getresponse()
        self.assertEqual(response.status, 200)
        lines = []
        while True:
            line = response.fp.readline().decode("utf-8").rstrip("\r\n")
            if not line:
                break
            lines.append(line)
        conn.close()
        parsed = {line.split(": ", 1)[0]: line.split(": ", 1)[1]
                  for line in lines if ": " in line}
        return parsed

    def test_initial_stream_resync_does_not_advance_tick(self):
        event = self.first_sse_event()
        self.assertEqual(event["event"], "resync")
        self.assertEqual(json.loads(event["data"])["tick"], 0)
        self.assertEqual(api.SIM.tick, 0)

    def test_snapshot_publish_can_be_replayed_by_last_event_id(self):
        status, snapshot = self.request_json("GET", "/api/snapshot")
        self.assertEqual(status, 200)
        self.assertEqual(snapshot["tick"], 1)
        event = self.first_sse_event({"Last-Event-ID": "0"})
        self.assertEqual(event["event"], "snapshot")
        self.assertEqual(json.loads(event["data"])["tick"], 1)
        self.assertEqual(api.SIM.tick, 1)

    def test_invalid_last_event_id_is_400(self):
        status, body = self.request_json("GET", "/api/stream",
                                         headers={"Last-Event-ID": "not-an-int"})
        self.assertEqual(status, 400)
        self.assertEqual(body, {"error": "invalid Last-Event-ID"})

    def test_control_publishes_without_advancing_tick(self):
        status, state = self.request_json("POST", "/api/control", {"action": "pause"})
        self.assertEqual(status, 200)
        self.assertEqual(state["tick"], 0)
        event = api.STREAM.reconnect(0, api.SIM.snapshot())[0]
        self.assertEqual(event.event, "snapshot")
        self.assertEqual(event.data["state"], "PAUSED")


if __name__ == "__main__":
    unittest.main()
