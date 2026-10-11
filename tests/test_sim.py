import unittest
from factorytwin.sim import ProductionLine


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
        previous = list(line.conveyor)
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
        with self.assertRaises(ValueError):
            ProductionLine().control("fault", "Unknown")

    def test_reset_clears_counters(self):
        line = ProductionLine()
        for _ in range(8):
            line.step()
        self.assertGreater(line.completed, 0)
        line.control("reset")
        self.assertEqual(line.completed, 0)
        self.assertEqual(line.tick, 0)


if __name__ == "__main__":
    unittest.main()
