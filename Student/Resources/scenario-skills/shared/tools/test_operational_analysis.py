import copy
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parents[1]
sys.path.insert(0, str(TOOLS))
from operational_analysis import FIELDS, assess


def test_workflow_definitions_match_executable_fields():
    extensions = json.loads(
        (ROOT / "catalog" / "extension-scenarios.json").read_text(encoding="utf-8"))["scenarios"]
    assert {row["slug"] for row in extensions} == set(FIELDS)
    for row in extensions:
        _, contract = fixture(row["slug"])
        fields = contract["properties"]["findings"]["items"]["properties"]["scenario_data"]["required"]
        assert set(fields) == set(FIELDS[row["slug"]])


def fixture(scenario):
    directory = ROOT / "management" / scenario / "references"
    return (
        json.loads((directory / "evidence-example.json").read_text(encoding="utf-8")),
        json.loads((directory / "output-contract.json").read_text(encoding="utf-8")),
    )


def analyze(scenario, edit=None):
    document, contract = fixture(scenario)
    if edit:
        edit(document)
    return assess(scenario, document, contract)


@pytest.mark.parametrize("scenario", FIELDS)
def test_six_synthetic_healthy_cases(scenario):
    result = analyze(scenario)
    assert result["assessment_status"] == "Complete"
    assert result["findings"][0]["status"] == "Observed"
    assert set(result["findings"][0]["scenario_data"]) == set(FIELDS[scenario])


@pytest.mark.parametrize("scenario,edit", [
    ("slo-error-budget-analysis", lambda d: d["data"].update(good_events=9800)),
    ("backup-restore-validation", lambda d: d["data"].update(integrity_passed=False)),
    ("release-regression-detection", lambda d: d["data"]["current"].update(failed_requests=60)),
    ("aks-application-incident-triage", lambda d: d["data"]["pods"][0].update(waiting_reason="CrashLoopBackOff")),
    ("messaging-delivery-failure-triage", lambda d: d["data"].update(active_end=300)),
    ("ai-inference-reliability-investigation", lambda d: d["data"].update(quality_passed_cases=50)),
])
def test_six_findings_have_evidence(scenario, edit):
    result = analyze(scenario, edit)
    finding = result["findings"][0]
    assert finding["status"] == "Needs attention"
    assert finding["evidence"]
    assert finding["severity"] == "Medium"


@pytest.mark.parametrize("scenario,field", [
    ("slo-error-budget-analysis", "total_events"),
    ("backup-restore-validation", "application_ready_at"),
    ("release-regression-detection", "baseline"),
    ("aks-application-incident-triage", "pods"),
    ("messaging-delivery-failure-triage", "completed_messages"),
    ("ai-inference-reliability-investigation", "evaluated_cases"),
])
def test_missing_evidence_never_looks_healthy(scenario, field):
    result = analyze(scenario, lambda d: d["data"].pop(field))
    assert result["assessment_status"] == "Not assessed"
    assert result["coverage"]["assessed_checks"] == 0
    assert result["findings"][0]["status"] == "Not assessed"
    assert all(v is None for v in result["findings"][0]["scenario_data"].values())
    assert any(field in limit for limit in result["limitations"])


@pytest.mark.parametrize("scenario", FIELDS)
def test_incomplete_collection_cannot_be_complete(scenario):
    result = analyze(scenario, lambda d: d.update(
        collection_complete=False, collection_limitations=["Synthetic denied or incomplete source."]))
    assert result["assessment_status"] == "Partial"
    assert result["coverage"]["truncated"] is False


def test_truncation_is_separate_from_denied_or_missing_evidence():
    result = analyze("slo-error-budget-analysis", lambda d: d.update(
        collection_complete=False, collection_truncated=True,
        collection_limitations=["Synthetic query result cap."]))
    assert result["assessment_status"] == "Partial"
    assert result["coverage"]["truncated"] is True
    with pytest.raises(ValueError, match="truncated"):
        analyze("slo-error-budget-analysis", lambda d: d.update(collection_truncated=True))


def test_exact_slo_math_and_budget_boundary():
    result = analyze("slo-error-budget-analysis")
    values = result["findings"][0]["scenario_data"]
    assert values["sli"] == 0.995
    assert values["remaining_error_budget"] == pytest.approx(50)
    assert values["budget_consumed_ratio"] == pytest.approx(0.5)
    result = analyze("slo-error-budget-analysis", lambda d: d["data"].update(good_events=9900))
    assert result["findings"][0]["status"] == "Observed"
    result = analyze("slo-error-budget-analysis", lambda d: d["data"].update(good_events=9800))
    assert result["findings"][0]["scenario_data"]["remaining_error_budget"] == pytest.approx(-100)


