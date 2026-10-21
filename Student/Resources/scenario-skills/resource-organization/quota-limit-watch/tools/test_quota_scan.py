"""Unit tests for the pure helpers in quota_scan (no Azure calls)."""

import quota_scan as qs


def test_utilization():
    assert qs.utilization(80, 100) == 80.0
    assert qs.utilization(0, 0) is None
    assert qs.utilization(5, 0) is None


def test_band_thresholds():
    assert qs.band(96) == "Critical"
    assert qs.band(90) == "High"
    assert qs.band(85) == "Medium"
    assert qs.band(50) == "Low"


def test_classify_usage_flags_near_limit():
    item = {"name": {"localizedValue": "Total Regional vCPUs"}, "currentValue": 95, "limit": 100}
    finding = qs.classify_usage(item, "Sub A", "westeurope", 80)
    assert finding["severity"] == "Critical"
    assert finding["utilization"] == "95%"
    assert finding["_percent"] == 95.0


def test_classify_usage_ignores_below_threshold_and_no_limit():
    below = {"name": {"value": "x"}, "currentValue": 10, "limit": 100}
    assert qs.classify_usage(below, "Sub A", "westeurope", 80) is None
    nolimit = {"name": {"value": "x"}, "currentValue": 10, "limit": 0}
    assert qs.classify_usage(nolimit, "Sub A", "westeurope", 80) is None


def test_build_report_data_sorts_by_tightness():
    findings = [
        qs.classify_usage({"name": {"value": "a"}, "currentValue": 82, "limit": 100}, "S", "r", 80),
        qs.classify_usage({"name": {"value": "b"}, "currentValue": 99, "limit": 100}, "S", "r", 80),
    ]
    data = qs.build_report_data(findings, 1, 1, 80, [])
    assert data["findings"]["rows"][0]["quota"] == "b"  # tightest first
    assert data["summary_cards"][1]["value"] == "1"  # one Critical


def test_invalid_and_infinite_usage_not_healthy_headroom():
    for current, limit in [(None, 100), (1, float("nan")), (1, float("inf")), (-1, 10)]:
        assert qs.utilization(current, limit) is None


def test_storage_usage_is_regional_and_coverage_reported():
    from unittest.mock import patch
    urls = []
    def get(_, url):
        urls.append(url)
        return [{"name": {"value": "counter"}, "currentValue": 1, "limit": 100}]
    with patch.object(qs, "_headers", return_value={}), patch.object(qs, "_list_subscription_names", return_value={"a": "A"}), patch.object(qs, "_run_graph", return_value=[{"subscriptionId": "a", "location": "eastus"}]), patch.object(qs, "_get", side_effect=get):
        data = qs.main()
    assert any("Microsoft.Storage/locations/eastus/usages?api-version=2023-05-01" in u for u in urls)
    assert data["assessment_status"] == "Complete"
    assert len(data["assessments"]) == 3


def test_failed_or_empty_usage_never_complete():
    from unittest.mock import patch
    for result in ([], [{"currentValue": None, "limit": 100}]):
        with patch.object(qs, "_headers", return_value={}), patch.object(qs, "_list_subscription_names", return_value={}), patch.object(qs, "_run_graph", return_value=[{"subscriptionId": "a", "location": "eastus"}]), patch.object(qs, "_get", return_value=result):
            assert qs.main()["assessment_status"] != "Complete"


def test_empty_scope_is_not_assessed():
    from unittest.mock import patch
    with patch.object(qs, "_headers", return_value={}), patch.object(qs, "_list_subscription_names", return_value={}), patch.object(qs, "_run_graph", return_value=[]):
        assert qs.main()["assessment_status"] == "Not assessed"


def test_invalid_threshold_rejected_without_calls():
    from unittest.mock import patch
    import pytest
    with patch.object(qs, "_headers") as headers:
        for value in (0, 101, float("nan")):
            with pytest.raises(ValueError):
                qs.main(value)
        headers.assert_not_called()


if __name__ == "__main__":
    for name, function in sorted(globals().items()):
        if name.startswith("test_") and callable(function):
            function()
            print(f"ok {name}")
    print("all quota_scan tests passed")
