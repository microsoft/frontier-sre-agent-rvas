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
        self.raw = fixture(self.e)
        self.snapshot = self.e.finish_snapshot(self.raw, REFERENCE, "SIMULATED", "LAB")

    def test_html_render_roundtrip_csp_and_required_sections(self):
        html = self.e.render_html(self.snapshot)
        self.assertLessEqual(len(html.encode("utf-8")), 4_800_000)
        parser = StructureParser()
        parser.feed(html)
        self.assertIsNotNone(parser.meta_csp)
        self.assertIn("default-src 'none'", parser.meta_csp)
        self.assertIn("connect-src 'none'", parser.meta_csp)
        for required_id in (
            "sec-cover",
            "sec-executive",
            "sec-dependencies",
            "sec-inventory",
            "sec-findings",
            "sec-finops",
            "sec-actions",
            "sec-sources",
            "tab-dep-observed",
            "tab-dep-reference",
            "panel-dep-observed",
            "panel-dep-reference",
            "dep-layer-filter",
            "dep-class-filter",
            "dep-edges-table",
            "dep-nodes-table",
            "dep-broken-table",
            "dep-unknowns-table",
            "report-data",
        ):
            self.assertIn(required_id, parser.ids)
        embedded = html.split('<script type="application/json" id="report-data">', 1)[1].split("</script>", 1)[0]
        self.assertEqual(json.loads(embedded), self.snapshot)

    def test_html_escapes_script_injection_in_embedded_json(self):
        poisoned = copy.deepcopy(self.snapshot)
        poisoned["workspace"]["name"] = "</script><script>alert('xss')</script>&<>"
        html = self.e.render_html(poisoned)
        self.assertNotIn("</script><script>", html)
        embedded = html.split('<script type="application/json" id="report-data">', 1)[1].split("</script>", 1)[0]
        self.assertEqual(json.loads(embedded), poisoned)

    def test_brand_palette_tokens_present(self):
        template = (ROOT / "report_template.html").read_text(encoding="utf-8")
        self.assertIn("--brand-navy: #003865", template)
        self.assertIn("--brand-lava: #ff3621", template)
        self.assertIn("--brand-steel: #0066a1", template)
        self.assertIn("--brand-teal: #00875a", template)

    def test_browser_interaction_dependency_filters_tabs_and_multi_workspace(self):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            self.skipTest("Playwright not installed")
        html = self.e.render_html(self.snapshot)
        second_id = self.snapshot["workspace"]["id"].replace(self.snapshot["workspace"]["name"], "dbx-dr-02")
        multi = self.e.multi_snapshot(
            [
                {
                    "workspace_id": self.snapshot["workspace"]["id"],
                    "workspace_name": self.snapshot["workspace"]["name"],
                    "reference_utc": REFERENCE,
                    "snapshot": self.snapshot,
                    "error": None,
                    "status": "ok",
                },
                {
                    "workspace_id": second_id,
                    "workspace_name": "dbx-dr-02",
                    "reference_utc": REFERENCE,
                    "snapshot": None,
                    "error": {"code": "access_denied", "message": "HTTP 403", "source_id": "arm_workspace", "http_status": 403},
                    "status": "error",
                },
            ],
            REFERENCE,
            [],
        )
        multi_html = self.e.render_html(multi)
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
                self.assertEqual(page.locator("#client-name-label").inner_text(), "CLIENTE")
                total_edges = int(page.locator("#dep-edges-count").inner_text())
                self.assertGreater(total_edges, 15)

                page.select_option("#dep-class-filter", "INFERRED")
                inferred_edges = int(page.locator("#dep-edges-count").inner_text())
                self.assertGreaterEqual(inferred_edges, 2)
                self.assertLess(inferred_edges, total_edges)

                page.select_option("#dep-class-filter", "OBSERVED")
                observed_edges = int(page.locator("#dep-edges-count").inner_text())
                self.assertEqual(observed_edges + inferred_edges, total_edges)

                page.click("#tab-dep-reference")
                self.assertFalse(page.locator("#panel-dep-reference").is_hidden())
                self.assertTrue(page.locator("#panel-dep-observed").is_hidden())

                page.click("#theme-toggle")
                self.assertEqual(page.locator("html").get_attribute("data-theme"), "dark")

                for width in (390, 320):
                    page.set_viewport_size({"width": width, "height": 844})
                    self.assertTrue(page.locator("#cover-title").is_visible())

                page.set_content(multi_html, wait_until="load")
                self.assertFalse(page.locator("#workspace-selector-wrap").is_hidden())
                page.select_option("#workspace-selector", "1")
                self.assertFalse(page.locator("#workspace-error-view").is_hidden())
                self.assertTrue(page.locator("#report-body").is_hidden())
                self.assertEqual(errors, [])
            finally:
                browser.close()


if __name__ == "__main__":
    unittest.main()