@pytest.mark.parametrize("edit", [
    lambda d: d["data"].update(total_events=0, good_events=0),
    lambda d: d["data"].update(unknown_events=1),
])
def test_slo_zero_or_unclassified_events_are_unassessed(edit):
    assert analyze("slo-error-budget-analysis", edit)["assessment_status"] == "Not assessed"


def test_restore_measures_application_not_platform_job():
    values = analyze("backup-restore-validation")["findings"][0]["scenario_data"]
    assert values["measured_rto_seconds"] == 1200
    assert values["measured_rpo_seconds"] == 120
    result = analyze("backup-restore-validation", lambda d: d["data"].update(restore_completed=False))
    assert result["findings"][0]["status"] == "Needs attention"
    assert result["findings"][0]["scenario_data"]["measured_rto_seconds"] is None
    assert result["limitations"]


@pytest.mark.parametrize("edit", [
    lambda d: d["data"].update(application_ready_at="2026-10-01T09:59:00Z"),
    lambda d: d["data"].update(recovered_through_at="2026-10-01T10:01:00Z"),
    lambda d: d["data"].update(application_ready_at="2026-10-03T10:00:00Z"),
])
def test_invalid_restore_clock_evidence_fails(edit):
    with pytest.raises(ValueError):
        analyze("backup-restore-validation", edit)


def test_release_distinguishes_percentage_points_from_relative_change():
    result = analyze("release-regression-detection", lambda d: d["data"]["current"].update(
        failed_requests=60, p95_latency_ms=300))
    values = result["findings"][0]["scenario_data"]
    assert values["error_increase_percentage_points"] == pytest.approx(4)
    assert values["latency_increase_percent"] == pytest.approx(50)
    assert "pause" in values["decision"].lower()


@pytest.mark.parametrize("scenario,field,edit", [
    ("release-regression-detection", "max_latency_increase_percent",
     lambda d: d["data"]["current"].update(failed_requests=100)),
    ("messaging-delivery-failure-triage", "max_transfer_dead_letter_count",
     lambda d: d["data"].update(active_end=1000)),
    ("messaging-delivery-failure-triage", "minimum_completed_messages",
     lambda d: d["data"].update(active_end=0)),
])
def test_a_breach_cannot_hide_missing_customer_criteria(scenario, field, edit):
    document, contract = fixture(scenario)
    edit(document)
    document["thresholds"].pop(field)
    result = assess(scenario, document, contract)
    assert result["assessment_status"] == "Not assessed"
    assert any(field in reason for reason in result["limitations"])


@pytest.mark.parametrize("edit", [
    lambda d: d["data"].update(comparable_cohorts=False),
    lambda d: d["data"]["current"].update(requests=50),
    lambda d: d["data"]["baseline"].update(p95_latency_ms=0),
])
def test_release_missing_comparability_never_promotes(edit):
    assert analyze("release-regression-detection", edit)["assessment_status"] == "Not assessed"


def test_successful_kubernetes_job_is_not_flagged_for_readiness():
    result = analyze("aks-application-incident-triage", lambda d: d["data"]["pods"][0].update(
        phase="Succeeded", ready=False))
    assert result["findings"][0]["status"] == "Observed"


def test_aks_window_symptoms_and_uid_safety():
    result = analyze("aks-application-incident-triage", lambda d: d["data"]["pods"][0].update(
        recent_oom_kills=1, restart_delta=3))
    symptoms = result["findings"][0]["scenario_data"]["symptom_counts"]
    assert symptoms == {"RecentOOMKill": 1, "RestartThresholdExceeded": 1}
    assert analyze("aks-application-incident-triage", lambda d: d["data"].update(pods=[]))[
        "assessment_status"] == "Not assessed"
    with pytest.raises(ValueError, match="UID"):
        analyze("aks-application-incident-triage", lambda d: d["data"]["pods"].append(
            copy.deepcopy(d["data"]["pods"][0])))


def test_queue_growth_and_idle_queue_are_distinct():
    values = analyze("messaging-delivery-failure-triage")["findings"][0]["scenario_data"]
    assert values["backlog_growth_per_minute"] == -8
    idle = analyze("messaging-delivery-failure-triage", lambda d: d["data"].update(
        active_start=0, active_end=0, completed_messages=0))
    assert idle["findings"][0]["status"] == "Observed"
    with pytest.raises(ValueError, match="duration"):
        analyze("messaging-delivery-failure-triage", lambda d: d["data"].update(sample_duration_seconds=1))


