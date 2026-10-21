# Defender and Advisor recommendation triage

## Inputs and permissions

Require approved subscription and resource allowlists, a UTC collection time,
workload owners and prioritization criteria. Use Reader for approved Advisor
reads and Security Reader for approved Defender evidence. Neither role implies
permission to apply, suppress or dismiss a recommendation.

## Collection

Using a scope restricted identity when the approved boundary is narrower than a
subscription, read current recommendations without forcing a refresh:

```powershell
foreach ($SUB in $SUBS) {
    az advisor recommendation list --subscription $SUB --output json
    az security assessment list --subscription $SUB --output json
}
```

Retain source IDs, resource IDs, collection time, source severity or impact,
category, recommendation text, observed state and any documented prerequisites.
Apply the shared assessment rules for pagination and bounded retries. Denied
sources remain unassessed, even when the other source succeeds.

## Analysis and output

1. Reconcile expected resources and readable sources. Current snapshots are not
   proof of historical compliance or continuous monitoring.
2. Preserve each source record and group overlapping proposed actions by
   affected resource and intended change. Do not silently discard one source.
3. Preserve Defender severity and Advisor impact as distinct fields. Apply
   approved local priority criteria with an explicit reason; they are not
   interchangeable source scales.
4. Explain dependencies, workload criticality and possible conflicting actions.
   Recommend owner validation before treating any recommendation as applicable.
5. Keep cost estimates by currency, time basis and source. Do not sum overlapping
   recommendations or label estimated savings as achieved. If the source does
   not provide a usable estimate, leave it null.
6. Draft an owner backlog with action, prerequisites, approval needs, risk,
   validation and evidence freshness. No dismissal, refresh, patching or ticket
   creation occurs in this workflow.
7. Populate `scenario_data` with `resource_id`, `source_recommendations`,
   `source_priority`, `local_priority_reason`, `overlap_group`, `owner` and
   `proposed_action`. Keep missing values null with a stated reason.

## Validation cases

- Healthy: complete readable sources have no applicable active recommendations.
- Finding: overlapping recommendations remain linked to both source IDs and
  produce one proposed action without duplicate savings.
- Missing: Defender access fails while Advisor succeeds, yielding Partial
  coverage rather than a clean security result.

## Sources

- [Advisor recommendation CLI](https://learn.microsoft.com/en-us/cli/azure/advisor/recommendation?view=azure-cli-latest).
- [Security assessment CLI](https://learn.microsoft.com/en-us/cli/azure/security/assessment?view=azure-cli-latest).

Read command shapes verified on 2026-10-21. Applicability and outcomes must be
verified separately in the approved environment.
