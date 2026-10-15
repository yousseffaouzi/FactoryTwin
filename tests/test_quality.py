"""FT-008: deterministic genealogy, scrap and same-station rework semantics."""
from copy import deepcopy
import http.client
import json
from pathlib import Path
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer

from factorytwin.blueprint import FactoryBlueprint
from factorytwin.quality import QualityScenario
from factorytwin.sim import ProductionLine, QUALITY_TRACE_SCHEMA, TRACE_SCHEMA
import factorytwin.__main__ as api


def plan(names=("Feed", "Inspect", "Pack"), cycles=(1, 2, 1)):
    return {"version": 1,
            "stations": [{"id": name, "cycle_ticks": cycle}
                         for name, cycle in zip(names, cycles)],
            "connections": [{"from": a, "to": b} for a, b in zip(names, names[1:])]}


def quality(*decisions):
    return {"version": 1, "decisions": list(decisions)}


def decision(piece, station, attempt, outcome):
    return {"workpiece_id": piece, "station": station, "attempt": attempt, "outcome": outcome}


class GenealogyAndQualityTest(unittest.TestCase):
    def test_default_run_keeps_legacy_trace_schema_and_behavior(self):
        line = ProductionLine()
        for _ in range(7):
            line.step()
        self.assertEqual(line.completed, 3)
        self.assertEqual(line.scrapped, 0)
        self.assertEqual(line.rework_cycles, 0)
        self.assertEqual(line.export_trace()["schema"], TRACE_SCHEMA)
        self.assertEqual(line.state_data().keys(),
                         {"tick", "sim_time_ms", "state", "running", "fault_station",
                          "completed", "scrapped", "next_id", "conveyor",
                          "event_sequence", "events"})
        line.audit_genealogy()

    def test_genealogy_tracks_station_entry_processing_and_exit(self):
        line = ProductionLine.from_blueprint(plan())
        for _ in range(5):
            line.step()
        record = line.workpiece_genealogy("WP-0001")
        self.assertEqual(record["status"], "COMPLETED")
        self.assertEqual([v["station"] for v in record["visits"]], ["Feed", "Inspect", "Pack"])
        self.assertEqual(
            [(v["entered_tick"], v["processing_completed_tick"], v["exited_tick"])
             for v in record["visits"]],
            [(1, 2, 2), (2, 4, 4), (4, 5, 5)])
        self.assertTrue(all(v["outcome"] == "GOOD" for v in record["visits"]))
        self.assertTrue(all(v["outcome_source"] == "default" for v in record["visits"]))
        line.audit_genealogy()

    def test_scrap_is_terminal_and_conserved(self):
        line = ProductionLine.from_blueprint(
            plan(), quality(decision("WP-0002", "Inspect", 1, "SCRAP")))
        for _ in range(10):
            line.step()
            line.validate()
            self.assertEqual(line.next_id - 1,
                             line.completed + line.scrapped + line.snapshot()["in_process"])
        record = line.workpiece_genealogy("WP-0002")
        self.assertEqual(record["status"], "SCRAPPED")
        self.assertEqual(record["visits"][-1]["station"], "Inspect")
        self.assertEqual(record["visits"][-1]["outcome"], "SCRAP")
        self.assertEqual(record["visits"][-1]["outcome_source"], "scenario")
        self.assertEqual(line.scrapped, 1)
        self.assertNotIn("Pack", [v["station"] for v in record["visits"]])
        line.audit_genealogy()

    def test_rework_repeats_same_station_without_graph_loop(self):
        line = ProductionLine.from_blueprint(
            plan(), quality(decision("WP-0001", "Inspect", 1, "REWORK")))
        for _ in range(9):
            line.step()
        record = line.workpiece_genealogy("WP-0001")
        self.assertEqual(record["status"], "COMPLETED")
        self.assertEqual([(v["station"], v["attempt"]) for v in record["visits"]],
                         [("Feed", 1), ("Inspect", 1), ("Inspect", 2), ("Pack", 1)])
        self.assertEqual(record["visits"][1]["outcome"], "REWORK")
        self.assertEqual(record["visits"][2]["outcome"], "GOOD")
        self.assertEqual(record["rework_count"], 1)
        self.assertEqual(line.rework_cycles, 1)
        self.assertEqual(line.blueprint.station_ids, ("Feed", "Inspect", "Pack"))
        line.audit_genealogy()

    def test_rework_preserves_backpressure_and_unique_identity(self):
        line = ProductionLine.from_blueprint(
            plan(("A", "B"), (1, 1)),
            quality(decision("WP-0001", "B", 1, "REWORK"),
                    decision("WP-0001", "B", 2, "REWORK")))
        for _ in range(5):
            line.step()
        record = line.workpiece_genealogy("WP-0001")
        self.assertEqual([v["attempt"] for v in record["visits"] if v["station"] == "B"], [1, 2, 3])
        self.assertEqual(record["rework_count"], 2)
        self.assertEqual(len({piece["id"] for piece in line.conveyor if piece}),
                         line.snapshot()["in_process"])
        self.assertEqual(line.next_id - 1,
                         line.completed + line.scrapped + line.snapshot()["in_process"])
        line.audit_genealogy()

    def test_pause_and_fault_freeze_quality_processing_but_not_observation_tick(self):
        line = ProductionLine.from_blueprint(
            plan(("A",), (2,)), quality(decision("WP-0001", "A", 1, "SCRAP")))
        line.step()
        remaining = list(line.remaining_ticks)
        history = deepcopy(line.workpiece_genealogy("WP-0001"))
        line.control("pause")
        line.step()
        line.step()
        self.assertEqual(line.remaining_ticks, remaining)
        self.assertEqual(line.workpiece_genealogy("WP-0001"), history)
        line.control("fault", "A")
        line.control("resume")
        line.step()
        self.assertEqual(line.remaining_ticks, remaining)
        self.assertEqual(line.scrapped, 0)
        line.control("clear_fault")
        line.step()
        line.step()
        self.assertEqual(line.scrapped, 1)
        self.assertEqual(line.tick, 6)
        line.audit_genealogy()

    def test_quality_scenario_is_strict_and_station_bound(self):
        bad = [
            None,
            {},
            {"version": True, "decisions": []},
            quality({"workpiece_id": "bad", "station": "A", "attempt": 1, "outcome": "SCRAP"}),
            quality(decision("WP-0001", "A", True, "SCRAP")),
            quality(decision("WP-0001", "A", 1, "MAYBE")),
            quality(decision("WP-0001", "A", 1, "SCRAP"), decision("WP-0001", "A", 1, "GOOD")),
        ]
        for item in bad:
            with self.subTest(item=item):
                with self.assertRaises(ValueError):
                    QualityScenario.from_dict(item)
        scenario = QualityScenario.from_dict(quality(decision("WP-0001", "Missing", 1, "SCRAP")))
        with self.assertRaisesRegex(ValueError, "unknown station"):
            ProductionLine(blueprint=FactoryBlueprint.from_dict(plan(("A",), (1,))),
                           quality_scenario=scenario)

    def test_quality_scenario_load_is_local_json_and_canonical(self):
        raw = quality(decision("WP-0003", "Inspect", 1, "SCRAP"),
                      decision("WP-0002", "Inspect", 1, "REWORK"))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "quality.json"
            path.write_text(json.dumps(raw), encoding="utf-8")
            scenario = QualityScenario.load(path)
        self.assertEqual([d["workpiece_id"] for d in scenario.to_dict()["decisions"]],
                         ["WP-0002", "WP-0003"])

    def test_trace_v3_roundtrip_replays_genealogy_quality_and_continuation(self):
        q = quality(decision("WP-0001", "Inspect", 1, "REWORK"),
                    decision("WP-0003", "Inspect", 1, "SCRAP"))
        line = ProductionLine.from_blueprint(plan(), q)
        for _ in range(14):
            line.step()
        line.control("pause")
        line.step()
        line.control("resume")
        line.step()
        trace = json.loads(json.dumps(line.export_trace()))
        self.assertEqual(trace["schema"], QUALITY_TRACE_SCHEMA)
        self.assertIn("genealogy", trace["final_state"])
        restored = ProductionLine.replay(trace)
        self.assertEqual(restored.export_trace(), trace)
        for obj in (line, restored):
            for _ in range(5):
                obj.step()
        self.assertEqual(restored.export_trace(), line.export_trace())

    def test_tampered_quality_trace_is_rejected(self):
        line = ProductionLine.from_blueprint(
            plan(), quality(decision("WP-0001", "Inspect", 1, "SCRAP")))
        for _ in range(6):
            line.step()
        original = line.export_trace()
        changed = deepcopy(original)
        changed["quality_scenario"]["decisions"][0]["outcome"] = "REWORK"
        with self.assertRaises(ValueError):
            ProductionLine.replay(changed)
        changed = deepcopy(original)
        changed["final_state"]["genealogy"][0]["visits"][0]["station"] = "Pack"
        with self.assertRaisesRegex(ValueError, "final state mismatch"):
            ProductionLine.replay(changed)

    def test_reset_preserves_configuration_but_clears_session_genealogy(self):
        scenario = quality(decision("WP-0001", "Inspect", 1, "REWORK"))
        line = ProductionLine.from_blueprint(plan(), scenario)
        for _ in range(7):
            line.step()
        self.assertGreater(line.rework_cycles, 0)
        line.control("reset")
        self.assertEqual(line.next_id, 1)
        self.assertEqual(line.genealogy, {})
        self.assertEqual(line.rework_cycles, 0)
        self.assertTrue(line.quality_scenario.enabled)
        self.assertEqual(line.export_trace()["schema"], QUALITY_TRACE_SCHEMA)
        self.assertEqual(ProductionLine.replay(line.export_trace()).export_trace(), line.export_trace())

    def test_snapshot_quality_fields_are_additive_and_detached(self):
        line = ProductionLine.from_blueprint(plan())
        line.step()
        snapshot = line.snapshot()
        self.assertEqual(snapshot["quality"], {
            "mode": "default_good", "good_units": 0, "scrapped_units": 0, "rework_cycles": 0})
        self.assertEqual(snapshot["recent_workpieces"][0]["id"], "WP-0001")
        snapshot["recent_workpieces"][0]["status"] = "tampered"
        self.assertEqual(line.workpiece_genealogy("WP-0001")["status"], "IN_PROCESS")

    def test_deep_genealogy_audit_rejects_corruption(self):
        line = ProductionLine.from_blueprint(plan())
        for _ in range(5):
            line.step()
        line.genealogy["WP-0001"].visits[1].station = "Pack"
        with self.assertRaises(ValueError):
            line.audit_genealogy()


class GenealogyApiTest(unittest.TestCase):
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
            api.SIM = ProductionLine.from_blueprint(plan())

    def request(self, path):
        conn = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        try:
            conn.request("GET", path)
            response = conn.getresponse()
            return response.status, json.loads(response.read())
        finally:
            conn.close()

    def test_genealogy_endpoint_is_read_only(self):
        status, snapshot = self.request("/api/snapshot")
        self.assertEqual(status, 200)
        self.assertEqual(snapshot["tick"], 1)
        status, record = self.request("/api/workpieces/WP-0001")
        self.assertEqual(status, 200)
        self.assertEqual(record["id"], "WP-0001")
        self.assertEqual(api.SIM.tick, 1)
        status, err = self.request("/api/workpieces/WP-9999")
        self.assertEqual(status, 404)
        self.assertEqual(err, {"error": "workpiece not found"})
        self.assertEqual(api.SIM.tick, 1)


if __name__ == "__main__":
    unittest.main()
