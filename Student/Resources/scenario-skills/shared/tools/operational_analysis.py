"""Local evidence analysis for six original operational workflows. No cloud calls."""

import argparse
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path

from scenario_contract import validate_result
from sharing import sanitized_copy

FIELDS = {
    "slo-error-budget-analysis": [
        "total_events", "good_events", "bad_events", "sli", "slo_target",
        "allowed_bad_events", "remaining_error_budget", "budget_consumed_ratio",
    ],
    "backup-restore-validation": [
        "restore_completed", "isolated_target", "integrity_passed", "measured_rto_seconds",
        "measured_rpo_seconds", "target_rto_seconds", "target_rpo_seconds",
    ],
    "release-regression-detection": [
        "baseline_requests", "current_requests", "baseline_error_rate", "current_error_rate",
        "error_increase_percentage_points", "latency_increase_percent", "decision",
    ],
    "aks-application-incident-triage": [
        "pod_count", "affected_pods", "symptom_counts", "restart_threshold", "conclusion",
    ],
    "messaging-delivery-failure-triage": [
        "active_start", "active_end", "backlog_growth_per_minute", "dead_letter_count",
        "transfer_dead_letter_count", "completed_messages", "conclusion",
    ],
    "ai-inference-reliability-investigation": [
        "requests", "failure_rate", "throttle_rate", "p95_latency_ms", "latency_definition",
        "tokens_total", "evaluated_cases", "quality_pass_rate", "signals",
    ],
}


class EvidenceUnavailable(ValueError):
    """A required observation is missing, rather than observed to be healthy."""


def required(data: dict, key: str):
    if key not in data or data[key] is None:
        raise EvidenceUnavailable(f"Required evidence is unavailable: {key}.")
    return data[key]


def number(data: dict, key: str, minimum=0, maximum=None, integer=False):
    value = required(data, key)
    types = (int,) if integer else (int, float)
    if type(value) not in types or not math.isfinite(value):
        raise ValueError(f"{key} must be a finite {'integer' if integer else 'number'}.")
    if value < minimum or (maximum is not None and value > maximum):
        raise ValueError(f"{key} is outside its permitted range.")
    return value


def flag(data: dict, key: str) -> bool:
    value = required(data, key)
    if type(value) is not bool:
        raise ValueError(f"{key} must be a boolean.")
    return value


def utc(value: str) -> datetime:
    if not isinstance(value, str) or not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|\+00:00)", value
    ):
        raise ValueError("Timestamps must be ISO UTC values.")
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def positive(data: dict, key: str, integer=False):
    value = number(data, key, integer=integer)
    if value == 0:
        raise EvidenceUnavailable(f"{key} is zero; no valid denominator is available.")
    return value


def slo(data: dict, thresholds: dict):
    total = positive(data, "total_events", integer=True)
    good = number(data, "good_events", maximum=total, integer=True)
    unknown = number(data, "unknown_events", maximum=total, integer=True)
    if good + unknown > total:
        raise ValueError("Good and unclassified events cannot exceed the total.")
    if unknown:
        raise EvidenceUnavailable("Unclassified events prevent a complete success ratio.")
    target = number(thresholds, "slo_target", maximum=1)
    if not 0 < target < 1:
        raise ValueError("slo_target must be strictly between zero and one.")
    bad = total - good
    allowed = total * (1 - target)
    return bad > allowed + 1e-9, {
        "total_events": total, "good_events": good, "bad_events": bad,
        "sli": good / total, "slo_target": target, "allowed_bad_events": allowed,
        "remaining_error_budget": allowed - bad, "budget_consumed_ratio": bad / allowed,
    }, ["The budget is event based for the supplied window, not a time based SLA or short window burn rate."]


def restore(data: dict, thresholds: dict):
    completed = flag(data, "restore_completed")
    isolated = flag(data, "isolated_target")
    integrity = flag(data, "integrity_passed")
    rto_target = number(thresholds, "rto_seconds")
    rpo_target = number(thresholds, "rpo_seconds")
    rto = rpo = None
    limits = []
    if completed:
        start = utc(required(data, "recovery_started_at"))
        ready = utc(required(data, "application_ready_at"))
        reference = utc(required(data, "loss_reference_at"))
        recovered = utc(required(data, "recovered_through_at"))
        rto = (ready - start).total_seconds()
        rpo = (reference - recovered).total_seconds()
        if not recovered <= reference <= start <= ready:
            raise ValueError("Recovery and recovered write timestamps are inconsistent.")
    else:
        limits.append("Restore did not complete; measured recovery times are unavailable.")
    attention = not all((completed, isolated, integrity)) or (
        completed and (rto > rto_target or rpo > rpo_target)
    )
    return attention, {
        "restore_completed": completed, "isolated_target": isolated, "integrity_passed": integrity,
        "measured_rto_seconds": rto, "measured_rpo_seconds": rpo,
        "target_rto_seconds": rto_target, "target_rpo_seconds": rpo_target,
    }, limits


