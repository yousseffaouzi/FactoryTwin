"""End-to-end subprocess acceptance regression for the local FactoryTwin demo."""
import unittest

from factorytwin.acceptance import run_acceptance


class LocalAcceptanceHarnessTest(unittest.TestCase):
    def test_controls_genealogy_and_sqlite_restart_recovery(self):
        report = run_acceptance()
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["bind"], "127.0.0.1")
        self.assertTrue(report["clean_shutdown"])
        self.assertGreater(report["first_port"], 0)
        self.assertGreater(report["second_port"], 0)

        checkpoint = report["checkpoint"]
        recovered = report["after_restart"]
        self.assertEqual(checkpoint["state"], "RUNNING")
        self.assertEqual(checkpoint["fault_stations"], [])
        self.assertEqual(checkpoint["good_units"], checkpoint["completed"])
        self.assertEqual(recovered["tick"], checkpoint["tick"] + 1)
        self.assertGreaterEqual(recovered["completed"], checkpoint["completed"])
        self.assertGreater(recovered["continued_completed"], checkpoint["completed"])
        self.assertGreater(recovered["continued_tick"], recovered["tick"])
        self.assertEqual(checkpoint["genealogy"]["status"], "COMPLETED")
        self.assertTrue(all(visit["outcome"] == "GOOD"
                            for visit in checkpoint["genealogy"]["visits"]))


if __name__ == "__main__":
    unittest.main()
