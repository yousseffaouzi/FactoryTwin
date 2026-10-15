"""FT-010: production metrics and explicitly assumed synthetic OEE."""
import json
from pathlib import Path
import tempfile
import unittest

from factorytwin.blueprint import FactoryBlueprint
from factorytwin.metrics import MetricsPlan, production_metrics
from factorytwin.persistence import PersistentProductionLine
from factorytwin.quality import QualityScenario
from factorytwin.sim import ProductionLine


def one_station(cycle=1):
    return FactoryBlueprint.from_dict({
        "version": 1,
        "stations": [{"id": "Only", "cycle_ticks": cycle}],
        "connections": [],
    })


def enabled(ideal=1):
    return MetricsPlan(True, ideal)


class ProductionMetricsTest(unittest.TestCase):
    def test_default_metrics_do_not_invent_oee(self):
        line = ProductionLine(blueprint=one_station())
        for _ in range(3):
            line.step()
        metrics = line.snapshot()["metrics"]
        self.assertEqual(metrics["observation_ticks"], 3)
        self.assertEqual(metrics["production_enabled_ticks"], 3)
        self.assertIsNone(metrics["planned_ticks"])
        self.assertIsNone(metrics["availability"])
        self.assertIsNone(metrics["performance"])
        self.assertIsNone(metrics["oee"])
        self.assertEqual(metrics["quality"], 1.0)

    def test_known_all_running_case(self):
        line = ProductionLine(blueprint=one_station())
        line.metrics_plan = enabled(1)
        for _ in range(5):
            line.step()
        metrics = production_metrics(line)
        self.assertEqual(line.completed, 4)
        self.assertEqual(metrics["planned_ticks"], 5)
        self.assertEqual(metrics["production_enabled_ticks"], 5)
        self.assertEqual(metrics["availability"], 1.0)
        self.assertEqual(metrics["performance"], 0.8)
        self.assertEqual(metrics["quality"], 1.0)
        self.assertEqual(metrics["oee"], 0.8)

    def test_pause_counts_as_downtime_only_when_plan_explicitly_enabled(self):
        line = ProductionLine(blueprint=one_station())
        line.metrics_plan = enabled(1)
        line.step()
        line.step()
        line.control("pause")
        line.step()
        line.step()
        line.control("resume")
        line.step()
        metrics = production_metrics(line)
        self.assertEqual(metrics["observation_ticks"], 5)
        self.assertEqual(metrics["planned_ticks"], 5)
        self.assertEqual(metrics["production_enabled_ticks"], 3)
        self.assertAlmostEqual(metrics["availability"], 3 / 5)
        self.assertAlmostEqual(metrics["performance"], 2 / 3)
        self.assertAlmostEqual(metrics["oee"], 2 / 5)

    def test_fault_interlock_reduces_declared_availability(self):
        line = ProductionLine(blueprint=one_station())
        line.metrics_plan = enabled(1)
        line.step()
        line.control("fault", "Only")
        line.step()
        line.step()
        line.control("clear_fault")
        line.step()
        metrics = production_metrics(line)
        self.assertEqual(metrics["planned_ticks"], 4)
        self.assertEqual(metrics["production_enabled_ticks"], 2)
        self.assertEqual(metrics["availability"], 0.5)

    def test_quality_uses_good_over_terminal_units(self):
        scenario = QualityScenario.from_dict({
            "version": 1,
            "decisions": [{"workpiece_id": "WP-0001", "station": "Only",
                           "attempt": 1, "outcome": "SCRAP"}],
        })
        line = ProductionLine(blueprint=one_station(), quality_scenario=scenario)
        line.metrics_plan = enabled(1)
        for _ in range(4):
            line.step()
        metrics = production_metrics(line)
        self.assertEqual((line.completed, line.scrapped), (2, 1))
        self.assertEqual(metrics["terminal_units"], 3)
        self.assertAlmostEqual(metrics["quality"], 2 / 3)
        self.assertAlmostEqual(metrics["oee"], 0.5)

    def test_zero_denominators_are_null_not_zero_or_fabricated(self):
        line = ProductionLine(blueprint=one_station())
        line.metrics_plan = enabled(1)
        line.control("pause")
        line.step()
        metrics = production_metrics(line)
        self.assertEqual(metrics["availability"], 0.0)
        self.assertIsNone(metrics["performance"])
        self.assertIsNone(metrics["quality"])
        self.assertIsNone(metrics["oee"])

    def test_performance_above_one_is_not_hidden(self):
        line = ProductionLine(blueprint=one_station())
        line.metrics_plan = enabled(10)
        for _ in range(3):
            line.step()
        metrics = production_metrics(line)
        self.assertGreater(metrics["performance"], 1.0)
        self.assertTrue(metrics["warnings"])

    def test_metrics_plan_validation_and_local_loading(self):
        invalid = [
            None,
            {},
            {"version": 1, "planned_observation_ticks": True, "ideal_cycle_ticks": None},
            {"version": 1, "planned_observation_ticks": False, "ideal_cycle_ticks": 1},
            {"version": 1, "planned_observation_ticks": True, "ideal_cycle_ticks": True},
            {"version": 1, "planned_observation_ticks": True, "ideal_cycle_ticks": 0},
        ]
        for item in invalid:
            with self.subTest(item=item), self.assertRaises(ValueError):
                MetricsPlan.from_dict(item)
        raw = {"version": 1, "planned_observation_ticks": True, "ideal_cycle_ticks": 2}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "metrics.json"
            path.write_text(json.dumps(raw), encoding="utf-8")
            self.assertEqual(MetricsPlan.load(path).to_dict(), raw)

    def test_reporting_plan_does_not_change_trace_and_survives_reset(self):
        baseline = ProductionLine(blueprint=one_station())
        measured = ProductionLine(blueprint=one_station())
        measured.metrics_plan = enabled(1)
        for _ in range(4):
            baseline.step()
            measured.step()
        self.assertEqual(measured.export_trace(), baseline.export_trace())
        measured.control("reset")
        self.assertEqual(measured.metrics_plan, enabled(1))
        self.assertEqual(production_metrics(measured)["observation_ticks"], 0)

    def test_persistent_recovery_can_apply_reporting_plan_without_schema_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "metrics.sqlite3"
            line = PersistentProductionLine.open(path, blueprint=one_station())
            line.metrics_plan = enabled(1)
            for _ in range(5):
                line.step()
            expected = production_metrics(line)
            restored = PersistentProductionLine.open(path)
            restored.metrics_plan = enabled(1)
            self.assertEqual(production_metrics(restored), expected)


if __name__ == "__main__":
    unittest.main()