def test_ai_rates_and_separate_failure_signals():
    result = analyze("ai-inference-reliability-investigation", lambda d: d["data"].update(
        failed_requests=100, throttled_requests=50, p95_latency_ms=3000, quality_passed_cases=40))
    values = result["findings"][0]["scenario_data"]
    assert values["failure_rate"] == 0.1
    assert values["throttle_rate"] == 0.05
    assert values["quality_pass_rate"] == 0.4
    assert values["signals"] == ["Failure rate", "Throttle rate", "Latency", "Quality"]
    with pytest.raises(ValueError):
        analyze("ai-inference-reliability-investigation", lambda d: d["data"].update(throttled_requests=20))


@pytest.mark.parametrize("edit", [
    lambda d: d["data"].update(evaluated_cases=0),
    lambda d: d["data"].update(comparable_cohorts=False),
    lambda d: d["data"].update(evaluated_cases=10),
])
def test_ai_unknown_quality_or_mixed_cohorts_are_unassessed(edit):
    assert analyze("ai-inference-reliability-investigation", edit)["assessment_status"] == "Not assessed"


@pytest.mark.parametrize("edit", [
    lambda d: d.update(scope={"subscription_ids": []}),
    lambda d: d.update(resource_ids=["/subscriptions/11111111-1111-1111-1111-111111111111/resourceGroups/x/providers/Microsoft.Web/sites/x"]),
    lambda d: d.update(window_end=d["window_start"]),
    lambda d: d.update(collected_at="2026-10-01T01:00:00+01:00"),
    lambda d: d.update(collection_complete=False, collection_limitations=[]),
    lambda d: d.update(evidence=[]),
    lambda d: d.update(schema_version=True),
    lambda d: d["data"].update(total_events=True),
    lambda d: d["thresholds"].update(slo_target=float("nan")),
    lambda d: d["data"].update(good_events=10001),
    lambda d: d["data"].update(good_events=10000, unknown_events=1),
    lambda d: d["thresholds"].update(slo_target=1),
])
def test_invalid_evidence_or_thresholds_fail_explicitly(edit):
    with pytest.raises(ValueError):
        analyze("slo-error-budget-analysis", edit)


@pytest.mark.parametrize("scenario", FIELDS)
def test_actual_cli_emits_private_contract_and_sanitized_draft(tmp_path, scenario):
    directory = ROOT / "management" / scenario / "references"
    private, shared = tmp_path / "private.json", tmp_path / "shared.json"
    args = [sys.executable, str(TOOLS / "operational_analysis.py"), "--scenario", scenario,
            "--input", str(directory / "evidence-example.json"),
            "--contract", str(directory / "output-contract.json"),
            "--output", str(private), "--sharing-output", str(shared)]
    result = subprocess.run(args, capture_output=True, text=True, timeout=10, check=False)
    assert result.returncode == 0, result.stderr
    private_result = json.loads(private.read_text(encoding="utf-8"))
    assert private_result["assessment_status"] == "Complete"
    shared_result = json.loads(shared.read_text(encoding="utf-8"))
    assert shared_result["sharing_review"]["status"] == "Draft: human review required"
    assert "00000000-0000-0000-0000-000000000000" not in shared.read_text(encoding="utf-8")
    original = private.read_bytes()
    rerun = subprocess.run(args, capture_output=True, text=True, timeout=10, check=False)
    assert rerun.returncode != 0
    assert private.read_bytes() == original


@pytest.mark.parametrize("scenario", FIELDS)
def test_local_runtime_works_inside_its_flattened_bundle(tmp_path, scenario):
    sys.path.insert(0, str(ROOT / "scripts"))
    from build_library import bundle_files

    for relative, source in bundle_files(ROOT / "management" / scenario).items():
        destination = tmp_path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
    result = subprocess.run(
        [sys.executable, "tools/operational_analysis.py", "--scenario", scenario,
         "--input", "references/evidence-example.json", "--contract", "references/output-contract.json",
         "--output", "private.json", "--sharing-output", "sharing.json"],
        cwd=tmp_path, capture_output=True, text=True, timeout=10, check=False,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads((tmp_path / "private.json").read_text(encoding="utf-8"))["assessment_status"] == "Complete"
    assert json.loads((tmp_path / "sharing.json").read_text(encoding="utf-8"))["sharing_review"]["redactions"] > 0
