"""Regression tests for the public simulator/module boundary."""
import inspect
import unittest

import factorytwin
from factorytwin import faults, genealogy, sim
from factorytwin.engine import ProductionLine as EngineProductionLine
from factorytwin.genealogy import GenealogyProductionLine
from factorytwin.runtime import RuntimeProductionLine


class ModuleBoundaryTest(unittest.TestCase):
    def test_public_sim_facade_exposes_runtime_without_package_mutation(self):
        self.assertIs(sim.ProductionLine, RuntimeProductionLine)
        self.assertIs(factorytwin.ProductionLine, RuntimeProductionLine)

    def test_engine_base_remains_distinct_and_stable(self):
        self.assertIsNot(EngineProductionLine, RuntimeProductionLine)
        self.assertIs(GenealogyProductionLine.__mro__[1], EngineProductionLine)
        self.assertEqual(EngineProductionLine.__module__, "factorytwin.engine")

    def test_public_trace_symbols_are_available_without_runtime_rebinding(self):
        self.assertEqual(sim.QUALITY_TRACE_SCHEMA, "factorytwin.trace.v3")
        self.assertEqual(sim.MULTI_FAULT_TRACE_SCHEMA, "factorytwin.trace.v4")
        self.assertIs(sim.EngineProductionLine, EngineProductionLine)

    def test_internal_layers_do_not_import_public_sim_facade(self):
        self.assertNotIn("from .sim import", inspect.getsource(genealogy))
        self.assertNotIn("from .sim import", inspect.getsource(faults))
        self.assertIs(genealogy.LegacyProductionLine, EngineProductionLine)
        self.assertEqual(faults.LineState.__module__, "factorytwin.engine")
        sim_source = inspect.getsource(sim)
        self.assertEqual(sim_source.count("ProductionLine ="), 1)
        self.assertIn("ProductionLine = RuntimeProductionLine", sim_source)


if __name__ == "__main__":
    unittest.main()
