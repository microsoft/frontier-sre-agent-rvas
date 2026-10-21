"""Unit tests for the pure render helpers in postmortem_render (no file or network)."""

import postmortem_render as pm

SAMPLE = {
    "title": "Checkout latency",
    "severity": "Sev2",
    "status": "Resolved",
    "summary": "Checkout slowed for 40 minutes.",
    "impact": {"duration": "40 minutes", "scope": "Checkout API", "customer": "Timeouts for some users"},
    "timeline": [{"time": "10:02 UTC", "event": "Config change deployed"}],
    "root_cause": "Pool too small (trigger); no guardrail (weakness).",
    "contributing_factors": ["No saturation alert"],
    "detection": "Latency alert fired.",
    "resolution": "Rolled back the change.",
    "lessons": {"went_well": ["Alert caught it"], "went_wrong": ["No guardrail"], "got_lucky": ["Low traffic"]},
    "action_items": [{"action": "Add saturation alert", "owner": "Platform", "due": "2026-07-23", "type": "Detect"}],
}


def test_render_includes_all_sections():
    doc = pm.render_html(SAMPLE)
    for text in ["Checkout latency", "Summary", "Impact", "Timeline", "Root cause", "Contributing factors", "Detection", "Resolution", "Lessons", "Action items"]:
        assert text in doc, f"missing section: {text}"


def test_render_is_blameless_callout_present():
    doc = pm.render_html(SAMPLE)
    assert "blameless review" in doc
    assert "Add saturation alert" in doc
    assert "Detect" in doc


def test_render_handles_sparse_input():
    doc = pm.render_html({"title": "Minimal"})
    assert "Minimal" in doc
    assert "Summary" not in doc  # omitted when empty


def test_action_item_type_colour():
    doc = pm.render_html(SAMPLE)
    assert pm.ACTION_CLASS["Detect"] in doc
    assert "Detect" in doc


def test_draft_is_sanitized_and_never_claims_external_send():
    data = {**SAMPLE, "summary": "Contact owner@example.com for /subscriptions/11111111-1111-1111-1111-111111111111/resourceGroups/rg.",
            "password": "test-secret-value"}
    doc = pm.render_html(data)
    assert "owner@example.com" not in doc
    assert "11111111-1111" not in doc
    assert "test-secret-value" not in doc
    assert "Draft: human review required" in doc
    assert "No external send is performed" in doc
    assert "owner@example.com" in pm.render_html(data, include_identifiers=True)


def test_plain_text_is_escaped_and_unknown_assessment_is_visible():
    doc = pm.render_html({"title": "<script>alert(1)</script>"})
    assert "<script>alert(1)</script>" not in doc
    assert "&lt;script&gt;" in doc
    assert "Not assessed" in doc


def test_failed_evidence_cannot_be_marked_complete():
    data = {**SAMPLE, "assessment_status": "Complete", "collection_errors": ["Activity Log denied"],
            "sources": [{"title": "Incident evidence", "url": "https://example.com/incident"}]}
    doc = pm.render_html(data)
    assert "Partial" in doc and "Activity Log denied" in doc and "Sources" in doc
    assert pm._reviewed_input({"assessment_status": "Complete"})["assessment_status"] == "Partial"


if __name__ == "__main__":
    for name, function in sorted(globals().items()):
        if name.startswith("test_") and callable(function):
            function()
            print(f"ok {name}")
    print("all postmortem_render tests passed")
