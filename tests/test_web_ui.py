"""FT-012 static dashboard accessibility and fallback contract tests."""
from html.parser import HTMLParser
from pathlib import Path
import re
import unittest

WEB = Path(__file__).resolve().parents[1] / "web" / "index.html"


class InventoryParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags = []
        self.ids = set()
        self.labels_for = set()
        self.external = []
        self.progressbars = []

    def handle_starttag(self, tag, attrs):
        data = dict(attrs)
        self.tags.append(tag)
        if data.get("id"):
            self.ids.add(data["id"])
        if tag == "label" and data.get("for"):
            self.labels_for.add(data["for"])
        if data.get("role") == "progressbar":
            self.progressbars.append(data)
        for name in ("src", "href"):
            value = data.get(name, "")
            if value.startswith(("http://", "https://", "//")):
                self.external.append(value)


class DashboardContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = WEB.read_text(encoding="utf-8")
        cls.parser = InventoryParser()
        cls.parser.feed(cls.html)

    def test_semantic_landmarks_and_skip_navigation(self):
        for tag in ("header", "main", "section", "aside", "footer"):
            self.assertIn(tag, self.parser.tags)
        self.assertIn('class="skip" href="#factory-floor"', self.html)
        self.assertIn('aria-labelledby="floor-title"', self.html)
        self.assertIn('aria-live="polite"', self.html)

    def test_controls_are_labeled_and_keyboard_native(self):
        self.assertIn("station", self.parser.ids)
        self.assertIn("station", self.parser.labels_for)
        self.assertNotIn("tabindex=\"-1\"", self.html)
        self.assertIn("focus-visible", self.html)
        for action in ("pause", "resume", "fault", "clear_fault", "reset"):
            self.assertIn(f"act('{action}')", self.html)

    def test_status_is_not_encoded_by_color_alone(self):
        self.assertIn("station-state", self.html)
        self.assertIn("${esc(s.status)}", self.html)
        self.assertIn("Line '+d.state", self.html)
        self.assertIn("Simulation boundary", self.html)

    def test_responsive_and_reduced_motion_styles_exist(self):
        self.assertIn("@media(max-width:980px)", self.html)
        self.assertIn("@media(max-width:640px)", self.html)
        self.assertIn("prefers-reduced-motion:reduce", self.html)
        self.assertIn("grid-template-columns:1fr", self.html)

    def test_stream_is_display_transport_and_polling_remains_driver(self):
        self.assertIn("new EventSource('/api/stream')", self.html)
        self.assertIn("source.addEventListener('snapshot'", self.html)
        self.assertIn("source.addEventListener('resync'", self.html)
        self.assertIn("fetch('/api/snapshot'", self.html)
        self.assertIn("setInterval(poll,1500)", self.html)
        self.assertIn("Polling fallback", self.html)

    def test_oee_null_is_rendered_as_undefined_not_zero(self):
        self.assertIn("const pct=v=>v==null?'—'", self.html)
        for element_id in ("oee", "availability", "performance", "quality"):
            self.assertIn(f'id="{element_id}"', self.html)

    def test_station_floor_has_route_progress_and_accessible_machine_text(self):
        self.assertIn('aria-label="Production stations"', self.html)
        self.assertIn('role="progressbar"', self.html)
        self.assertIn('aria-valuenow="${progress}"', self.html)
        self.assertIn("Material entry", self.html)
        self.assertIn("Finished output", self.html)

    def test_no_external_frontend_resources_or_3d_runtime(self):
        self.assertEqual(self.parser.external, [])
        lowered = self.html.lower()
        self.assertNotIn("webgl", lowered)
        self.assertNotIn("three.js", lowered)
        self.assertNotIn("<canvas", lowered)

    def test_escaping_is_used_for_snapshot_derived_html(self):
        self.assertIn("const esc=", self.html)
        risky = re.findall(r"innerHTML=.*", self.html)
        self.assertTrue(risky)
        self.assertIn("esc(s.name)", self.html)
        self.assertIn("esc(w.id)", self.html)
        self.assertIn("esc(e.event)", self.html)


if __name__ == "__main__":
    unittest.main()
