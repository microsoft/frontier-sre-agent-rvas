# Evidence collection and analysis

## Collection

### 1. Discover queryable tables and workspace GUID

Set $WORKSPACE_GUID from customerId. Confirm AppTraces SeverityLevel, Message, Properties and _ResourceId columns exist. If only legacy traces, Syslog or AzureDiagnostics exists, map that table's actual schema explicitly; Syslog severity has different semantics and must not use the same numeric comparison.

```powershell
az monitor log-analytics workspace show --subscription $SUB --resource-group $RG --workspace-name $WORKSPACE --query customerId --output tsv
az monitor log-analytics workspace get-schema --subscription $SUB --resource-group $RG --workspace-name $WORKSPACE --output json
```

### 2. Aggregate errors and sample the five largest patterns

Validate identifiers and ISO timestamps before interpolation; encode approved IDs as JSON, not executable KQL. Also run the same aggregation without take 5 for full pattern counts, partitioning by time and resource when result caps are reached, then merge counts and deduplicate boundary events. No generic continuation exists for Log Analytics query results; retry 429, disclose partial query errors and redact samples before delivery.

```powershell
$KQL="AppTraces | where TimeGenerated >= datetime($START) and TimeGenerated < datetime($END) | where tolower(_ResourceId) in~ (dynamic($RESOURCE_IDS_JSON)) | where SeverityLevel >= 3 | extend error_code=tostring(Properties['ErrorCode']), pattern=replace_regex(Message, @'[0-9]+', '#') | summarize event_count=count(), represented_count=sum(ItemCount), samples=make_set(substring(Message,0,500),3) by _ResourceId,error_code,pattern | order by event_count desc | take 5"
az monitor log-analytics query --subscription $SUB --workspace $WORKSPACE_GUID --timespan "$START/$END" --analytics-query $KQL --output json
```

## Analysis rules

1. Interpret SeverityLevel >= 3 only for the documented Application Insights severity mapping. State the exact table and schema adapter used.
2. Group by resource, error code and normalized message pattern; missing ErrorCode is empty or unknown, not an invented code. Preserve counts for all patterns and examples for the five largest.
3. Separate observed row count from sampled represented telemetry count using ItemCount. Do not infer total application errors if sampling coverage is unknown.
4. Strip credentials, personal data and customer content from sample messages. A query returning zero with confirmed telemetry coverage is different from a missing table or denied workspace.

## Known limits

- Log Analytics tables are not interchangeable; unsupported schemas require a reviewed adapter.
- Row caps, sampling and retention can prevent complete counts; absent or denied data is null.

## Expected validation cases

- Healthy: accessible table with ingestion in window returns no severity three or higher events.
- Finding: two messages differing only in request numbers form one pattern and produce redacted examples.
- Denied or missing: missing AppTraces table is Not assessed until an actual supported table is mapped.

## Sources

- [AppTraces schema](https://learn.microsoft.com/en-us/azure/azure-monitor/reference/tables/apptraces) (consulted 2026-10-21).
- [Workspace schema discovery](https://learn.microsoft.com/en-us/cli/azure/monitor/log-analytics/workspace?view=azure-cli-latest) (consulted 2026-10-21).
