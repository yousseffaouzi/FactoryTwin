"""Bounded long-run reliability validation for deterministic simulation and recovery."""
import json
from pathlib import Path
import tempfile
import unittest

from factorytwin.fault_persistence import FaultPersistentProductionLine
from factorytwin.sim import ProductionLine


class LongRunValidationTest(unittest.TestCase):
    def assert_conserved(self, line):
        snapshot = line.snapshot()
        self.assertEqual(
            line.next_id - 1,
            line.completed + line.scrapped + snapshot["in_process"],
        )

    def test_mixed_interlock_long_run_replays_and_continues_exactly(self):
        line = ProductionLine()
        controls = {
            120: ("pause", None),
            150: ("resume", None),
            360: ("fault_add", "Feeder"),
            390: ("fault_add", "Packing"),
            420: ("clear_fault_station", "Feeder"),
            460: ("clear_fault_station", "Packing"),
            700: ("pause", None),
            730: ("resume", None),
        }

        for index in range(1_200):
            if index in controls:
                action, station = controls[index]
                line.control(action, station)
            line.step()
            if index % 100 == 0:
                line.validate()
                self.assert_conserved(line)

        line.validate()
        line.audit_genealogy()
        self.assert_conserved(line)
        self.assertEqual(line.scrapped, 0)
        self.assertGreater(line.completed, 0)
        self.assertEqual(line.fault_stations, [])

        trace = json.loads(json.dumps(line.export_trace()))
        restored = ProductionLine.replay(trace)
        self.assertEqual(restored.export_trace(), trace)
        restored.audit_genealogy()

        for _ in range(50):
            line.step()
            restored.step()
        line.validate()
        restored.validate()
        self.assertEqual(restored.export_trace(), line.export_trace())
        self.assert_conserved(restored)

    def test_repeated_sqlite_reopen_preserves_exact_long_running_session(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "soak.sqlite3"
            line = FaultPersistentProductionLine.open(path)
            stations = ("Feeder", "Conveyor", "Processing", "Packing")

            for cycle, station in enumerate(stations):
                for offset in range(100):
                    if offset == 20:
                        line.control("fault_add", station)
                    elif offset == 30:
                        line.control("pause")
                    elif offset == 35:
                        line.control("resume")
                    elif offset == 45:
                        line.control("clear_fault_station", station)
                    line.step()
                    if offset % 25 == 0:
                        line.validate()
                        self.assert_conserved(line)

                expected = json.loads(json.dumps(line.export_trace()))
                line = FaultPersistentProductionLine.open(path)
                self.assertEqual(line.export_trace(), expected, f"reopen cycle {cycle}")
                line.validate()
                line.audit_genealogy()
                self.assert_conserved(line)
                self.assertEqual(line.fault_stations, [])

            self.assertEqual(line.tick, 400)
            self.assertEqual(line.scrapped, 0)
            self.assertGreater(line.completed, 0)


if __name__ == "__main__":
    unittest.main()
