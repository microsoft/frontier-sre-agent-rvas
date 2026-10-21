# Evidence collection and analysis

## Collection

### 1. Resource creation timestamps

Use the documented REST expansion and follow nextLink on the approved ARM host. Preserve missing timestamps as null. A provider update time or oldest visible event is not a substitute for creation time.

```azurecli
az rest --method get --subscription "<subscription_id>" --url "https://management.azure.com/subscriptions/<subscription_id>/resources?api-version=2021-04-01&%24expand=createdTime,changedTime" --output json
```

### 2. Retained management activity

Split any capped time slice and deduplicate events. Record exact readable bounds, failures and ingestion lag; native Activity Log retains 90 days, so do not promise older history.

```azurecli
az monitor activity-log list --subscription "<subscription_id>" --start-time "<start_utc>" --end-time "<end_utc>" --max-events 10000 --output json
```

### 3. Observed monthly cost

Follow properties.nextLink and retain currency. Empty billing rows are unknown until the period and scope reconcile.

```azurecli
az rest --method post --subscription "<subscription_id>" --url "https://management.azure.com/subscriptions/<subscription_id>/providers/Microsoft.CostManagement/query?api-version=2025-03-01" --body '{"type":"Usage","timeframe":"Custom","timePeriod":{"from":"<month_start_utc>","to":"<month_end_utc>"},"dataset":{"granularity":"Daily","aggregation":{"totalCost":{"name":"PreTaxCost","function":"Sum"}},"grouping":[{"type":"Dimension","name":"ResourceId"}]}}' --output json
```

## Analysis rules

1. Subtract age_months calendar months from end_utc with a documented month end rule, rather than approximating months as a fixed number of days.
2. Identify resources with known creation time before the cutoff. Unknown creation timestamps stay Not assessed for age regardless of resource name or first observed event.
3. Find successful /write operations for each normalized resource ID and report the latest observed management event separately from latest write. If none exist, latest_write is null with no write observed in the covered interval.
4. Flag old resources with no observed writes as decommission review candidates only when coverage is adequate. Explicitly state that stable resources can be heavily used on the data plane.
5. Join last complete monthly costs and currency, retaining unattributed cost as null. Owner review must include utilization, dependencies, recovery needs and business value before any retirement decision.

## Known limits

- No writes in Activity Log does not mean no reads, no data plane use or no business value.
- Native retention and provider timestamp gaps prevent lifetime activity reconstruction.

## Expected validation cases

- Healthy: an old resource with a recent successful write is not a no write candidate.
- Finding: a resource created 18 months ago with complete 90 day no write evidence becomes an owner review candidate.
- Denied or missing: missing creation time or a denied log interval blocks an asserted age plus no write finding.

## Sources

- [Documented resource creation timestamp expansion](https://learn.microsoft.com/en-us/rest/api/resources/resources/list?view=rest-resources-2021-04-01) (consulted 2026-10-21).
- [Activity Log retention and scope](https://learn.microsoft.com/en-us/azure/azure-monitor/fundamentals/activity-log) (consulted 2026-10-21).
- [Monthly resource cost](https://learn.microsoft.com/en-us/rest/api/cost-management/query/usage?view=rest-cost-management-2025-03-01) (consulted 2026-10-21).
