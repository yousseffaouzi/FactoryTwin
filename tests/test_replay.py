"""FT-006: deterministic, timestamped operations and verified replay."""
from copy import deepcopy
import json
from pathlib import Path
import unittest

from factorytwin.sim import ProductionLine, TICK_DURATION_MS, TRACE_SCHEMA

FIXTURE = Path(__file__).parent / "fixtures" / "replay_scenario_v1.json"


def example_scenario():
    line = ProductionLine()
    for _ in range(5):
        line.step()
    line.control("pause")
    line.step()
    line.step()
    line.control("fault", "Processing")
    line.control("resume")
    line.step()  # Fault still blocks production.
    line.control("clear_fault")
    for _ in range(5):
        line.step()
    return line


class ReplayTest(unittest.TestCase):
    def test_committed_fixture_reconstructs_state(self):
        data = json.loads(FIXTURE.read_text(encoding="utf-8"))
        replayed = ProductionLine.replay(data)
        self.assertEqual(replayed.state_data(), data["final_state"])
        self.assertEqual(replayed.tick, 13)
        self.assertEqual(replayed.completed, 6)
        self.assertEqual(replayed.next_id, 11)
        self.assertEqual(replayed.fault_station, None)
        self.assertTrue(replayed.running)

    def test_same_scenario_has_identical_json_trace(self):
        first = example_scenario().export_trace()
        second = example_scenario().export_trace()
        self.assertEqual(json.dumps(first, sort_keys=True), json.dumps(second, sort_keys=True))
        self.assertEqual(first["schema"], TRACE_SCHEMA)
        self.assertEqual(first["tick_duration_ms"], TICK_DURATION_MS)
        self.assertEqual(first, json.loads(json.dumps(first)))
        self.assertEqual(first, json.loads(FIXTURE.read_text(encoding="utf-8")))

    def test_replayed_run_can_continue_identically(self):
        initial = example_scenario()
        restored = ProductionLine.replay(initial.export_trace())
        for line in (initial, restored):
            line.control("pause")
            line.step()
            line.control("resume")
            line.step()
        self.assertEqual(initial.export_trace(), restored.export_trace())

    def test_elapsed_simulation_time_not_wall_clock(self):
        line = ProductionLine()
        line.step()
        line.control("pause")
        line.step()
        line.control("fault", "Feeder")
        line.control("resume")
        line.step()
        self.assertEqual(line.sim_time_ms, 3000)
        self.assertEqual([(e["event"], e["sim_time_ms"]) for e in line.events],
                         [("workpiece_created", 1000), ("line_paused", 1000),
                          ("fault_injected", 2000), ("line_resumed", 2000)])
        self.assertEqual([e["seq"] for e in line.events], [1, 2, 3, 4])
        self.assertEqual([op["tick"] for op in line.operations], [1, 1, 2, 2, 2, 3])
        self.assertEqual([op["seq"] for op in line.operations], list(range(1, 7)))
        self.assertEqual(line.snapshot()["sim_time_ms"], 3000)

    def test_bounded_ui_events_do_not_truncate_replay_history(self):
        line = ProductionLine()
        for _ in range(140):
            line.step()
        self.assertEqual(len(line.events), 40)
        self.assertEqual(len(line.snapshot()["events"]), 12)
        self.assertEqual(len(line.operations), 140)
        self.assertEqual(line.events[-1]["seq"], line.event_sequence)
        self.assertEqual(line.events[0]["seq"], line.event_sequence - 39)
        self.assertEqual(ProductionLine.replay(line.export_trace()).state_data(), line.state_data())

    def test_reset_restarts_trace_session_and_event_sequence(self):
        line = example_scenario()
        line.control("reset")
        self.assertEqual([event["seq"] for event in line.events], [1])
        self.assertEqual(line.operations, [{"seq": 1, "kind": "control", "action": "reset",
                                            "tick": 0, "sim_time_ms": 0}])
        after_first = line.export_trace()
        self.assertEqual(ProductionLine.replay(after_first).export_trace(), after_first)
        line.control("reset")
        self.assertEqual(line.export_trace(), after_first)
        line.step()
        self.assertEqual(ProductionLine.replay(line.export_trace()).state_data(), line.state_data())

    def test_rejected_command_never_enters_trace(self):
        line = ProductionLine()
        line.control("fault", "Conveyor")
        old = line.export_trace()
        with self.assertRaisesRegex(ValueError, "fault already active"):
            line.control("fault", "Packing")
        with self.assertRaisesRegex(ValueError, "unknown"):
            line.control("not_valid")
        self.assertEqual(line.export_trace(), old)

    def test_valid_idempotent_commands_are_replayable(self):
        line = ProductionLine()
        line.control("resume")  # Accepted but no resulting domain event.
        line.control("pause")
        line.control("pause")
        line.control("resume")
        line.control("clear_fault")
        self.assertEqual(len(line.operations), 5)
        self.assertEqual(len(line.events), 2)
        self.assertEqual(ProductionLine.replay(line.export_trace()).export_trace(), line.export_trace())

    def test_export_and_state_projection_cannot_mutate_internals(self):
        line = example_scenario()
        trace = line.export_trace()
        trace["operations"][0]["tick"] = 999
        trace["final_state"]["conveyor"][0]["id"] = "WRONG"
        trace["final_state"]["events"][0]["event"] = "WRONG"
        self.assertEqual(line.operations[0]["tick"], 1)
        self.assertNotEqual(line.conveyor[0]["id"], "WRONG")
        self.assertNotEqual(line.events[0]["event"], "WRONG")

    def test_empty_line_trace_is_valid(self):
        line = ProductionLine()
        restored = ProductionLine.replay(line.export_trace())
        self.assertEqual(restored.export_trace(), line.export_trace())

    def test_reject_bad_trace_envelope(self):
        base = example_scenario().export_trace()
        for invalid in (None, {}, [], {**base, "schema": "unknown"},
                        {**base, "tick_duration_ms": True}, {**base, "final_state": None},
                        {**base, "operations": None}, {**base, "operations": [None]}):
            with self.subTest(invalid=str(invalid)[:50]):
                with self.assertRaises(ValueError):
                    ProductionLine.replay(invalid)

    def test_reject_reordered_or_missing_steps(self):
        base = example_scenario().export_trace()
        for mutation in ("sequence", "timestamp", "kind", "action", "extra", "missing", "reset"):
            changed = deepcopy(base)
            operation = changed["operations"][2]
            if mutation == "sequence":
                operation["seq"] = 99
            elif mutation == "timestamp":
                operation["sim_time_ms"] += 1000
            elif mutation == "kind":
                operation["kind"] = "hack"
            elif mutation == "action":
                operation["action"] = "unknown"
            elif mutation == "extra":
                operation["unwanted"] = 1
            elif mutation == "missing":
                changed["operations"].pop(2)
            elif mutation == "reset":
                operation["kind"] = "control"
                operation["action"] = "reset"
            with self.subTest(mutation=mutation):
                with self.assertRaises(ValueError):
                    ProductionLine.replay(changed)

    def test_reject_tampered_final_state(self):
        base = example_scenario().export_trace()
        for field, invalid in (("completed", 999), ("fault_station", "Packing"),
                               ("event_sequence", -1), ("tick", 14)):
            trace = deepcopy(base)
            trace["final_state"][field] = invalid
            with self.subTest(field=field):
                with self.assertRaisesRegex(ValueError, "final state mismatch"):
                    ProductionLine.replay(trace)

    def test_reject_boolean_tick_or_time_and_bool_final_counter(self):
        for key in ("tick", "sim_time_ms"):
            trace = example_scenario().export_trace()
            trace["operations"][0][key] = True if key == "tick" else False
            with self.subTest(key=key):
                with self.assertRaises(ValueError):
                    ProductionLine.replay(trace)
        trace = ProductionLine().export_trace()
        trace["final_state"]["completed"] = False
        with self.assertRaisesRegex(ValueError, "final state mismatch"):
            ProductionLine.replay(trace)

    def test_reject_bool_sequence_instead_of_integer(self):
        trace = ProductionLine().export_trace()
        trace["operations"] = [{"seq": True, "kind": "step", "tick": 1,
                                 "sim_time_ms": 1000}]
        with self.assertRaises(ValueError):
            ProductionLine.replay(trace)


if __name__ == "__main__":
    unittest.main()
