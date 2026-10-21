# Evidence collection and analysis

## Collection

### 1. Four workload families

Page using --skip-token from skipToken. App Service CPU belongs primarily to its plan, requests to the site; do not duplicate plan cost across apps. Include legacy and enterprise Redis but do not assume identical metrics.

```azurecli
az graph query --subscriptions "<subscription_id>" --first 1000 -q "Resources | where type in~ ('microsoft.compute/virtualmachines','microsoft.web/sites','microsoft.web/serverfarms','microsoft.sql/servers/databases','microsoft.cache/redis','microsoft.cache/redisenterprise','microsoft.cache/redisenterprise/databases') | project id, name, type, resourceGroup, subscriptionId, sku, properties" --output json
```

### 2. Discover available utilization signals

Choose CPU percent for VMs and SQL; CPU percent or CPU time with a documented capacity conversion for App Service; connected clients for Redis; requests for sites. Retain supported units, aggregation, dimensions and metric time grains.

```azurecli
az monitor metrics list-definitions --subscription "<subscription_id>" --resource "<resource_id>" --output json
```

### 3. Seven day hourly average signals

The declared array loops over validated metric names and passes exactly one metric per call, preserving names containing spaces. Use only metrics supporting Average. For request counters, repeat with --aggregation Total instead and compare requests per complete hour. Split windows and dimension filters if response limits would omit series; unsupported metrics are Not assessed, not zero.

```azurecli
[string[]]$METRIC_NAMES = '<metric_names>' -split ','
foreach ($METRIC_NAME in $METRIC_NAMES) {
    az monitor metrics list --subscription "<subscription_id>" --resource "<resource_id>" --metrics $METRIC_NAME --start-time "<start_utc>" --end-time "<end_utc>" --interval PT1H --aggregation Average --output json
}
```

### 4. Monthly resource cost

Follow properties.nextLink and join by resource ID and currency. Shared App Service plan charges stay at plan scope, and unallocated SQL or Redis charges remain unattributed.

```azurecli
az rest --method post --subscription "<subscription_id>" --url "https://management.azure.com/subscriptions/<subscription_id>/providers/Microsoft.CostManagement/query?api-version=2025-03-01" --body '{"type":"Usage","timeframe":"Custom","timePeriod":{"from":"<month_start_utc>","to":"<month_end_utc>"},"dataset":{"granularity":"Daily","aggregation":{"totalCost":{"name":"PreTaxCost","function":"Sum"}},"grouping":[{"type":"Dimension","name":"ResourceId"}]}}' --output json
```

## Analysis rules

1. Build eligible resource counts for all four families, including plan/site relationships. Discover metrics for each type and explicitly report unsupported families and dimensions.
2. Calculate time weighted average CPU percent over valid hourly buckets and flag below 5 percent. Do not compare CPU time seconds directly with a percentage threshold.
3. For Redis use average connected clients below 10; for App Service requests use average complete hourly totals below 100. Apply thresholds only to applicable services, not an arbitrary OR across unrelated metrics.
4. Report coverage as valid buckets divided by expected buckets and maximum/peak when supplied. Below 90 percent coverage is Not assessed for a definitive low usage finding. A low seven day average is a review candidate, not proof of no business value.
5. Attach last complete month observed cost and currency. Distinguish monthly cost from estimated savings, which remains null until a feasible target configuration and current rates are validated.
6. Require workload owner review of scheduled, disaster recovery, latency and headroom needs before any resize or deletion plan.

## Known limits

- Seven days can miss monthly peaks, standby needs and business value; low usage is not authorization to stop a service.
- Metric availability, dimensions and aggregation differ by SKU and Redis generation; no universal connections or requests metric exists.

## Expected validation cases

- Healthy: VM CPU averages 35 percent with complete coverage and is not flagged.
- Finding: Redis connected clients average 2 with 100 percent coverage and monthly cost evidence produces a review candidate.
- Denied or missing: missing metrics or 40 percent bucket coverage returns Not assessed, never zero utilization.

## Sources

- [Metric definitions and metric reads](https://learn.microsoft.com/en-us/cli/azure/monitor/metrics?view=azure-cli-latest) (consulted 2026-10-21).
- [Monthly resource cost API](https://learn.microsoft.com/en-us/rest/api/cost-management/query/usage?view=rest-cost-management-2025-03-01) (consulted 2026-10-21).
- [Observed versus estimated cost](https://learn.microsoft.com/en-us/azure/cost-management-billing/costs/understand-cost-mgt-data) (consulted 2026-10-21).
- [Resource inventory](https://learn.microsoft.com/en-us/cli/azure/graph?view=azure-cli-latest) (consulted 2026-10-21).
