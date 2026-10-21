"""Unit tests for the pure helpers in waf_assess (no Azure calls)."""

import waf_assess as wa


def test_rating():
    assert wa.rating(95) == "Excellent"
    assert wa.rating(80) == "Good"
    assert wa.rating(60) == "Fair"
    assert wa.rating(30) == "Poor"
    assert wa.rating(None) == "Not assessed"


def test_score_pillars_weighted():
    assessed = [
        {"pillar": "Reliability", "severity": "High", "applicable": 10, "failing": 5},   # 0.5 pass, weight 3
        {"pillar": "Reliability", "severity": "Medium", "applicable": 10, "failing": 0},  # 1.0 pass, weight 2
    ]
    scores = wa.score_pillars(assessed)
    # (3*0.5 + 2*1.0) / (3+2) = 3.5/5 = 0.7 -> 70
    assert scores["Reliability"] == 70
    assert scores["Security"] is None  # not assessed


def test_score_pillars_skips_zero_applicable():
    assessed = [{"pillar": "Security", "severity": "High", "applicable": 0, "failing": 0}]
    assert wa.score_pillars(assessed)["Security"] is None


def test_build_report_data_five_pillar_cards():
    assessed = [{"pillar": "Reliability", "name": "x", "severity": "High", "applicable": 4, "failing": 1, "recommendation": "y"}]
    data = wa.build_report_data(assessed, 2, [])
    assert data["title"] == "Well-Architected Review"
    assert len(data["summary_cards"]) == 5
    assert data["summary_cards"][0]["label"] == "Reliability"
    assert data["summary_cards"][0]["value"] == "75"  # 3/4 pass -> 75
    assert data["findings"]["rows"][0]["pass_rate"] == "75%"


def test_build_report_data_marks_unassessed_pillars():
    data = wa.build_report_data([], 1, [])
    values = {c["label"]: c["value"] for c in data["summary_cards"]}
    assert values["Security"] == "n/a"


def test_custom_score_discloses_not_official_and_skipped_coverage():
    assessed = [{"pillar": "Reliability", "name": "one", "severity": "High", "applicable": 4, "failing": 0, "recommendation": "review"}]
    data = wa.build_report_data(assessed, 1, [])
    assert "not an official Microsoft" in data["subtitle"]
    assert data["coverage"]["skipped"] == 12
    assert data["assessment_status"] == "Partial"
    assert "partial coverage" in data["summary_cards"][0]["sub"]


def test_unknown_lifecycle_never_contributes_pass_score():
    counts = wa.assess_lifecycle_rows([{"properties": {"kubernetesVersion": "1.99.0", "supportPlan": "KubernetesOfficial"}}], {})
    assert {k: counts[k] for k in ("applicable", "failing", "unknown")} == {"applicable": 1, "failing": 0, "unknown": 1}
    assert counts["lifecycle_reasons"]
    scores = wa.score_pillars([{"pillar": "Operational Excellence", "severity": "Medium", **counts}])
    assert scores["Operational Excellence"] is None


def test_failed_all_checks_is_not_assessed_and_skipped():
    from unittest.mock import patch
    with patch.object(wa, "_headers", return_value={}), patch.object(wa, "_count_subscriptions", return_value=1), patch.object(wa, "_run_graph", side_effect=RuntimeError("denied")):
        data = wa.main()
    assert data["assessment_status"] == "Not assessed"
    assert data["coverage"]["skipped"] == 13


def test_no_permanent_kubernetes_floor_in_queries():
    assert not any("minor < 28" in c["kql"] for c in wa.CHECKS)


def test_missing_fields_are_counted_unknown_in_score_queries():
    for name in ("Locally redundant storage", "Premium SQL without zone redundancy", "Container Apps that cannot scale out"):
        check = next(c for c in wa.CHECKS if c["name"] == name)
        assert "unknown=countif(" in wa.check_query(check)
    network = next(c for c in wa.CHECKS if c["name"] == "PaaS with public network access")
    assert "properties.network.publicNetworkAccess" in wa.check_query(network)


def test_snapshot_load_failure_reason_reaches_report_notes():
    from unittest.mock import patch
    with patch("lifecycle.load_evidence", return_value={"_evidence_error": {"code": "SnapshotMalformed", "reason": "Configured lifecycle snapshot is not valid UTF-8 JSON."}}):
        counts = wa.assess_lifecycle_rows([{"properties": {"kubernetesVersion": "1.34", "supportPlan": "KubernetesOfficial"}}])
    check = next(c for c in wa.CHECKS if c.get("lifecycle"))
    data = wa.build_report_data([{**check, **counts}], 1, [])
    assert data["assessment_status"] == "Partial"
    assert any("not valid UTF-8 JSON" in note for note in data["method_notes"])


if __name__ == "__main__":
    for name, function in sorted(globals().items()):
        if name.startswith("test_") and callable(function):
            function()
            print(f"ok {name}")
    print("all waf_assess tests passed")
