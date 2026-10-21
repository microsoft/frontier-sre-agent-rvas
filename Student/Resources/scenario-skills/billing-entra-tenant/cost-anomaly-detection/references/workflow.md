# Evidence collection and analysis

## Collection

### 1. Daily resource and service costs

Read only query despite POST. Validate UUIDs, UTC dates and customer authorization in the host. Decode rows by returned columns, retain Currency, and follow properties.nextLink with the same body only on the approved management.azure.com host. Respect Retry-After and mark incomplete pages Partial.

```azurecli
az rest --method post --subscription "<subscription_id>" --url "https://management.azure.com/subscriptions/<subscription_id>/providers/Microsoft.CostManagement/query?api-version=2025-03-01" --body '{"type":"Usage","timeframe":"Custom","timePeriod":{"from":"<start_utc>","to":"<end_utc>"},"dataset":{"granularity":"Daily","aggregation":{"totalCost":{"name":"PreTaxCost","function":"Sum"}},"grouping":[{"type":"Dimension","name":"ResourceId"},{"type":"Dimension","name":"ServiceName"}]}}' --output json
```

### 2. Resource context

Retain id for pagination. Repeat unchanged with --skip-token from skipToken until exhausted; detect repeated tokens and any resultTruncated response without a usable token. Resource Graph absence is not deletion evidence.

```azurecli
az graph query --subscriptions "<subscription_id>" --first 1000 -q "Resources | project id, name, type, resourceGroup, subscriptionId, location, sku, tags" --output json
```

### 3. Changes in the observed window

Split UTC windows when the cap is reached, deduplicate eventDataId, retain denied intervals. This captures management changes, not all application activity.

```azurecli
az monitor activity-log list --subscription "<subscription_id>" --start-time "<start_utc>" --end-time "<end_utc>" --max-events 10000 --output json
```

## Analysis rules

1. Partition by subscription, resource ID, service and currency. Preserve unattributed charges as a separate bucket. Do not combine currencies or substitute missing rows with zero unless the fully reconciled billing extract establishes a true zero.
2. For each of the last seven complete days, compute the mean of the preceding 30 complete daily values, excluding the tested day. Calculate delta = observed minus mean and percentage = 100 * delta / mean. Flag absolute percentage above 20; if mean is zero report new spend with percentage null, not infinity.
3. Require 30 comparable baseline days for the requested test. Mark shorter histories Not assessed for the rolling test and report coverage. Flag provisional billing days separately from confirmed anomalies.
4. Aggregate the same daily rows by service and currency for service anomalies; do not add resource and service findings as separate spend.
5. Correlate cost onset with SKU, deployment and write events by resource ID and UTC time. Label causes hypotheses unless a change and its billing effect are demonstrated. Publish amount, direction, baseline, completeness and supporting events.

## Known limits

- Usage cost is not a finalized invoice and can be restated or delayed; no fixed customer completeness watermark is assumed.
- Activity Log does not prove workload usage or root cause, and Resource Graph may lag resource changes.

## Expected validation cases

- Healthy: 37 complete days at 100 currency units produce no deviation findings.
- Finding: a tested day at 150 against a 100 baseline produces a 50 absolute and 50 percent increase.
- Denied or missing: a denied subscription or 12 baseline days yields Not assessed, never a zero baseline.

## Sources

- [Cost Management Query Usage API](https://learn.microsoft.com/en-us/rest/api/cost-management/query/usage?view=rest-cost-management-2025-03-01) (consulted 2026-10-21).
- [Understand Cost Management data](https://learn.microsoft.com/en-us/azure/cost-management-billing/costs/understand-cost-mgt-data) (consulted 2026-10-21).
- [Resource Graph CLI and paging](https://learn.microsoft.com/en-us/cli/azure/graph?view=azure-cli-latest) (consulted 2026-10-21).
- [Activity Log scope and retention](https://learn.microsoft.com/en-us/azure/azure-monitor/fundamentals/activity-log) (consulted 2026-10-21).
