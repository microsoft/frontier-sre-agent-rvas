"""Opt-in, local-file-only Playwright checks. No Azure calls or live evidence."""

import base64
import csv
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from support import ATTACK, BIG_INTEGER, FakeReader, csv_records, empty_snapshot, large_retained_snapshot, snapshot, tool


@unittest.skipUnless(os.environ.get("CASE05_BROWSER_TESTS") == "1", "Set CASE05_BROWSER_TESTS=1 for the installed local browser.")
class OfflineReportUITests(unittest.TestCase):
    def test_large_retained_all_record_exports_match_complete_python_evidence(self):
        document = large_retained_snapshot()
        document["events"][0]["title"] += " \U0001f30d \u00e9 \" \\"
        raw = tool.source_record(document, document["events"][0]["source_ref"])
        raw["properties"]["unknownFutureField"]["numeric_lexemes"] = {
            "large_integer": -BIG_INTEGER, "integral_float": 1.0, "tiny_float": 1.0e-150,
            "negative_zero": -0.0, "text": "\U0001f30d } [ \" \\\\ \n",
            "prototype_key": {"__proto__": {"unknown_integer": BIG_INTEGER}},
        }
        self.assert_complete_retained_exports(document)

    @unittest.skipUnless(os.environ.get("CASE05_PRIVATE_SNAPSHOT"), "Private full-model replay is explicit opt-in.")
    def test_opt_in_private_full_model_exports_keep_record_field_and_byte_parity(self):
        from private_replay import worst_case_test_logo
        document = tool.decode_json(Path(os.environ["CASE05_PRIVATE_SNAPSHOT"]).read_bytes())
        self.assertEqual(document["schema_version"], "service-health-events-v1")
        self.assertEqual(document["source_query"]["lookback_days"], 365)
        with patch.object(tool, "COMPANY_LOGO_DATA_URI", worst_case_test_logo()):
            self.assert_complete_retained_exports(document)

    def assert_complete_retained_exports(self, document):
        from playwright.sync_api import sync_playwright
        files = tool.prepare_artifacts(document, tool.logo_markup())
        with tempfile.TemporaryDirectory() as temporary, sync_playwright() as playwright:
            report = Path(temporary) / "retained-review.html"
            report.write_bytes(files["report_path"])
            channel = os.environ.get("CASE05_BROWSER_CHANNEL", "msedge" if os.name == "nt" else "")
            browser = playwright.chromium.launch(headless=True, **({"channel": channel} if channel else {}))
            context = browser.new_context(viewport={"width": 1440, "height": 1000}, accept_downloads=True)
            requests, errors = [], []
            context.on("request", lambda request: requests.append(request.url))
            page = context.new_page()
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(report.as_uri(), wait_until="load")
            self.assertTrue(page.locator("#render-error").is_hidden())
            with page.expect_download() as expected:
                page.locator("#full-json").click()
            self.assertEqual(Path(expected.value.path()).read_bytes(), files["snapshot_path"])
            with page.expect_download() as expected:
                page.locator("#filtered-json").click()
            filtered_bytes = Path(expected.value.path()).read_bytes()
            exported = json.loads(filtered_bytes)
            expected_events = {
                row["event_key"]: tool.complete_event(document, row) for row in document["events"]
            }
            expected_resources = {
                row["resource_key"]: tool.complete_resource(document, row) for row in document["impacted_resources"]
            }
            self.assertEqual({row["event_key"]: row for row in exported["events"]}, expected_events)
            self.assertEqual({row["resource_key"]: row for row in exported["impacted_resources"]}, expected_resources)
            for row in (*expected_events.values(), *expected_resources.values()):
                self.assertIn(tool.json_text(row).encode("utf-8"), filtered_bytes)
            expected_receipts = {}
            for source in document["sources"]:
                receipt = {key: value for key, value in source.items() if key != "pages"}
                receipt["pages"] = [{
                    **{key: value for key, value in page.items() if key != "response"},
                    "response_metadata": {key: value for key, value in page["response"].items() if key != "value"}
                    if isinstance(page.get("response"), dict) else page.get("response"),
                } for page in source["pages"]]
                expected_receipts[source["source_id"]] = receipt
                self.assertIn(tool.json_text(receipt).encode("utf-8"), filtered_bytes)
            self.assertEqual({row["source_id"]: row for row in exported["source_receipts"]}, expected_receipts)
            for identifier, key, path in (("events-csv", "event_key", "events_csv_path"), ("resources-csv", "resource_key", "resources_csv_path")):
                with page.expect_download() as expected:
                    page.locator("#" + identifier).click()
                actual_rows = csv_records(Path(expected.value.path()).read_text(encoding="utf-8-sig"))
                expected_rows = csv_records(files[path].decode("utf-8-sig"))
                self.assertEqual({row[key]: row for row in actual_rows}, {row[key]: row for row in expected_rows})
            page.locator('[data-scope="requested_updates"]').click()
            self.assertIn(str(sum(row["temporal"]["requested_updates"] for row in document["events"])) + " matching", page.locator("#results").inner_text())
            self.assertFalse([url for url in requests if url.startswith(("http:", "https:"))])
            self.assertEqual(errors, [])
            browser.close()

    def test_invalid_utf8_reference_is_an_explicit_render_error_not_empty_success(self):
        import re
        from playwright.sync_api import sync_playwright
        document = snapshot()
        markup = tool.prepare_artifacts(document, tool.logo_markup())["report_path"].decode("utf-8")
        match = re.search(r'<script id="report-model" type="application/json">(.*?)</script>', markup, re.S)
        model = json.loads(match[1])
        model["events"][0]["source_record_range"] = [-1, 4]
        markup = markup[:match.start(1)] + tool.safe_script_json(model) + markup[match.end(1):]
        with tempfile.TemporaryDirectory() as temporary, sync_playwright() as playwright:
            file = Path(temporary) / "SIMULATED-invalid-reference.html"
            file.write_text(markup, encoding="utf-8")
            channel = os.environ.get("CASE05_BROWSER_CHANNEL", "msedge" if os.name == "nt" else "")
            browser = playwright.chromium.launch(headless=True, **({"channel": channel} if channel else {}))
            page = browser.new_page()
            page.goto(file.as_uri(), wait_until="load")
            self.assertTrue(page.locator("#render-error").is_visible())
            self.assertIn("Do not interpret this as an empty source", page.locator("#render-error").inner_text())
            self.assertFalse(page.locator("#filtered-json").get_attribute("href"))
            browser.close()

    def test_desktop_mobile_exports_filters_detail_and_empty_in_one_bounded_pass(self):
        from playwright.sync_api import sync_playwright
        document = snapshot(FakeReader(extra_events=60))
        files = tool.prepare_artifacts(document, tool.logo_markup())
        source_snapshot = files["snapshot_path"]
        artifact_root = Path(os.environ["CASE05_UI_ARTIFACTS"]) if os.environ.get("CASE05_UI_ARTIFACTS") else None
        if artifact_root is not None:
            artifact_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory() as temporary, sync_playwright() as playwright:
            root = Path(temporary)
            report = root / "SIMULATED-service-health.html"
            report.write_bytes(files["report_path"])
            channel = os.environ.get("CASE05_BROWSER_CHANNEL", "msedge" if os.name == "nt" else "")
            browser = playwright.chromium.launch(headless=True, **({"channel": channel} if channel else {}))
            context = browser.new_context(viewport={"width": 1440, "height": 1000}, accept_downloads=True, reduced_motion="reduce")
            requests, errors = [], []
            context.on("request", lambda request: requests.append(request.url))
            page = context.new_page()
            def capture(name):
                if artifact_root is not None:
                    page.screenshot(path=str(artifact_root / name), full_page=False)
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)
            page.goto(report.as_uri(), wait_until="load")
            self.assertTrue(page.locator("#render-error").is_hidden())
            self.assertEqual(page.locator("#provenance").inner_text(), "SIMULATED")
            self.assertIn("65 matching", page.locator("#results").inner_text())
            self.assertEqual(page.locator("#event-rows tr").count(), 25)
            self.assertIsNone(page.evaluate("window.SOURCE_EXECUTED"))
            self.assertFalse(page.locator("img").count())
            self.assertIn("partial", page.locator("#coverage-tag").inner_text().lower())
            capture("SIMULATED-desktop.png")

            with page.expect_download() as expected:
                page.locator("#full-json").click()
            complete = Path(expected.value.path()).read_bytes()
            self.assertEqual(complete, source_snapshot)
            self.assertEqual(json.loads(complete)["sources"][0]["pages"][0]["response"]["providerExtension"]["complete_extra_field"], BIG_INTEGER)
            full_href = page.locator("#full-json").get_attribute("href")
            self.assertEqual(base64.b64decode(full_href.split(",", 1)[1]), source_snapshot)

            with page.expect_download() as expected:
                page.locator("#events-csv").click()
            rows = list(csv.DictReader(io.StringIO(Path(expected.value.path()).read_text(encoding="utf-8-sig"))))
            self.assertEqual(len(rows), 65)
            self.assertTrue(all(row["provenance"] == "SIMULATED" for row in rows))
            self.assertTrue(all(row["subscription_id"] == document["subscription_id"] for row in rows))
            page.locator("#show-more").click()
            self.assertEqual(page.locator("#event-rows tr").count(), 50)
            page.locator(".event-open").nth(40).click()
            self.assertEqual(page.evaluate("document.activeElement.id"), "event-detail")
            self.assertTrue(page.locator("#event-detail h3").evaluate("(node) => node.getBoundingClientRect().top >= 0 && node.getBoundingClientRect().bottom < innerHeight"))
            capture("SIMULATED-desktop-selection.png")

            page.locator('[data-scope="future_maintenance"]').click()
            self.assertIn("1 matching", page.locator("#results").inner_text())
            self.assertEqual(page.locator("#event-rows tr").count(), 1)
            self.assertIn("SIM-MAINT-004", page.locator("#event-detail").inner_text())
            self.assertIn("No targetResourceId supplied", page.locator("#event-detail").inner_text())
            with page.expect_download() as expected:
                page.locator("#filtered-json").click()
            filtered_bytes = Path(expected.value.path()).read_bytes()
            filtered = json.loads(filtered_bytes)
            self.assertEqual(len(filtered["events"]), 1)
            self.assertEqual(len(filtered["impacted_resources"]), 2)
            self.assertEqual(filtered["events"][0]["source_record"]["properties"]["unknownFutureField"]["large_integer"], BIG_INTEGER)
            self.assertEqual(filtered["impacted_resources"][1]["source_record"]["properties"]["info"][1]["value"], BIG_INTEGER)
            self.assertEqual(filtered["source_receipts"][0]["pages"][0]["response_metadata"]["providerExtension"]["complete_extra_field"], BIG_INTEGER)
            with page.expect_download() as expected:
                page.locator("#resources-csv").click()
            resource_rows = list(csv.DictReader(io.StringIO(Path(expected.value.path()).read_text(encoding="utf-8-sig"))))
            self.assertEqual(len(resource_rows), 2)
            self.assertEqual(json.loads(resource_rows[1]["details_json"])["source_record"]["properties"]["info"][1]["value"], BIG_INTEGER)
            self.assertEqual(page.locator("#full-json").get_attribute("href"), full_href)

            page.locator("#reset").click()
            page.locator("#event-type").select_option("ServiceIssue")
            page.locator("#state").select_option("Unknown")
            self.assertIn("1 matching", page.locator("#results").inner_text())
            self.assertIn(ATTACK, page.locator("#event-detail").inner_text())
            self.assertIsNone(page.evaluate("window.SOURCE_EXECUTED"))
            page.locator("#region").select_option("__unknown__")
            self.assertIn("1 matching", page.locator("#results").inner_text())
            page.locator("#search").fill("NO_MATCH_SYNTHETIC")
            self.assertIn("0 matching", page.locator("#results").inner_text())
            self.assertIn("No records match", page.locator("#event-rows").inner_text())
            page.locator("#reset").click()
            page.locator("#search").focus()
            page.keyboard.press("Tab")
            self.assertEqual(page.evaluate("document.activeElement.id"), "event-type")
            self.assertNotEqual(page.locator("#event-type").evaluate("(node) => getComputedStyle(node).outlineStyle"), "none")

            page.evaluate("window.print = () => { window.PRINT_REQUESTED = true; }")
            page.locator("#print-report").click()
            self.assertTrue(page.evaluate("window.PRINT_REQUESTED"))
            page.evaluate("window.dispatchEvent(new Event('beforeprint'))")
            self.assertEqual(page.locator("#event-rows tr").count(), 65)
            page.emulate_media(media="print")
            self.assertEqual(page.locator(".toolbar").evaluate("(node) => getComputedStyle(node).display"), "none")
            page.emulate_media(media="screen")
            page.evaluate("window.dispatchEvent(new Event('afterprint'))")
            self.assertEqual(page.locator("#event-rows tr").count(), 25)
            page.set_viewport_size({"width": 390, "height": 844})
            page.evaluate("window.scrollTo(0, 0)")
            self.assertTrue(page.evaluate("document.documentElement.scrollWidth <= innerWidth"))
            capture("SIMULATED-mobile.png")
            page.locator("#review").evaluate("(node) => node.scrollIntoView()")
            capture("SIMULATED-mobile-review.png")
            page.locator('[data-scope="future_maintenance"]').click()
            page.locator(".event-open").first.click()
            self.assertEqual(page.evaluate("document.activeElement.id"), "event-detail")
            self.assertTrue(page.evaluate("document.documentElement.scrollWidth <= innerWidth"))
            self.assertIn("SIM-MAINT-004", page.locator("#event-detail").inner_text())
            self.assertEqual(len(errors), 0, errors)
            self.assertFalse([url for url in requests if url.startswith(("http:", "https:"))], requests)

            empty = root / "SIMULATED-empty.html"
            empty.write_bytes(tool.prepare_artifacts(empty_snapshot(), tool.logo_markup())["report_path"])
            page.goto(empty.as_uri(), wait_until="load")
            self.assertIn("Successful-empty event reads", page.locator("#event-rows").inner_text())
            self.assertIn("source validation only", page.locator("#coverage-summary").inner_text())
            self.assertIn("No communication selected", page.locator("#event-detail").inner_text())
            self.assertEqual(page.locator("#source-entries > details").count(), 1)
            self.assertEqual(len(errors), 0, errors)
            browser.close()


if __name__ == "__main__":
    unittest.main()
