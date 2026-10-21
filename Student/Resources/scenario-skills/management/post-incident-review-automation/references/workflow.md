# Evidence collection and analysis

## Collection

### 1. Read first alert, change and performance evidence

Use supported interval and aggregations from definitions. Page alerts and ARG, split Activity Log windows if capped, deduplicate IDs and obey Retry-After. Retrieve each relevant alert history with its /history GET to distinguish detection, acknowledgement and monitor resolution.

```powershell
az rest --method get --url "https://management.azure.com/subscriptions/$SUB/providers/Microsoft.AlertsManagement/alerts?api-version=2019-03-01&customTimeRange=$LOOKBACK_START/$END" --output json
az monitor activity-log list --subscription $SUB --resource-id $RESOURCE_ID --start-time $LOOKBACK_START --end-time $END --max-events 10000 --output json
az graph query --subscriptions $SUB --first 1000 --graph-query "resourcechanges | where properties.targetResourceId =~ '$RESOURCE_ID' | extend changed_at=todatetime(properties.changeAttributes.timestamp) | where changed_at >= datetime($LOOKBACK_START) and changed_at < datetime($END) | project id,changed_at,properties | order by changed_at asc" --output json
az monitor metrics list-definitions --subscription $SUB --resource $RESOURCE_ID --output json
az monitor metrics list --subscription $SUB --resource $RESOURCE_ID --metrics $METRIC_NAMES --start-time $START --end-time $END --interval PT1M --aggregation Average Maximum --output json
```

### 2. Read service impact aggregates and merge owner timeline

Confirm AppRequests schema and sampling policy first; otherwise use an actual service adapter or owner supplied impact aggregates. Do not extract user IDs or infer distinct customers from request counts. Partition capped queries. Merge all observations into a UTC timeline retaining event IDs, source, precision and confidence.

```powershell
$KQL="AppRequests | where TimeGenerated >= datetime($START) and TimeGenerated < datetime($END) | where _ResourceId in~ (dynamic($RESOURCE_IDS_JSON)) | summarize requests=sum(ItemCount),failed=sumif(ItemCount,Success == false),duration_ms=avg(DurationMs) by _ResourceId,bin(TimeGenerated,1m)"
az monitor log-analytics query --subscription $SUB --workspace $WORKSPACE_GUID --timespan "$START/$END" --analytics-query $KQL --output json
Get-Content -Raw .\approved-response-timeline.json | ConvertFrom-Json
```

## Analysis rules

1. Separate impact start, first alert, human detection, response start, mitigation and verified recovery. User Closed state alone is not recovery evidence.
2. List changes before and during impact, but label causation as hypothesis until supported by the investigation. Include failed rollback or remediation attempts.
3. Estimate failed requests and affected workload time from actual telemetry, accounting for sampling and gaps. Customer count is null unless an authorized aggregate source establishes it.
4. Calculate detection and recovery intervals only when their endpoints are known, retaining uncertainty bounds instead of fabricated timestamps.
5. Create prevention actions with owner alias, due UTC date, expected verification evidence and priority. No tickets are automatically created or assigned.

## Known limits

- Azure control plane telemetry cannot establish every application or customer impact event.
- Temporal correlation alone does not identify root cause; response events may require owner records.

## Expected validation cases

- Healthy: verified recovery and owner timeline produce a consistent event sequence.
- Finding: mitigation predates recovery by 20 minutes and both are retained, not collapsed into one timestamp.
- Denied or missing: inaccessible request telemetry leaves customer impact null while known alert timeline remains reportable.

## Sources

- [Change timing and actor evidence](https://learn.microsoft.com/en-us/azure/governance/resource-graph/changes/get-resource-changes) (consulted 2026-10-21).
- [Alert history and condition transitions](https://learn.microsoft.com/en-us/javascript/api/@azure/arm-alertsmanagement/alertsoperations?view=azure-node-preview) (consulted 2026-10-21).
- [Validate reliability and recovery through evidence](https://learn.microsoft.com/en-us/azure/well-architected/reliability/reliability-test) (consulted 2026-10-21).
- [Application request sampling and impact fields](https://learn.microsoft.com/en-us/azure/azure-monitor/reference/tables/apprequests) (consulted 2026-10-21).