def release(data: dict, thresholds: dict):
    if not flag(data, "comparable_cohorts"):
        raise EvidenceUnavailable("Release cohorts, time windows or telemetry definitions are not comparable.")
    minimum = positive(thresholds, "minimum_requests", integer=True)
    baseline, current = required(data, "baseline"), required(data, "current")
    if not isinstance(baseline, dict) or not isinstance(current, dict):
        raise ValueError("Release baseline and current must be evidence objects.")
    totals = [positive(x, "requests", integer=True) for x in (baseline, current)]
    if min(totals) < minimum:
        raise EvidenceUnavailable("A release cohort has fewer requests than the approved minimum.")
    failures = [number(x, "failed_requests", maximum=n, integer=True)
                for x, n in zip((baseline, current), totals)]
    latencies = [positive(x, "p95_latency_ms") for x in (baseline, current)]
    rates = [f / n for f, n in zip(failures, totals)]
    delta = 100 * (rates[1] - rates[0])
    latency_delta = 100 * (latencies[1] / latencies[0] - 1)
    error_limit = number(thresholds, "max_error_increase_percentage_points")
    latency_limit = number(thresholds, "max_latency_increase_percent")
    attention = delta > error_limit or latency_delta > latency_limit
    return attention, {
        "baseline_requests": totals[0], "current_requests": totals[1],
        "baseline_error_rate": rates[0], "current_error_rate": rates[1],
        "error_increase_percentage_points": delta, "latency_increase_percent": latency_delta,
        "decision": "Investigate or pause for review" if attention else "No threshold breach observed",
    }, ["A temporal comparison does not establish release causation or authorize promotion or rollback."]


def aks(data: dict, thresholds: dict):
    pods = required(data, "pods")
    if not isinstance(pods, list):
        raise ValueError("pods must be a list.")
    if not pods:
        raise EvidenceUnavailable("No pods were observed; workload health cannot be inferred.")
    threshold = number(thresholds, "restart_threshold", integer=True)
    affected, counts, uids = [], {}, set()
    for pod in pods:
        if not isinstance(pod, dict):
            raise ValueError("Every pod must be an evidence object.")
        uid = required(pod, "uid")
        if not isinstance(uid, str) or not uid or uid in uids:
            raise ValueError("Pod UIDs must be unique nonempty strings.")
        uids.add(uid)
        name = required(pod, "name")
        if not isinstance(name, str) or not name.strip():
            raise ValueError("Pod names must be nonempty strings.")
        phase = required(pod, "phase")
        if phase not in ("Pending", "Running", "Succeeded", "Failed", "Unknown"):
            raise ValueError("Unknown pod phase value.")
        ready = flag(pod, "ready")
        waiting = required(pod, "waiting_reason")
        if not isinstance(waiting, str):
            raise ValueError("waiting_reason must be a string; use an empty string when not waiting.")
        reasons = []
        if phase in ("Pending", "Failed", "Unknown"):
            reasons.append(phase)
        if phase not in ("Succeeded", "Failed") and not ready:
            reasons.append("NotReady")
        if waiting:
            reasons.append(waiting)
        if number(pod, "recent_oom_kills", integer=True):
            reasons.append("RecentOOMKill")
        if number(pod, "restart_delta", integer=True) > threshold:
            reasons.append("RestartThresholdExceeded")
        if reasons:
            affected.append({"resource": name, "symptoms": reasons})
            for reason in reasons:
                counts[reason] = counts.get(reason, 0) + 1
    return bool(affected), {
        "pod_count": len(pods), "affected_pods": affected, "symptom_counts": counts,
        "restart_threshold": threshold,
        "conclusion": "Investigate observed pod symptoms" if affected else "No configured pod symptom observed",
    }, ["Pod symptoms are not a proven root cause. A ready pod does not prove business journey availability."]


