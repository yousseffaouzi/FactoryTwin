"""Runtime composition regressions for the post-FT-015 engine cleanup."""
import unittest

import factorytwin
from factorytwin.genealogy import GenealogyProductionLine
from factorytwin.metrics import MetricsPlan
from factorytwin.runtime import RuntimeProductionLine
from factorytwin.sim import ProductionLine


class RuntimeCompositionTest(unittest.TestCase):
    def test_public_simulator_is_explicit_runtime_class(self):
        self.assertIs(ProductionLine, RuntimeProductionLine)
        self.assertTrue(issubclass(RuntimeProductionLine, GenealogyProductionLine))

    def test_package_import_does_not_replace_parent_methods(self):
        self.assertEqual(GenealogyProductionLine.snapshot.__module__, "factorytwin.genealogy")
        self.assertEqual(GenealogyProductionLine.control.__module__, "factorytwin.genealogy")
        self.assertEqual(GenealogyProductionLine.replay.__func__.__module__, "factorytwin.genealogy")
        self.assertFalse(hasattr(factorytwin, "_original_snapshot"))
        self.assertFalse(hasattr(factorytwin, "_original_control"))
        self.assertFalse(hasattr(factorytwin, "_original_replay"))

    def test_runtime_keeps_metrics_additive_and_reset_preserves_plan(self):
        line = ProductionLine()
        plan = MetricsPlan(planned_observation_ticks=True, ideal_cycle_ticks=4)
        line.metrics_plan = plan
        line.step()
        snapshot = line.snapshot()
        self.assertEqual(snapshot["metrics"]["plan"], plan.to_dict())
        self.assertIn("quality", snapshot)
        self.assertIn("fault_stations", snapshot)

        line.control("reset")
        self.assertEqual(line.metrics_plan, plan)
        self.assertEqual(line.snapshot()["metrics"]["plan"], plan.to_dict())


if __name__ == "__main__":
    unittest.main()
