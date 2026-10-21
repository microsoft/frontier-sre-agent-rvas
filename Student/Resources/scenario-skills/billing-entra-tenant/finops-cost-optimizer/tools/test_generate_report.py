"""Pure renderer validation and destructive instruction regressions."""

import pytest
import generate_report as gr
from unittest.mock import Mock, mock_open


def test_requires_explicit_single_currency():
    with pytest.raises(ValueError, match="currency"):
        gr._validated_totals({})
    with pytest.raises(ValueError, match="currency"):
        gr._validated_totals({"totals": {"currency": "USD"}, "findings": [{"currency": "EUR"}]})


def test_reconciles_scope_baseline_and_requires_savings_evidence():
    data = {"totals": {"currency": "USD", "analyzed_spend": 100, "estimated_monthly_savings": 20}, "subscriptions": [{"cost": 100}]}
    assert gr._validated_totals(data) == ("USD", 100, None)
    data["totals"]["savings_reconciled"] = True
    data["reconciliation_notes"] = "Advisor deduplicated; reservation chosen instead of overlapping savings plan."
    assert gr._validated_totals(data) == ("USD", 100, 20)
    data["subscriptions"][0]["cost"] = 200
    with pytest.raises(ValueError, match="baseline"):
        gr._validated_totals(data)


def test_confidence_never_implies_deletion_permission_or_recreates_commands():
    html = gr._render_candidates([{"resource": "old-disk", "resource_id": "/subscriptions/a/providers/x/y/z", "confidence": 99}], "USD")
    assert "never permission to delete" in html
    assert "az resource delete" not in html
    assert "likely safe" not in html


def test_generated_export_uses_shared_sanitizer_without_disk_writes(monkeypatch):
    identity = "/subscriptions/12345678-1234-1234-1234-123456789012/resourceGroups/private-rg/providers/Microsoft.Compute/disks/private-disk"
    data = {
        "totals": {"currency": "USD", "analyzed_spend": 10},
        "subscriptions": [{"name": "Private Subscription", "cost": 10}],
        "candidates": [{"resource": "private-disk", "resource_id": identity, "next_step": identity, "confidence": 99}],
    }
    output = mock_open()
    monkeypatch.setattr(gr, "open", output, raising=False)
    monkeypatch.setattr(gr.os, "makedirs", Mock())
    monkeypatch.setattr(gr, "document_shell", lambda title, body, **kw: body)
    result = gr.main(data)
    rendered = output().write.call_args.args[0]
    assert identity not in rendered
    assert result["summary"]["estimated_monthly_savings"] is None
    assert result["assessment_status"] == "Partial"
    assert result["sources"]
