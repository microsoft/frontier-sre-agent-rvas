"""Unit tests for the pure helpers in expiry_scan (no Azure calls)."""

from datetime import datetime, timezone, timedelta

import expiry_scan as es
import sys
from types import SimpleNamespace
from unittest.mock import Mock

NOW = datetime(2026, 7, 9, tzinfo=timezone.utc)


def test_days_to_expiry():
    assert es.days_to_expiry(NOW + timedelta(days=10), NOW) == 10
    assert es.days_to_expiry(NOW - timedelta(days=2), NOW) == -2
    assert es.days_to_expiry(None, NOW) is None


def test_severity_for_days():
    assert es.severity_for_days(-1) == "Critical"
    assert es.severity_for_days(10) == "High"
    assert es.severity_for_days(20) == "Medium"
    assert es.severity_for_days(45) == "Low"


def test_time_bucket():
    assert es.time_bucket(-1) == "Expired"
    assert es.time_bucket(7) == "Within 14 days"
    assert es.time_bucket(20) == "15 to 30 days"
    assert es.time_bucket(45) == "31 days to horizon"


def test_classify_item_within_and_outside_horizon():
    inside = {"name": "c1", "kind": "Key Vault certificate", "source": "v1", "subscription": "a", "expiry": NOW + timedelta(days=5)}
    finding = es.classify_item(inside, NOW, 60)
    assert finding["severity"] == "High"
    assert finding["days_left"] == 5
    outside = {"name": "c2", "kind": "cert", "source": "v1", "subscription": "a", "expiry": NOW + timedelta(days=200)}
    assert es.classify_item(outside, NOW, 60) is None


def test_build_report_data_sorted_soonest_first():
    items = [
        {"name": "later", "kind": "Key Vault certificate", "source": "v", "subscription": "a", "expiry": NOW + timedelta(days=20)},
        {"name": "expired", "kind": "Key Vault secret", "source": "v", "subscription": "a", "expiry": NOW - timedelta(days=1)},
    ]
    data = es.build_report_data(items, 60, 1, [], now=NOW)
    assert data["findings"]["rows"][0]["item"] == "expired"  # soonest first
    assert data["summary_cards"][1]["value"] == "1"  # one expired


def test_missing_expiry_is_explicit_and_disabled_is_distinct():
    data = es.build_report_data([
        {"name": "unknown", "expiry": None},
        {"name": "disabled", "expiry": NOW - timedelta(days=2), "enabled": False},
    ], 60, 1, [], now=NOW)
    assert data["assessment_status"] == "Partial"
    assert data["summary_cards"][1]["value"] == "0"
    assert data["summary_cards"][4]["value"] == "1"
    assert data["findings"]["rows"][0]["state"] == "Disabled"
    assert data["findings"]["rows"][0]["severity"] == "Low"
    assert data["findings"]["rows"][1]["days_left"] is None


def test_directory_enumeration_requires_separate_consent(monkeypatch):
    monkeypatch.setattr(es, "_run_graph", lambda *args: [])
    credential = SimpleNamespace(get_token=Mock(side_effect=AssertionError("No Graph token without consent")))
    items, notes = es._collect({}, credential)
    assert items == []
    credential.get_token.assert_not_called()
    assert any("consent" in note for note in notes)
    assert es.build_report_data([], 60, 0, notes)["assessment_status"] == "Not assessed"


def test_vault_collection_reads_metadata_and_retains_missing_expiry(monkeypatch):
    monkeypatch.setattr(es, "_run_graph", lambda headers, query: [{"name": "vault", "vaultUri": "https://example.vault.azure.net", "subscriptionId": "a"}] if "vaults" in query else [])
    urls = []
    def read(token, url):
        urls.append(url)
        return [{"id": url + "/item", "attributes": {"enabled": False}}]
    monkeypatch.setattr(es, "_read_vault_list", read)
    credential = SimpleNamespace(get_token=lambda scope: SimpleNamespace(token="test"))
    items, notes = es._collect({}, credential)
    assert len(items) == 2
    assert all(item["expiry"] is None and item["enabled"] is False for item in items)
    assert all(url.endswith(("/certificates", "/secrets")) for url in urls)


def test_graph_application_ids_do_not_enumerate_directory(monkeypatch):
    app_id = "12345678-1234-1234-1234-123456789012"
    monkeypatch.setattr(es, "_run_graph", lambda *args: [])
    calls = []
    def get(url, **kwargs):
        calls.append(url)
        body = {"id": app_id, "displayName": "app", "passwordCredentials": [{"keyId": "key", "endDateTime": None, "secretText": "must-not-retain"}]}
        return SimpleNamespace(raise_for_status=lambda: None, json=lambda: body, status_code=200, headers={}, close=lambda: None)
    monkeypatch.setitem(sys.modules, "requests", SimpleNamespace(get=get))
    credential = SimpleNamespace(get_token=lambda scope: SimpleNamespace(token="test"))
    items, notes = es._collect({}, credential, [app_id])
    assert len(calls) == 1 and f"/applications/{app_id}?" in calls[0]
    assert items[0]["id"] == app_id + "/key"
    assert "secretText" not in str(items) and "must-not-retain" not in str(items)


def test_graph_page_cap_is_explicitly_incomplete(monkeypatch):
    monkeypatch.setattr(es, "_run_graph", lambda *args: [])
    response = SimpleNamespace(raise_for_status=lambda: None, json=lambda: {"value": [], "@odata.nextLink": es.GRAPH_ENDPOINT + "/v1.0/applications?$skiptoken=more"}, status_code=200, headers={}, close=lambda: None)
    get = Mock(return_value=response)
    monkeypatch.setitem(sys.modules, "requests", SimpleNamespace(get=get))
    credential = SimpleNamespace(get_token=lambda scope: SimpleNamespace(token="test"))
    items, notes = es._collect({}, credential, allow_tenant_directory=True)
    assert get.call_count == 40
    assert any("incomplete" in note for note in notes)


def test_vault_list_continuation_cannot_fetch_a_secret_value(monkeypatch):
    import pytest

    response = SimpleNamespace(raise_for_status=lambda: None, json=lambda: {"value": [], "nextLink": "https://example.vault.azure.net/secrets/item/version?api-version=7.4"}, status_code=200, headers={}, close=lambda: None)
    get = Mock(return_value=response)
    monkeypatch.setitem(sys.modules, "requests", SimpleNamespace(get=get))
    with pytest.raises(ValueError, match="metadata collection"):
        es._read_vault_list("test", "https://example.vault.azure.net/secrets")
    assert get.call_count == 1


def test_unparseable_or_timezone_unknown_expiry_stays_unknown():
    assert es._from_iso("not-a-date") is None
    assert es._from_iso("2026-10-21") is None
    assert es._from_unix("not-a-timestamp") is None


if __name__ == "__main__":
    for name, function in sorted(globals().items()):
        if name.startswith("test_") and callable(function):
            function()
            print(f"ok {name}")
    print("all expiry_scan tests passed")
