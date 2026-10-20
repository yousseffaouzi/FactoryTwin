"""Regression tests for the declared CI interpreter/installability contract."""
from pathlib import Path
import unittest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = PROJECT_ROOT / ".github" / "workflows" / "test.yml"


class CiContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = WORKFLOW.read_text(encoding="utf-8")

    def test_supported_python_matrix_includes_declared_minimum(self):
        self.assertIn("python-version: ['3.11', '3.12']", self.workflow)
        self.assertIn("python-version: ${{ matrix.python-version }}", self.workflow)

    def test_each_matrix_job_keeps_source_and_installed_package_gates(self):
        self.assertIn("python -m unittest discover -s tests -v", self.workflow)
        self.assertIn("python -m pip wheel . --no-deps --wheel-dir dist", self.workflow)
        self.assertIn("python -m venv .wheel-venv", self.workflow)
        self.assertIn("pip install --no-deps dist/factorytwin-*.whl", self.workflow)
        self.assertIn("cd /tmp", self.workflow)

    def test_windows_python312_source_gate_is_explicit(self):
        self.assertIn("  windows-test:\n", self.workflow)
        windows_job = self.workflow.split("  windows-test:\n", 1)[1]
        self.assertIn("runs-on: windows-latest", windows_job)
        self.assertIn("python-version: '3.12'", windows_job)
        self.assertIn("python -m unittest discover -s tests -v", windows_job)


if __name__ == "__main__":
    unittest.main()
