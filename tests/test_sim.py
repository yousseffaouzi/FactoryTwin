import copy
import unittest

from factorytwin.sim import LineState, ProductionLine, STATIONS


class FactoryTwinTest(unittest.TestCase):
    def test_pipeline_produces(self):
        line = ProductionLine()
        for _ in range(7):
            line.step()
        self.assertEqual(line.completed, 3)
        self.assertEqual(line.snapshot()["state"], "RUNNING")

    def test_pause_freezes_equipment(self):
        line = ProductionLine()
        line.step()
        previous = copy.deepcopy(line.conveyor)
        line.control("pause")
        line.step()
        self.assertEqual(line.conveyor, previous)
        self.assertEqual(line.snapshot()["state"], "PAUSED")

    def test_fault_blocks_until_cleared(self):
        line = ProductionLine()
        line.control("fault", "Processing")
        line.step()
        self.assertEqual(line.snapshot()["state"], "FAULT")
        self.assertEqual(line.completed, 0)
        line.control("clear_fault")
        line.step()
        self.assertEqual(line.snapshot()["state"], "RUNNING")

    def test_invalid_station_rejected(self):
        with self.assertRaisesRegex(ValueError, "unknown station"):
            ProductionLine().control("fault", "Unknown")

    def test_reset_clears_counters(self):
        line = ProductionLine()
        for _ in range(8):
            line.step()
        self.assertGreater(line.completed, 0)
        line.control("reset")
        self.assertEqual(line.completed, 0)
        self.assertEqual(line.tick, 0)

    def test_initial_state_and_existing_snapshot_contract(self):
        line = ProductionLine()
        self.assertEqual(line.state, LineState.RUNNING)
        snapshot = line.snapshot()
        self.assertEqual(snapshot["state"], "RUNNING")
        self.assertEqual(snapshot["source"], "synthetic")
        self.assertEqual(snapshot["in_process"], 0)
        self.assertEqual([station["name"] for station in snapshot["stations"]], list(STATIONS))
        self.assertIn("recorded_at_utc", snapshot)

    def test_pause_resume_transition_and_processing(self):
        line = ProductionLine()
        line.step()
        line.control("pause")
        self.assertEqual(line.state, LineState.PAUSED)
        line.step()
        self.assertEqual(line.next_id, 2)
        line.control("resume")
        self.assertEqual(line.state, LineState.RUNNING)
        line.step()
        self.assertEqual(line.next_id, 3)

    def test_pause_and_resume_are_idempotent(self):
        line = ProductionLine()
        line.control("resume")
        self.assertEqual(line.events, [])
        line.control("pause")
        line.control("pause")
        self.assertEqual([e["event"] for e in line.events], ["line_paused"])
        line.control("resume")
        line.control("resume")
        self.assertEqual([e["event"] for e in line.events], ["line_paused", "line_resumed"])

    def test_fault_while_paused_remains_latched(self):
        line = ProductionLine()
        line.control("pause")
        line.control("fault", "Processing")
        self.assertEqual(line.state, LineState.PAUSED)
        statuses = {s["name"]: s["status"] for s in line.snapshot()["stations"]}
        self.assertEqual(statuses["Processing"], "FAULT")
        self.assertEqual(statuses["Feeder"], "PAUSED")
        line.control("resume")
        self.assertEqual(line.state, LineState.FAULT)
        line.step()
        self.assertEqual(line.next_id, 1)

    def test_resume_cannot_override_fault_interlock(self):
        line = ProductionLine()
        line.step()
        line.control("fault", "Feeder")
        before = (copy.deepcopy(line.conveyor), line.completed, line.next_id)
        line.control("resume")
        for _ in range(4):
            line.step()
        self.assertEqual((line.conveyor, line.completed, line.next_id), before)
        self.assertEqual(line.state, LineState.FAULT)

    def test_clear_fault_does_not_resume_paused_line(self):
        line = ProductionLine()
        line.control("fault", "Packing")
        line.control("pause")
        line.control("clear_fault")
        self.assertEqual(line.state, LineState.PAUSED)
        self.assertIsNone(line.fault_station)
        line.step()
        self.assertEqual(line.next_id, 1)
        line.control("resume")
        self.assertEqual(line.state, LineState.RUNNING)

    def test_duplicate_fault_does_not_emit_events(self):
        line = ProductionLine()
        line.control("fault", "Conveyor")
        line.control("fault", "Conveyor")
        self.assertEqual([e["event"] for e in line.events], ["fault_injected"])

    def test_second_distinct_fault_rejected_without_mutation(self):
        line = ProductionLine()
        line.control("fault", "Conveyor")
        before = copy.deepcopy(line.__dict__)
        with self.assertRaisesRegex(ValueError, "fault already active"):
            line.control("fault", "Packing")
        self.assertEqual(line.__dict__, before)

    def test_invalid_actions_do_not_mutate_state(self):
        line = ProductionLine()
        line.step()
        before = copy.deepcopy(line.__dict__)
        for action, station in (("launch", None), (None, None), ("fault", "Missing"), ("fault", None)):
            with self.subTest(action=action, station=station):
                with self.assertRaises(ValueError):
                    line.control(action, station)
                self.assertEqual(line.__dict__, before)

    def test_clearing_nonexistent_fault_is_noop(self):
        line = ProductionLine()
        line.control("clear_fault")
        self.assertEqual(line.events, [])
        self.assertEqual(line.state, LineState.RUNNING)

    def test_reset_clears_pause_fault_pipeline_and_events(self):
        line = ProductionLine()
        for _ in range(8):
            line.step()
        line.control("pause")
        line.control("fault", "Processing")
        line.control("reset")
        self.assertEqual(line.state, LineState.RUNNING)
        self.assertEqual(line.tick, 0)
        self.assertEqual(line.next_id, 1)
        self.assertEqual(line.completed, 0)
        self.assertEqual(line.scrapped, 0)
        self.assertIsNone(line.fault_station)
        self.assertEqual(line.conveyor, [None] * len(STATIONS))
        self.assertEqual(line.events, [{"tick": 0, "event": "simulation_reset"}])
        line.step()
        self.assertEqual(line.next_id, 2)

    def test_repeated_reset_is_predictable(self):
        line = ProductionLine()
        line.control("reset")
        after_first = copy.deepcopy(line.__dict__)
        line.control("reset")
        self.assertEqual(line.__dict__, after_first)

    def test_all_fault_stations_block_the_line(self):
        for station in STATIONS:
            with self.subTest(station=station):
                line = ProductionLine()
                line.step()
                line.control("fault", station)
                statuses = {s["name"]: s["status"] for s in line.snapshot()["stations"]}
                self.assertEqual(statuses[station], "FAULT")
                self.assertEqual(sum(s == "BLOCKED" for s in statuses.values()), len(STATIONS) - 1)
                before = copy.deepcopy(line.conveyor)
                line.step()
                self.assertEqual(line.conveyor, before)
                line.control("clear_fault")
                self.assertEqual(line.state, LineState.RUNNING)

    def test_tick_advances_during_interlocks_but_workpieces_do_not(self):
        line = ProductionLine()
        line.control("pause")
        line.step()
        line.control("fault", "Feeder")
        line.step()
        self.assertEqual(line.tick, 2)
        self.assertEqual(line.next_id, 1)
        self.assertEqual(line.completed, 0)
        self.assertEqual(line.snapshot()["in_process"], 0)

    def test_counter_conservation_many_steps_and_recovery(self):
        line = ProductionLine()
        for step in range(150):
            if step == 20:
                line.control("pause")
            elif step == 30:
                line.control("resume")
            elif step == 60:
                line.control("fault", "Packing")
            elif step == 80:
                line.control("clear_fault")
            line.step()
            line.validate()
            self.assertEqual(line.next_id - 1, line.completed + line.scrapped + line.snapshot()["in_process"])
        self.assertEqual(line.scrapped, 0)

    def test_snapshot_events_are_detached(self):
        line = ProductionLine()
        line.step()
        snapshot = line.snapshot()
        snapshot["events"][0]["event"] = "tampered"
        snapshot["stations"][0]["status"] = "tampered"
        self.assertEqual(line.events[0]["event"], "workpiece_created")
        self.assertEqual(line.snapshot()["stations"][0]["status"], "RUNNING")

    def test_corrupt_counters_rejected_before_mutation(self):
        line = ProductionLine()
        line.step()
        line.completed = -1
        before = copy.deepcopy(line.__dict__)
        with self.assertRaisesRegex(ValueError, "invalid completed"):
            line.step()
        self.assertEqual(line.__dict__, before)
        line.control("reset")
        line.validate()

    def test_corrupt_or_duplicate_workpieces_rejected(self):
        line = ProductionLine()
        line.step()
        line.conveyor[1] = copy.deepcopy(line.conveyor[0])
        before = copy.deepcopy(line.__dict__)
        with self.assertRaisesRegex(ValueError, "duplicate workpiece"):
            line.step()
        self.assertEqual(line.__dict__, before)
        line.control("reset")
        line.validate()

    def test_large_workpiece_identifiers_remain_valid(self):
        line = ProductionLine()
        for _ in range(10002):
            line.step()
        line.validate()
        self.assertEqual(line.next_id, 10003)
        self.assertEqual(line.completed, 9998)


if __name__ == "__main__":
    unittest.main()
