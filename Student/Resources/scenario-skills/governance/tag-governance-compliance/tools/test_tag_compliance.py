"""Unit tests for the pure helpers in tag_compliance (no Azure calls)."""

import tag_compliance as tc


def test_normalize_key():
    assert tc.normalize_key("Cost-Center") == "cost-center"
    assert tc.normalize_key("cost_center") == "cost_center"
    assert tc.normalize_key("OWNER") == "owner"


def test_matching_ignores_case_only():
    tags = {"Owner": "team", "CostCenter": "1234"}
    assert tc.missing_tags(tags, ["owner", "environment", "cost-center"]) == ["environment", "cost-center"]
    assert tc.missing_tags({}, ["owner"]) == ["owner"]


def test_severity_for_missing():
    assert tc.severity_for_missing(["owner"]) == "High"
    assert tc.severity_for_missing(["environment"]) == "Medium"


def test_classify_resource():
    resource = {"name": "r1", "type": "x", "subscriptionId": "a", "tags": {"environment": "prod"}}
    finding = tc.classify_resource(resource, ["owner", "environment"])
    assert finding["missing_tags"] == "owner"
    assert finding["severity"] == "High"
    assert tc.classify_resource({"name": "r2", "tags": {"owner": "t", "environment": "p"}}, ["owner", "environment"]) is None


def test_build_report_data_compliance_percent():
    resources = [
        {"name": "r1", "type": "x", "subscriptionId": "a", "tags": {"owner": "t", "environment": "p", "cost-center": "1"}},
        {"name": "r2", "type": "x", "subscriptionId": "a", "tags": {}, "supportsTags": True},
    ]
    data = tc.build_report_data(resources, ["owner", "environment", "cost-center"], 1, {"a": "Sub A"}, [])
    assert data["summary_cards"][0]["value"] == "50.0%"
    assert data["summary_cards"][2]["value"] == "1"  # one missing owner


def test_blank_required_values_fail():
    assert tc.missing_tags({"OWNER": "  ", "env": None, "cost-center": ""}, ["owner", "env", "cost-center"]) == ["owner", "env", "cost-center"]
    assert tc.missing_tags({"Owner": "Team"}, ["owner"]) == []


def test_empty_unknown_and_unsupported_are_not_compliant():
    empty = tc.build_report_data([], ["owner"], 0, {}, [])
    assert empty["assessment_status"] == "Not assessed"
    assert empty["summary_cards"][0]["value"] == "Not assessed"
    data = tc.build_report_data([
        {"id": "unknown", "type": "x", "tags": {}},
        {"id": "unsupported", "type": "y", "tags": {}, "supportsTags": False},
        {"id": "supported", "type": "z", "tags": {"OWNER": "Team"}},
    ], ["owner"], 1, {}, [])
    assert data["assessment_status"] == "Partial"
    assert data["unassessed_resources"][0]["resource_id"] == "unknown"
    assert data["excluded_resources"][0]["resource_id"] == "unsupported"
    assert data["summary_cards"][0]["value"] == "100.0%"


def test_inaccessible_inventory_is_not_assessed(monkeypatch):
    monkeypatch.setattr(tc, "_headers", lambda: {})
    monkeypatch.setattr(tc, "_list_subscription_names", lambda headers: {"a": "A"})
    def denied(*args):
        raise RuntimeError("denied")
    monkeypatch.setattr(tc, "_run_graph", denied)
    result = tc.main()
    assert result["assessment_status"] == "Not assessed"
    assert result["summary_cards"][0]["value"] == "Not assessed"


if __name__ == "__main__":
    for name, function in sorted(globals().items()):
        if name.startswith("test_") and callable(function):
            function()
            print(f"ok {name}")
    print("all tag_compliance tests passed")
