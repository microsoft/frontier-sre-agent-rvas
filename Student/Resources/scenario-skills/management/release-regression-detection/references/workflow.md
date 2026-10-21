# Evidence collection and analysis

## Collection

### 1. Read request counts and latency by observed application version

AppVersion must actually identify the release or be joined to the approved manifest. This query gives a percentile of retained telemetry rows, not a sampling corrected population percentile. Use unsampled request evidence or an explicitly validated common sampling regime for comparison. Reject unknown success records and mixed version cohorts; blank AppVersion is not a known release.

```powershell
$KQL = "AppRequests | where TimeGenerated >= datetime($START) and TimeGenerated < datetime($END) | where _ResourceId =~ '$APP_ID' | summarize requests=sum(ItemCount), failed_requests=sumif(ItemCount, Success == false), unknown_events=sumif(ItemCount, isnull(Success)), observed_p95_ms=percentile(DurationMs,95) by AppVersion"
az monitor log-analytics query --subscription $SUB --workspace $WORKSPACE --analytics-query $KQL --timespan "$START/$END" --output json
```

### 2. Read the approved local release mapping

This is a declared required operator input, not an assumed bundled file. Resolve before and after windows or simultaneous canary and control cohorts. Record other configuration, traffic, dependency and instrumentation changes as confounders.

```powershell
Get-Content -LiteralPath $RELEASE_MANIFEST -Raw | ConvertFrom-Json
```

### 3. Assess cohort differences locally

Use [input definitions](../../../shared/references/operational-evidence.md) and [synthetic example](./evidence-example.json). This tool reads local normalized evidence only. It never invokes a pipeline, changes traffic or performs rollback.

```powershell
python tools/operational_analysis.py --scenario release-regression-detection --input $INPUT --contract references/output-contract.json --output release-private-result.json --sharing-output release-sharing-draft.json
```

## Analysis rules

1. Require positive request denominators, the approved minimum sample per cohort and a positive baseline latency. Missing or incomparable cohorts are Not assessed.
2. Compute error rates independently per cohort. Error increase in percentage points is100 times (current rate minus baseline rate), not relative percent growth.
3. Compute latency increase percent as100 times (current p95 divided by baseline p95 minus1). Compare both values against separately configured customer thresholds.
4. A threshold breach recommends investigation or a pause for human review. No breach means only no configured regression observed, not approval to promote or proof of release safety.
5. Preserve cohort selection, observation windows, telemetry coverage and confounders. Temporal association does not establish a deployment as the cause.

## Known limits

- Aggregate counters alone do not establish statistical significance, causal attribution or whether a critical low traffic route regressed.
- Sampled percentiles, mismatched request mix and missing version instrumentation can make the comparison invalid. No automatic rollback or promotion is implemented.

## Expected validation cases

- Healthy: comparable cohorts with the approved minimum sample and differences below both thresholds produce Observed, not automatic promotion.
- Finding: current failures60 of1200 versus baseline10 of1000 exceed a synthetic1 percentage point threshold and require review.
- Missing: insufficient requests, zero baseline latency, unknown success, unmapped version or incomparable cohorts cannot be a successful gate.

## Sources

- [Progressive exposure and health gated safe deployment practices](https://learn.microsoft.com/azure/well-architected/operational-excellence/safe-deployments) (consulted 2026-10-21).
- [Application version, duration, success and sampling fields](https://learn.microsoft.com/azure/azure-monitor/reference/tables/apprequests) (consulted 2026-10-21).
