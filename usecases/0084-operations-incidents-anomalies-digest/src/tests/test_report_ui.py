import copy
import json
import sys
import unittest
from html.parser import HTMLParser

from support import REFERENCE, ROOT, fixture, load_engine


class StructureParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = set()
        self.meta_csp = None

    def handle_starttag(self, tag, attrs):
        attr_map = dict(attrs)
        if "id" in attr_map:
            self.ids.add(attr_map["id"])
        if tag == "meta" and attr_map.get("http-equiv", "").lower() == "content-security-policy":
            self.meta_csp = attr_map.get("content")


class ReportUiTests(unittest.TestCase):
    def setUp(self):
        self.e = load_engine()
        self.window = self.e.compute_window("previous_month", REFERENCE)
        self.raw = fixture(self.e, "previous_month")
        self.snapshot = self.e.finish_snapshot(self.raw, self.window, REFERENCE, "SIMULATED")

    def test_html_render_roundtrip_csp_and_required_sections(self):
        html = self.e.render_html(self.snapshot)
        self.assertLessEqual(len(html.encode("utf-8")), 4_800_000)
        parser = StructureParser()
        parser.feed(html)
        self.assertIsNotNone(parser.meta_csp)
        self.assertIn("default-src 'none'", parser.meta_csp)
        self.assertIn("connect-src 'none'", parser.meta_csp)
        for required_id in (
            "topbar",
            "sec-executive",
            "sec-filters",
            "sec-incidents",
            "sec-anomalies",
            "sec-actions",
            "sec-resources",
            "sec-coverage",
            "filter-category",
            "filter-severity",
            "filter-horizon",
            "filter-search",
            "incidents-table",
            "anomalies-table",
            "actions-table",
            "resources-table",
            "advisor-table",
            "sources-table",
            "theme-toggle",
            "btn-export-json",
            "btn-export-incidents-csv",
            "btn-export-actions-csv",
            "btn-print",
            "report-data",
        ):
            self.assertIn(required_id, parser.ids)
        embedded = html.split('<script type="application/json" id="report-data">', 1)[1].split("</script>", 1)[0]
        self.assertEqual(json.loads(embedded), self.snapshot)

    def test_html_escapes_script_injection_in_embedded_json(self):
        poisoned = copy.deepcopy(self.snapshot)
        poisoned["client"]["name"] = "</script><script>alert('xss')</script>&<>"
        html = self.e.render_html(poisoned)
        self.assertNotIn("</script><script>", html)
        embedded = html.split('<script type="application/json" id="report-data">', 1)[1].split("</script>", 1)[0]
        self.assertEqual(json.loads(embedded), poisoned)

    def test_swiss_architectural_palette_tokens_present(self):
        template = (ROOT / "report_template.html").read_text(encoding="utf-8")
        self.assertIn("--brand-orange: #FF4E00", template)
        self.assertIn("--brand-orange-text: #C23800", template)
        self.assertIn("--slate-topbar: #141B24", template)
        self.assertIn("--bg-page: #F6F5F2", template)

    def test_browser_interaction_filters_dark_mode_and_responsive_viewports(self):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            self.skipTest("Playwright not installed")
        html = self.e.render_html(self.snapshot)
        with sync_playwright() as p:
            launch_kwargs = {"headless": True}
            if sys.platform == "win32":
                launch_kwargs["channel"] = "msedge"
            browser = p.chromium.launch(**launch_kwargs)
            try:
                page = browser.new_page(viewport={"width": 1440, "height": 900})
                errors = []
                page.on("pageerror", lambda exc: errors.append(str(exc)))
                page.set_content(html, wait_until="load")
                self.assertEqual(errors, [])
                self.assertEqual(page.locator("#client-name-label").inner_text(), "Customer")

                total_incidents = int(page.locator("#incidents-count").inner_text())
                total_anomalies = int(page.locator("#anomalies-count").inner_text())
                total_actions = int(page.locator("#actions-count").inner_text())
                self.assertEqual(total_incidents, 3)
                self.assertGreaterEqual(total_anomalies, 5)
                self.assertGreaterEqual(total_actions, 7)

                # Filter by extension_failure category
                page.select_option("#filter-category", "extension_failure")
                self.assertEqual(int(page.locator("#incidents-count").inner_text()), 0)
                self.assertEqual(int(page.locator("#anomalies-count").inner_text()), 2)

                # Reset filters
                page.click("#filter-reset")
                self.assertEqual(int(page.locator("#incidents-count").inner_text()), total_incidents)
                self.assertEqual(int(page.locator("#anomalies-count").inner_text()), total_anomalies)

                # Filter by search query
                page.fill("#filter-search", "MDE.Windows")
                self.assertGreaterEqual(int(page.locator("#anomalies-count").inner_text()), 1)
                page.click("#filter-reset")

                # Filter by horizon
                page.select_option("#filter-horizon", "immediate_24h")
                imm_actions = int(page.locator("#actions-count").inner_text())
                self.assertGreaterEqual(imm_actions, 1)
                self.assertLess(imm_actions, total_actions)
                page.click("#filter-reset")

                # Toggle dark mode
                page.click("#theme-toggle")
                self.assertEqual(page.locator("html").get_attribute("data-theme"), "dark")

                # Responsive viewports (1440px, 390px, 320px) and zero horizontal overflow
                for width in (1440, 390, 320):
                    page.set_viewport_size({"width": width, "height": 844})
                    self.assertTrue(page.locator("#cover-title").is_visible())
                    overflow = page.evaluate("document.documentElement.scrollWidth > document.documentElement.clientWidth")
                    self.assertFalse(overflow)

                self.assertEqual(errors, [])
            finally:
                browser.close()


if __name__ == "__main__":
    unittest.main()
