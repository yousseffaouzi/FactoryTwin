"""Repository-level software release-readiness guardrails."""
from pathlib import Path
import tomllib
import unittest

from factorytwin._version import __version__

ROOT = Path(__file__).resolve().parents[1]


def text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


class ReleaseReadinessTest(unittest.TestCase):
    def test_required_release_and_validation_documents_exist(self):
        required = (
            "LICENSE",
            "CHANGELOG.md",
            "docs/PUBLIC_API.md",
            "docs/RELEASES.md",
            "docs/RELEASE_CHECKLIST.md",
            "docs/VALIDATION.md",
            "docs/PERFORMANCE.md",
            "docs/DEMO.md",
        )
        for path in required:
            with self.subTest(path=path):
                self.assertTrue((ROOT / path).is_file())
                self.assertGreater((ROOT / path).stat().st_size, 0)

    def test_scope_and_physical_integration_guards_remain_explicit(self):
        readme = text("README.md")
        self.assertIn("pre-alpha research/demo software", readme)
        self.assertIn("not a PLC, SCADA system, wire-compatible OPC UA server", readme)
        self.assertIn("server binds to `127.0.0.1`", readme)
        self.assertIn("must never be used as an industrial control or safety system", readme)
        todo = text("TODO.md")
        self.assertIn("| FT-016 | ON HOLD |", todo)
        self.assertIn("Tracker does not indicate a production-ready industrial digital twin.", todo)

    def test_development_version_and_release_actions_stay_approval_gated(self):
        self.assertRegex(__version__, r"^\d+\.\d+\.\d+\.dev\d+$")
        releases = text("docs/RELEASES.md")
        checklist = text("docs/RELEASE_CHECKLIST.md")
        self.assertIn("requires explicit project-owner approval", releases)
        self.assertIn("No PyPI publication is currently claimed or automated.", releases)
        self.assertIn("Explicit project-owner approval to promote or merge into `main`.", checklist)
        self.assertIn("Explicit approval to create a Git tag or GitHub release.", checklist)
        self.assertIn("FT-016 physical PLC/SCADA/robotics/plant integration remains `ON HOLD`", checklist)

    def test_packaging_and_ci_release_gates_match_documented_support(self):
        config = tomllib.loads(text("pyproject.toml"))
        project = config["project"]
        self.assertEqual(project["requires-python"], ">=3.11")
        self.assertEqual(project["dependencies"], [])
        self.assertEqual(project["dynamic"], ["version"])
        workflow = text(".github/workflows/test.yml")
        self.assertIn("python-version: ['3.11', '3.12']", workflow)
        self.assertIn("python -m unittest discover -s tests -v", workflow)
        self.assertIn("python -m pip wheel . --no-deps --wheel-dir dist", workflow)
        self.assertIn("pip install --no-deps dist/factorytwin-*.whl", workflow)
        self.assertIn("python -m factorytwin.benchmark --ticks 2000 --sqlite-ticks 100 --json", workflow)


if __name__ == "__main__":
    unittest.main()