def messaging(data: dict, thresholds: dict):
    start = number(data, "active_start", integer=True)
    end = number(data, "active_end", integer=True)
    seconds = positive(data, "sample_duration_seconds")
    dlq = number(data, "dead_letter_count", integer=True)
    transfer = number(data, "transfer_dead_letter_count", integer=True)
    completed = number(data, "completed_messages", integer=True)
    growth = (end - start) * 60 / seconds
    growth_limit = number(thresholds, "max_backlog_growth_per_minute")
    dlq_limit = number(thresholds, "max_dead_letter_count", integer=True)
    transfer_limit = number(thresholds, "max_transfer_dead_letter_count", integer=True)
    minimum_completed = number(thresholds, "minimum_completed_messages", integer=True)
    attention = (
        growth > growth_limit or dlq > dlq_limit or transfer > transfer_limit
        or (end > 0 and completed < minimum_completed)
    )
    return attention, {
        "active_start": start, "active_end": end, "backlog_growth_per_minute": growth,
        "dead_letter_count": dlq, "transfer_dead_letter_count": transfer,
        "completed_messages": completed,
        "conclusion": "Investigate backlog or delivery evidence" if attention else "No configured threshold breach",
    }, ["Queue depth is a stock, not a count of failures. Replay requires separate approval and idempotency review."]


def ai(data: dict, thresholds: dict):
    if not flag(data, "comparable_cohorts"):
        raise EvidenceUnavailable("Model deployment, API, streaming mode or evaluation cohorts are mixed.")
    requests = positive(data, "requests", integer=True)
    minimum = positive(thresholds, "minimum_requests", integer=True)
    cases = positive(data, "evaluated_cases", integer=True)
    if requests < minimum or cases < positive(thresholds, "minimum_evaluated_cases", integer=True):
        raise EvidenceUnavailable("Inference or quality samples are below the approved minimum.")
    failed = number(data, "failed_requests", maximum=requests, integer=True)
    throttled = number(data, "throttled_requests", maximum=failed, integer=True)
    passed = number(data, "quality_passed_cases", maximum=cases, integer=True)
    latency = number(data, "p95_latency_ms")
    definition = required(data, "latency_definition")
    if definition not in ("end_to_end_nonstreaming", "time_to_first_token"):
        raise ValueError("Use one explicitly supported latency definition.")
    failure_rate, throttle_rate, quality_rate = failed / requests, throttled / requests, passed / cases
    signals = []
    for label, breached in (
        ("Failure rate", failure_rate > number(thresholds, "max_failure_rate", maximum=1)),
        ("Throttle rate", throttle_rate > number(thresholds, "max_throttle_rate", maximum=1)),
        ("Latency", latency > number(thresholds, "max_p95_latency_ms")),
        ("Quality", quality_rate < number(thresholds, "minimum_quality_pass_rate", maximum=1)),
    ):
        if breached:
            signals.append(label)
    return bool(signals), {
        "requests": requests, "failure_rate": failure_rate, "throttle_rate": throttle_rate,
        "p95_latency_ms": latency, "latency_definition": definition,
        "tokens_total": number(data, "tokens_total", integer=True),
        "evaluated_cases": cases, "quality_pass_rate": quality_rate, "signals": signals,
    }, ["Quality depends on the approved dataset and rubric. Token counts alone are not a billed cost estimate."]


ANALYZERS = dict(zip(FIELDS, (slo, restore, release, aks, messaging, ai)))


