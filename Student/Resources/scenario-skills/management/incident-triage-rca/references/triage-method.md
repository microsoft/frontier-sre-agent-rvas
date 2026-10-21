# Triage method

A repeatable order for triaging one affected resource. The goal is time to mitigate, so gather the fast, high signal evidence first and reason from a timeline, not from a hunch.

## The order

1. Confirm the symptom. What is the user or alert actually seeing: unavailable, degraded, slow, or erroring. Note when it started, as precisely as you can.
2. Read current health. The gather_context tool reads Azure Resource Health for the resource. Unavailable or Degraded with a platform reason points at the platform; Available with a user symptom points at configuration or a dependency.
3. Ask what changed. The most common cause of a new incident is a recent change. gather_context reads the Activity Log over the window. Look for deployments, configuration writes, scale actions, and failed operations just before the symptom start.
4. Verify dependencies using configuration IDs, topology or traces. Resources in the same resource group are proximity candidates, not proven dependencies. Check the workload's database, gateway or key vault only when the relationship is evidenced.
5. Read the signals. Pull the metrics around the symptom start and a focused log query for errors.

## Evidence to pull with RunAzCliReadCommands

Metrics around the symptom start (adjust the metric to the resource type):

```
az monitor metrics list --resource <resource id> --metric "Percentage CPU" --interval PT1M --start-time <iso> --end-time <iso>
```

Recent errors from Log Analytics, when the resource sends logs to a workspace:

```
az monitor log-analytics query --workspace <workspace id> --analytics-query "union isfuzzy=true AzureDiagnostics, AppServiceHTTPLogs | where TimeGenerated > ago(2h) | where _ResourceId =~ '<resource id>' | where Level in ('Error','Critical') or toint(ScStatus) >= 500 | summarize count() by bin(TimeGenerated, 5m), Level"
```

Resource Health history detail, if you need more than the current state:

```
az rest --method GET --url "https://management.azure.com<resource id>/providers/Microsoft.ResourceHealth/availabilityStatuses?api-version=2020-05-01"
```

## Reasoning to a probable cause

The collector follows Activity Log and Resource Health continuations, up to 40 pages each. Neighbour inventory follows up to five Resource Graph pages of 200 rows. Caps, truncation and failed queries mark the assessment incomplete. A successful empty page is different from failed collection. Availability statuses do not guarantee complete health history for the requested interval.

- Build one timeline from the changes and the health transitions, most recent first.
- Anchor on the symptom start. The nearest preceding change is the first lead.
- Write two to four hypotheses. For each: the cause, the timeline evidence for it, a confidence (high, medium, low), and the single check that would confirm or rule it out.
- Prefer the hypothesis that explains the timing and the blast radius with the fewest assumptions. Keep correlation honest: a change just before the symptom is a lead, not proof.

## Mitigations

Propose mitigations ordered by safety and reversibility. For each give the exact command and the check to confirm it worked. Never present a change as done; the human runs it. A safe rollback of the most recent change is usually the first candidate; a restart is a mitigation, not a fix, so pair it with the follow up to find the cause.

## Sources

- [Activity Log](https://learn.microsoft.com/azure/azure-monitor/essentials/activity-log).
- [Resource Graph paging](https://learn.microsoft.com/azure/governance/resource-graph/concepts/work-with-data).
