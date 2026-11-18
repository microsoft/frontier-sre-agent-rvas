"""Private replay harness tested with synthetic receipts only."""

import copy
import unittest
from urllib.parse import parse_qs, urlsplit

from private_replay import replay
from support import CONFIG, FakeReader, REFERENCE, tool


class PrivateReplayHarnessTests(unittest.TestCase):
    def test_replay_is_explicit_provenance_and_missing_receipts_not_empty(self):
        reader = FakeReader()
        raw = copy.deepcopy(reader.responses[reader.event_url]["payload"])
        raw.pop("nextLink")
        original_url = reader.event_url
        query = {key: values[0] for key, values in parse_qs(urlsplit(original_url).query).items()}
        receipt = {
            "method": "GET", "path": urlsplit(original_url).path, "parameters": query, "http": 200,
            "requested_utc": tool.iso(REFERENCE), "completed_utc": tool.iso(REFERENCE),
            "first_page_only": True, "body": raw,
        }
        document = {
            "reference_utc": tool.iso(REFERENCE), "subscription_id": CONFIG["subscription_id"],
            "identity": {"tid": CONFIG["tenant_id"]},
            "first_page_probe_not_complete_collection": True, "sources": [receipt],
        }
        snapshot, summary = replay(document)
        self.assertEqual(snapshot["provenance"], "PRIVATE_REPLAY")
        self.assertFalse(summary["fresh_live_validation"])
        self.assertFalse(snapshot["replay_context"]["identity_reauthenticated"])
        self.assertEqual(summary["in_scope_events"], 4)
        self.assertEqual(summary["excluded_category_records"], 1)
        self.assertEqual(summary["uncollected_resource_sources"], 4)
        self.assertTrue(summary["all_in_scope_record_field_parity"])
        self.assertEqual([source["status"] for source in snapshot["sources"][1:]], ["not_collected"] * 4)
        self.assertNotIn("EXCLUDED_ADVISORY_BODY", tool.json_text(snapshot))


if __name__ == "__main__":
    unittest.main()
