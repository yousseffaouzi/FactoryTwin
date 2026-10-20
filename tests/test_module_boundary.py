"""Regression tests for the public simulator/module boundary."""
import inspect
import unittest

import factorytwin
from factorytwin import fault_persistence, faults, genealogy, persistence, sim
from factorytwin.engine import ProductionLine as EngineProductionLine
from factorytwin.fault_persistence import FaultPersistentProductionLine
from factorytwin.genealogy import GenealogyProductionLine
from factorytwin.persistence import PersistentProductionLine
from factorytwin.runtime import RuntimeProductionLine


PACKAGE_PUBLIC_API = [
    "MULTI_FAULT_TRACE_SCHEMA",
    "ProductionLine",
    "QUALITY_TRACE_SCHEMA",
]

SIM_PUBLIC_API = [
    "CUSTOM_TRACE_SCHEMA",
    "EngineProductionLine",
    "LineState",
    "MAX_REPLAY_OPERATIONS",
    "MULTI_FAULT_TRACE_SCHEMA",
    "ProductionLine",
    "QUALITY_TRACE_SCHEMA",
    "STATIONS",
    "TICK_DURATION_MS",
    "TRACE_SCHEMA",
]


def _star_import_names(statement):
    namespace = {}
    exec(statement, namespace)
    return {name for name in namespace if name != "__builtins__"}


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

    def test_package_public_api_is_explicit_and_resolvable(self):
        self.assertEqual(factorytwin.__all__, PACKAGE_PUBLIC_API)
        for name in PACKAGE_PUBLIC_API:
            self.assertTrue(hasattr(factorytwin, name), name)
        self.assertEqual(
            _star_import_names("from factorytwin import *"),
            set(PACKAGE_PUBLIC_API),
        )
        self.assertNotIn("EngineProductionLine", factorytwin.__all__)

    def test_sim_public_api_is_explicit_and_resolvable(self):
        self.assertEqual(sim.__all__, SIM_PUBLIC_API)
        for name in SIM_PUBLIC_API:
            self.assertTrue(hasattr(sim, name), name)
        self.assertEqual(
            _star_import_names("from factorytwin.sim import *"),
            set(SIM_PUBLIC_API),
        )
        self.assertIs(sim.ProductionLine, factorytwin.ProductionLine)
        self.assertIs(sim.EngineProductionLine, EngineProductionLine)

    def test_internal_layers_do_not_import_public_sim_facade(self):
        self.assertNotIn("from .sim import", inspect.getsource(genealogy))
        self.assertNotIn("from .sim import", inspect.getsource(faults))
        self.assertIs(genealogy.LegacyProductionLine, EngineProductionLine)
        self.assertEqual(faults.LineState.__module__, "factorytwin.engine")
        sim_source = inspect.getsource(sim)
        self.assertEqual(sim_source.count("ProductionLine ="), 1)
        self.assertIn("ProductionLine = RuntimeProductionLine", sim_source)

    def test_persistence_layers_depend_on_runtime_not_public_facade(self):
        for module in (persistence, fault_persistence):
            with self.subTest(module=module.__name__):
                self.assertNotIn("from .sim import", inspect.getsource(module))
        self.assertIs(PersistentProductionLine.__mro__[1], RuntimeProductionLine)
        self.assertIs(FaultPersistentProductionLine.__mro__[1], PersistentProductionLine)
        self.assertIs(persistence.ProductionLine, RuntimeProductionLine)
        self.assertIs(fault_persistence.ProductionLine, RuntimeProductionLine)

    def test_fault_persistence_runtime_bypass_is_explicit(self):
        source = inspect.getsource(fault_persistence.FaultPersistentProductionLine)
        self.assertNotIn("super(PersistentProductionLine, self)", source)
        self.assertIn("RuntimeProductionLine.step(self)", source)
        self.assertIn("RuntimeProductionLine.control(self, action, station)", source)
        self.assertIs(fault_persistence.RuntimeProductionLine, RuntimeProductionLine)
        self.assertIs(fault_persistence.ProductionLine, RuntimeProductionLine)


if __name__ == "__main__":
    unittest.main()