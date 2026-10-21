# Evidence collection and analysis

## Collection

### 1. Enumerate diagnostic capable resources

Run categories list for every approved inventory resource and continue ARG skip_token pages. A documented unsupported response is Not applicable; 403 is Not assessed, not unsupported. Keep categoryType and categoryGroups. Retry throttling with Retry-After and cap concurrency.

```powershell
az graph query --subscriptions $SUBS --first 1000 --graph-query 'Resources | project id,type,name,subscriptionId,resourceGroup' --output json
az monitor diagnostic-settings categories list --subscription $SUB --resource $RESOURCE_ID --output json
```

### 2. Read and expand settings against available log categories

Repeat for all resources with category support. Process full list response, retaining settings IDs, enabled logs, categoryGroup and destinations. Expand enabled allLogs or audit groups against the previously retrieved category membership before computing missing categories.

```powershell
az monitor diagnostic-settings list --subscription $SUB --resource $RESOURCE_ID --output json
```

## Analysis rules

1. Use only supported and successfully assessed resources in the coverage denominator and report unsupported and inaccessible counts separately.
2. A resource has complete log coverage only when the union of enabled log categories across settings covers the required available categories. Disabled entries do not count.
3. Report zero settings, partial categories and destination misconfiguration as separate findings. Preserve destination workspace or storage IDs internally and alias them for customer sharing.
4. Platform metrics are collected independently of diagnostic settings. Missing settings means absent configured export for those streams, not that platform metrics do not exist.

## Known limits

- Diagnostic category support varies by resource type and changes over time.
- A valid destination reference does not prove successful ingestion or sufficient retention.

## Expected validation cases

- Healthy: enabled allLogs covers every available log category.
- Finding: two of five available categories are enabled, giving partial log coverage.
- Denied or missing: categories call returns 403; resource is excluded from assessed denominator and retained as Not assessed.

## Sources

- [Diagnostic settings, category groups and automatically collected metrics](https://learn.microsoft.com/en-us/azure/azure-monitor/data-collection/diagnostic-settings) (consulted 2026-10-21).