def assess(scenario: str, document: dict, contract: dict) -> dict:
    if scenario not in ANALYZERS or not isinstance(document, dict):
        raise ValueError("Select a supported scenario and an evidence object.")
    if type(document.get("schema_version")) is not int or document["schema_version"] != 1:
        raise ValueError("Evidence schema_version must be 1.")
    scope = required(document, "scope")
    if not isinstance(scope, dict) or not isinstance(scope.get("subscription_ids"), list) or not scope["subscription_ids"]:
        raise ValueError("An explicit approved subscription allowlist is required.")
    subscriptions = scope["subscription_ids"]
    if any(not isinstance(x, str) or not re.fullmatch(
        r"[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}", x
    ) for x in subscriptions):
        raise ValueError("Approved subscriptions must be GUIDs.")
    ids = required(document, "resource_ids")
    if not isinstance(ids, list) or not ids:
        raise ValueError("At least one approved Azure resource ID is required.")
    for resource in ids:
        if not isinstance(resource, str) or not re.fullmatch(
            r"/subscriptions/[^/]+/resourceGroups/[^/]+/providers/[^/]+/.+", resource, re.IGNORECASE
        ) or resource.split("/")[2].lower() not in {x.lower() for x in subscriptions}:
            raise ValueError("An evidence resource is outside the approved subscription scope.")
    start, end = utc(required(document, "window_start")), utc(required(document, "window_end"))
    collected = utc(required(document, "collected_at"))
    if end <= start or collected < end:
        raise ValueError("Evidence must cover a positive closed UTC window collected after its end.")
    evidence = required(document, "evidence")
    if not isinstance(evidence, list) or not evidence:
        raise ValueError("Source references and timestamps are required.")
    for item in evidence:
        if (not isinstance(item, dict) or not isinstance(item.get("source"), str)
                or not item["source"].strip() or utc(required(item, "collected_at")) > collected):
            raise ValueError("Invalid evidence source or collection timestamp.")
    complete = flag(document, "collection_complete")
    truncated = flag(document, "collection_truncated")
    if complete and truncated:
        raise ValueError("A truncated collection cannot be marked complete.")
    if not complete and not document.get("collection_limitations"):
        raise ValueError("Incomplete collection requires explicit collection_limitations.")
    limits = required(document, "collection_limitations")
    if not isinstance(limits, list) or not all(isinstance(x, str) and x.strip() for x in limits):
        raise ValueError("collection_limitations must be a list of nonempty reasons.")
    data, thresholds = required(document, "data"), required(document, "thresholds")
    if not isinstance(data, dict) or not isinstance(thresholds, dict):
        raise ValueError("data and thresholds must be objects.")
    limits = list(limits)
    assessed = 1
    try:
        if scenario == "messaging-delivery-failure-triage" and (
            positive(data, "sample_duration_seconds") != (end - start).total_seconds()
        ):
            raise ValueError("Queue snapshot duration must match the observation window.")
        if scenario == "backup-restore-validation" and flag(data, "restore_completed"):
            for key in ("recovery_started_at", "application_ready_at"):
                if not start <= utc(required(data, key)) <= end:
                    raise ValueError("Recovery observations must lie within the approved window.")
        attention, values, specific_limits = ANALYZERS[scenario](data, thresholds)
        limits.extend(specific_limits)
        state = "Needs attention" if attention else "Observed"
    except EvidenceUnavailable as error:
        assessed = 0
        state = "Not assessed"
        values = dict.fromkeys(FIELDS[scenario])
        limits.append(str(error))
    if set(values) != set(FIELDS[scenario]):
        raise ValueError("Analyzer fields do not match the scenario contract.")
    result = {
        "scenario_id": scenario, "scope": scope,
        "assessed_at": datetime.now(timezone.utc).isoformat(),
        "assessment_status": "Not assessed" if not assessed else "Complete" if complete else "Partial",
        "coverage": {"expected_checks": 1, "assessed_checks": assessed, "truncated": truncated},
        "findings": [{"id": f"{scenario}-summary", "status": state,
                      "severity": "Medium" if state == "Needs attention" else "Info",
                      "evidence": evidence, "scenario_data": values}],
        "limitations": limits, "resource_ids": ids,
        "observation_window": {"start": document["window_start"], "end": document["window_end"]},
    }
    validate_result(result, contract)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", required=True, choices=FIELDS)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--contract", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--sharing-output", type=Path)
    args = parser.parse_args()
    outputs = [args.output] + ([args.sharing_output] if args.sharing_output else [])
    if len({p.resolve() for p in outputs}) != len(outputs) or any(p.exists() for p in outputs):
        parser.error("Output paths must be distinct new files; existing evidence is never overwritten.")
    result = assess(args.scenario, json.loads(args.input.read_text(encoding="utf-8")),
                    json.loads(args.contract.read_text(encoding="utf-8")))
    shared = sanitized_copy(result) if args.sharing_output else None
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write("\n")
    if args.sharing_output:
        with args.sharing_output.open("x", encoding="utf-8") as stream:
            json.dump(shared, stream, indent=2, allow_nan=False)
            stream.write("\n")
    print("Local evidence validated. Sharing copies are drafts; no cloud action was performed.")


if __name__ == "__main__":
    main()
