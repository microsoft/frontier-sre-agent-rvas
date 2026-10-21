from datetime import date
from lifecycle import aks_support_plan, lifecycle_status, load_evidence
from unittest.mock import mock_open, patch
import os


TODAY = date(2026, 10, 21)


def snapshot(plan="standard", end="2026-11-01"):
    return {"schema_version": 1, "checked_at": "2026-10-21", "entries": [{
        "service": "aks", "version": "1.34", "support_plan": plan, "support_end": end,
        "source": "https://learn.microsoft.com/en-us/azure/aks/supported-kubernetes-versions",
    }]}


def test_no_current_evidence_is_unknown():
    assert lifecycle_status("aks", "1.99", "standard", {}, TODAY)["status"] == "Unknown"


def test_supported_and_expired_dates():
    assert lifecycle_status("aks", "1.34", "standard", snapshot(), TODAY)["status"] == "Supported"
    assert lifecycle_status("aks", "1.34", "standard", snapshot(end="2026-10-20"), TODAY)["status"] == "Unsupported"


def test_stale_future_or_malformed_metadata_is_unknown():
    for checked in ("2026-09-01", "2026-10-22", "bad"):
        data = snapshot()
        data["checked_at"] = checked
        assert lifecycle_status("aks", "1.34", "standard", data, TODAY)["status"] == "Unknown"


def test_lts_cannot_pass_standard_plan():
    assert lifecycle_status("aks", "1.34", "standard", snapshot("lts"), TODAY)["status"] == "Unknown"
    assert aks_support_plan({"supportPlan": "AKSLongTermSupport"}, {"tier": "Standard"}) is None
    assert aks_support_plan({"supportPlan": "AKSLongTermSupport"}, {"tier": "Premium"}) == "lts"


def test_missing_dates_and_untrusted_sources_are_unknown():
    for field in ("support_end", "source"):
        data = snapshot()
        del data["entries"][0][field]
        assert lifecycle_status("aks", "1.34", "standard", data, TODAY)["status"] == "Unknown"
    data = snapshot()
    data["entries"][0]["source"] = "https://microsoft.com.attacker.invalid/lifecycle"
    assert lifecycle_status("aks", "1.34", "standard", data, TODAY)["status"] == "Unknown"


def test_unknown_version_cannot_match_prefix():
    assert lifecycle_status("aks", "1.340", "standard", snapshot(), TODAY)["status"] == "Unknown"


def test_unconfigured_evidence_has_distinct_diagnostic():
    with patch.dict(os.environ, {}, clear=True):
        assert load_evidence() is None
        result = lifecycle_status("aks", "1.34", "standard", today=TODAY)
    assert result["status"] == "Unknown"
    assert result["evidence_error"] == "SnapshotUnconfigured"
    assert "not configured" in result["reason"]


def test_malformed_configured_json_preserves_reason_without_file_contents():
    with patch.dict(os.environ, {"SRE_LIFECYCLE_EVIDENCE": "configured.json"}), patch("builtins.open", mock_open(read_data="{sensitive-invalid-content")):
        diagnostic = load_evidence()
        result = lifecycle_status("aks", "1.34", "standard", today=TODAY)
    assert diagnostic["_evidence_error"]["code"] == "SnapshotMalformed"
    assert result["status"] == "Unknown"
    assert result["evidence_error"] == "SnapshotMalformed"
    assert "not valid UTF-8 JSON" in result["reason"]
    assert "sensitive" not in result["reason"]


def test_missing_and_unreadable_snapshots_are_distinct_from_unconfigured():
    for error, code in ((FileNotFoundError("private-file-name"), "SnapshotNotFound"), (PermissionError("private-file-name"), "SnapshotUnreadable")):
        with patch.dict(os.environ, {"SRE_LIFECYCLE_EVIDENCE": "configured.json"}), patch("builtins.open", side_effect=error):
            result = lifecycle_status("aks", "1.34", "standard", today=TODAY)
        assert result["status"] == "Unknown"
        assert result["evidence_error"] == code
        assert "private-file-name" not in result["reason"]


def test_invalid_schema_and_stale_evidence_keep_explicit_reasons():
    data = snapshot()
    data["schema_version"] = 2
    assert lifecycle_status("aks", "1.34", "standard", data, TODAY)["evidence_error"] == "SnapshotSchemaUnsupported"
    data = snapshot()
    data["checked_at"] = "2026-09-01"
    assert lifecycle_status("aks", "1.34", "standard", data, TODAY)["evidence_error"] == "SnapshotStale"


def test_valid_json_with_invalid_structure_is_not_assessed():
    for contents in ("[]", "null", "123", '"not-an-object"'):
        with patch.dict(os.environ, {"SRE_LIFECYCLE_EVIDENCE": "configured.json"}), patch("builtins.open", mock_open(read_data=contents)):
            result = lifecycle_status("aks", "1.34", "standard", today=TODAY)
        assert result["evidence_error"] == "SnapshotInvalid"


def test_invalid_encoding_is_reported_without_exception_contents():
    error = UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid byte")
    with patch.dict(os.environ, {"SRE_LIFECYCLE_EVIDENCE": "configured.json"}), patch("builtins.open", side_effect=error):
        result = lifecycle_status("aks", "1.34", "standard", today=TODAY)
    assert result["status"] == "Unknown"
    assert result["evidence_error"] == "SnapshotMalformed"


def test_invalid_source_type_does_not_escape_unknown_assessment():
    data = snapshot()
    data["entries"][0]["source"] = 123
    result = lifecycle_status("aks", "1.34", "standard", data, TODAY)
    assert result["status"] == "Unknown"
    assert result["evidence_error"] == "SnapshotSourceInvalid"
