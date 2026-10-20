"""Packaging, versioning and installed-asset contract tests."""
from pathlib import Path
import tomllib
import unittest

from factorytwin import __main__ as app
from factorytwin._version import __version__

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = PROJECT_ROOT / "pyproject.toml"
PACKAGED_WEB = PROJECT_ROOT / "factorytwin" / "web" / "index.html"
SOURCE_WEB = PROJECT_ROOT / "web" / "index.html"


class PackagingContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))

    def test_project_metadata_preserves_stdlib_runtime_boundary(self):
        project = self.config["project"]
        self.assertEqual(project["name"], "factorytwin")
        self.assertEqual(project["requires-python"], ">=3.11")
        self.assertEqual(project["dependencies"], [])
        self.assertEqual(project["scripts"]["factorytwin"], "factorytwin.__main__:main")

    def test_version_has_one_private_source_of_truth(self):
        project = self.config["project"]
        self.assertNotIn("version", project)
        self.assertEqual(project["dynamic"], ["version"])
        dynamic = self.config["tool"]["setuptools"]["dynamic"]
        self.assertEqual(dynamic["version"]["attr"], "factorytwin._version.__version__")
        self.assertRegex(__version__, r"^\d+\.\d+\.\d+\.dev\d+$")

    def test_dashboard_is_served_from_package_data(self):
        self.assertEqual(app.ROOT, PACKAGED_WEB.parent)
        self.assertTrue(PACKAGED_WEB.is_file())
        self.assertEqual(PACKAGED_WEB.read_bytes(), SOURCE_WEB.read_bytes())

    def test_setuptools_declares_dashboard_package_data(self):
        package_data = self.config["tool"]["setuptools"]["package-data"]
        self.assertIn("web/index.html", package_data["factorytwin"])


if __name__ == "__main__":
    unittest.main()
