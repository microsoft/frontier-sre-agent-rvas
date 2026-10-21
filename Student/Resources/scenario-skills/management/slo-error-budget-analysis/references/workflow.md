# Evidence collection and analysis

## Collection

### 1. Read scoped request counts with sampling weights

This executable query implements the simple technical request success definition only. Apply the approved eligibility and success predicate before production use. AppRequests ItemCount supplies sampling weights; do not use count() as an unsampled request total. Keep the raw query response privately and normalize its numeric cells to the documented input. An empty response, missing ItemCount, unknown Success, query cap or access denial is not zero failures. Record sampling and ingestion caveats.

```powershell
$KQL = "AppRequests | where TimeGenerated >= datetime($START) and TimeGenerated < datetime($END) | where _ResourceId =~ '$APP_ID' | summarize total_events=sum(ItemCount), good_events=sumif(ItemCount, Success == true), unknown_events=sumif(ItemCount, isnull(Success))"
az monitor log-analytics query --subscription $SUB --workspace $WORKSPACE --analytics-query $KQL --timespan "$START/$END" --output json
```

### 2. Analyze the approved normalized evidence locally

Run from the deployed skill root, or a packaging-equivalent local bundle. All files are local. The shared tool performs no cloud calls. See [input and algorithm contract](../../../shared/references/operational-evidence.md) and [synthetic example](./evidence-example.json). The private result satisfies the evidence contract; the sanitized sharing draft intentionally aliases identifiers and is not a replacement for private evidence.

```powershell
python tools/operational_analysis.py --scenario slo-error-budget-analysis --input $INPUT --contract references/output-contract.json --output slo-private-result.json --sharing-output slo-sharing-draft.json
```

## Analysis rules

1. Require a positive eligible event denominator, classified success evidence, explicit UTC window and customer target. Zero traffic and unknown success values are Not assessed.
2. Calculate SLI = good_events / total_events. Bad events = total_events minus good_events. Allowed bad events = total_events times (1 minus target). Retain fractional allowance and negative remaining budget rather than rounding away a breach.
3. Calculate remaining budget = allowed bad events minus bad events, and consumed ratio = bad events / allowed bad events. Compare the event based SLI with the approved target. Do not call this elapsed downtime or a contractual SLA result.
4. Any incomplete collection prevents Complete even when the observed subset meets the target. Do not claim a short window burn rate without separate windows and denominators.
5. Recommendations to freeze releases, change alerts or adjust an SLO are drafts. No release system, monitor or target is changed.

## Known limits

- Telemetry sampling weights are estimates of represented events and do not prove full traffic capture. Ingestion delay, workspace scope and instrumentation gaps must be assessed.
- A request success field is a technical indicator, not necessarily a successful business transaction. Eligibility, exclusions and the target require customer agreement.

## Expected validation cases

- Healthy: synthetic 10000 events, 9950 good, zero unknown and target0.99 yield SLI0.995 and50 remaining bad events within floating point tolerance.
- Finding: 9800 good out of10000 at target0.99 exhausts the budget and returns Needs attention with negative remaining budget.
- Missing: zero traffic, unknown success values, denied query or incomplete collection must never produce an unqualified successful assessment.

## Sources

- [AppRequests schema and ItemCount sampling weight](https://learn.microsoft.com/azure/azure-monitor/reference/tables/apprequests) (consulted 2026-10-21).
- [Reliability targets and error budgets](https://learn.microsoft.com/azure/well-architected/reliability/reliability-test) (consulted 2026-10-21).
