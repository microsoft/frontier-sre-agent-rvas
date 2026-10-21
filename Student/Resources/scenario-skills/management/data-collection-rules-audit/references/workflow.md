# Evidence collection and analysis

## Collection

### 1. Inspect all DCRs and association references

Derive DCR_RG and DCR_NAME from the approved DCR ID. Page ARG and association responses. Follow references only to separately approved source and destination IDs, including approved cross subscription destinations. Distinguish 404 deleted destinations from 403 unknown existence; obey Retry-After on 429. Inspect dataSources, destinations, dataFlows, streams and transformKql in raw properties.

```powershell
az graph query --subscriptions $SUBS --first 1000 --graph-query "Resources | where type =~ 'microsoft.insights/datacollectionrules' | project id,name,kind,properties,subscriptionId,resourceGroup" --output json
az monitor data-collection rule association list --subscription $SUB --resource-group $DCR_RG --rule-name $DCR_NAME --output json
az resource show --subscription $DESTINATION_SUB --ids $DESTINATION_WORKSPACE_ID --output json
```

### 2. Check actual stream tables for data freshness

Validate $TABLE against discovered schema and identifier syntax; never interpolate arbitrary text. Use this route only when the stream has _ResourceId. For direct ingestion or streams without it, query the confirmed attribution column or use supplied client delivery receipts; if no attribution exists, mark DCR specific flow unknown. Partition queries if capped and preserve partial errors.

```powershell
az monitor log-analytics workspace get-schema --subscription $DESTINATION_SUB --resource-group $DESTINATION_RG --workspace-name $DESTINATION_WORKSPACE --output json
$KQL="$TABLE | where TimeGenerated >= datetime($START) and TimeGenerated < datetime($END) | where _ResourceId in~ (dynamic($SOURCE_IDS_JSON)) | summarize rows=count(),last_seen=max(TimeGenerated) by _ResourceId"
az monitor log-analytics query --subscription $DESTINATION_SUB --workspace $WORKSPACE_GUID --timespan "$START/$END" --analytics-query $KQL --output json
```

## Analysis rules

1. Count distinct associated resource IDs and identify zero association rules, but do not call direct Logs Ingestion API rules orphaned solely because they need no DCRA.
2. List data sources, named destinations, stream routing and transformKql presence. A configured transform is not evidence it ran successfully.
3. Flag a deleted workspace only on authorized 404 evidence. Inaccessible destinations have null existence and are not confirmed deleted.
4. No rows in 24 hours is a delivery concern only for sources expected to emit during the window and when DCR attribution is credible. A workspace row can be delivered by another DCR.
5. Separate broken stream to destination references, idle sources and unavailable telemetry. Never equate sparse logs with a failed rule.

## Known limits

- DCR specific attribution is not available in every destination table.
- Zero DCRA count can be legitimate for direct ingestion or workspace transformation rules.

## Expected validation cases

- Healthy: expected sources have fresh attributed rows and all destinations exist.
- Finding: authorized GET confirms a referenced workspace is deleted.
- Denied or missing: unreadable workspace leaves last_data_at and destination existence null; a direct ingestion rule with no DCRA is not automatically orphaned.

## Sources

- [DCR concepts and collection routes](https://learn.microsoft.com/en-us/azure/azure-monitor/data-collection/data-collection-rule-overview) (consulted 2026-10-21).
- [List rule associations](https://learn.microsoft.com/en-us/cli/azure/monitor/data-collection/rule/association?view=azure-cli-latest) (consulted 2026-10-21).
