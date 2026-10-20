"""Contract tests for synthetic benchmark reporting."""
import contextlib
import io
import json
import unittest

from factorytwin import benchmark


class BenchmarkContractTest(unittest.TestCase):
    def test_report_has_environment_and_non_threshold_metrics(self):
        report = benchmark.run_benchmark(ticks=20, sqlite_ticks=5)
        self.assertEqual(report["schema"], benchmark.BENCHMARK_SCHEMA)
        self.assertIn("no real-time", report["note"])
        self.assertEqual(report["in_memory"]["ticks"], 20)
        self.assertGreater(report["in_memory"]["ticks_per_second"], 0)
        self.assertGreater(report["in_memory"]["snapshot_bytes"], 0)
        self.assertGreater(report["in_memory"]["trace_bytes"], 0)
        self.assertGreater(report["replay"]["operations"], 0)
        self.assertGreater(report["replay"]["operations_per_second"], 0)
        self.assertEqual(report["sqlite"]["ticks"], 5)
        self.assertGreater(report["sqlite"]["storage_bytes"], 0)
        self.assertGreater(report["sqlite"]["ticks_per_second"], 0)
        self.assertIn("python", report["environment"])

    def test_cli_json_is_machine_readable_and_arguments_fail_closed(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            benchmark.main(["--ticks", "5", "--sqlite-ticks", "2", "--json"])
        report = json.loads(output.getvalue())
        self.assertEqual(report["schema"], benchmark.BENCHMARK_SCHEMA)
        self.assertEqual(report["in_memory"]["ticks"], 5)
        self.assertEqual(report["sqlite"]["ticks"], 2)
        for bad_ticks, bad_sqlite in ((0, 1), (1, 0), (True, 1), (1, True)):
            with self.subTest(ticks=bad_ticks, sqlite_ticks=bad_sqlite):
                with self.assertRaises(ValueError):
                    benchmark.run_benchmark(ticks=bad_ticks, sqlite_ticks=bad_sqlite)


if __name__ == "__main__":
    unittest.main()
