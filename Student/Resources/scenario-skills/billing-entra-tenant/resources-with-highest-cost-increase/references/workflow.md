# Evidence collection and analysis

## Collection

### 1. Two week daily resource charges

Bind columns by name, retain Currency, follow properties.nextLink using the original query body and record completeness of each seven day interval.

```azurecli
az rest --method post --subscription "<subscription_id>" --url "https://management.azure.com/subscriptions/<subscription_id>/providers/Microsoft.CostManagement/query?api-version=2025-03-01" --body '{"type":"Usage","timeframe":"Custom","timePeriod":{"from":"<start_utc>","to":"<end_utc>"},"dataset":{"granularity":"Daily","aggregation":{"totalCost":{"name":"PreTaxCost","function":"Sum"}},"grouping":[{"type":"Dimension","name":"ResourceId"}]}}' --output json
```

### 2. Resource names and types

Page with --skip-token from skipToken until exhausted. Preserve cost rows without a current inventory match, including resources deleted since billing.

```azurecli
az graph query --subscriptions "<subscription_id>" --first 1000 -q "Resources | project id, name, type, subscriptionId, resourceGroup, location, sku" --output json
```

## Analysis rules

1. Split the fourteen days into adjacent equal seven day UTC windows, excluding the terminal boundary row if the API includes it.
2. Join week totals by normalized resource ID, subscription and currency, retaining new and removed resource costs. Distinguish a confirmed zero from an incomplete extract.
3. Compute absolute delta and percentage when previous week is nonzero. Rank the twenty largest positive absolute deltas per currency and separately mark increases above 30 percent.
4. Use ARG metadata where available; otherwise preserve the billing ID and derive name/type only if its ARM path parses, labeling that derivation.
5. Report unattributed charges outside the resource ranking and include total positive growth and negative offsets without declaring an operational root cause.

## Known limits

- Resource replacement or moving changes IDs and can appear as new spend.
- Week comparisons can be distorted by delayed charges and must show billing completeness.

## Expected validation cases

- Healthy: equal weekly costs produce no positive growth ranking.
- Finding: 100 to 140 produces delta 40, percentage 40 and the 30 percent marker.
- Denied or missing: missing previous week is null and excluded from numeric growth ranking, not treated as zero.

## Sources

- [Daily resource cost query](https://learn.microsoft.com/en-us/rest/api/cost-management/query/usage?view=rest-cost-management-2025-03-01) (consulted 2026-10-21).
- [Cost data updates](https://learn.microsoft.com/en-us/azure/cost-management-billing/costs/understand-cost-mgt-data) (consulted 2026-10-21).
- [Resource Graph CLI](https://learn.microsoft.com/en-us/cli/azure/graph?view=azure-cli-latest) (consulted 2026-10-21).
