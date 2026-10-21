# Evidence collection and analysis

## Collection

### 1. Six month service series

Map returned column names, retain currency, follow every properties.nextLink using the original body and approved ARM host. Bound and deduplicate UTC dates at calendar edges. Split into monthly requests if the service rejects the full interval.

```azurecli
az rest --method post --subscription "<subscription_id>" --url "https://management.azure.com/subscriptions/<subscription_id>/providers/Microsoft.CostManagement/query?api-version=2025-03-01" --body '{"type":"Usage","timeframe":"Custom","timePeriod":{"from":"<start_utc>","to":"<end_utc>"},"dataset":{"granularity":"Daily","aggregation":{"totalCost":{"name":"PreTaxCost","function":"Sum"}},"grouping":[{"type":"Dimension","name":"ServiceName"}]}}' --output json
```

### 2. Independent period total

Reconciliation query without service grouping detects missing service rows and preserves charges with no service attribution. Follow nextLink, record denied months and the collection timestamp.

```azurecli
az rest --method post --subscription "<subscription_id>" --url "https://management.azure.com/subscriptions/<subscription_id>/providers/Microsoft.CostManagement/query?api-version=2025-03-01" --body '{"type":"Usage","timeframe":"Custom","timePeriod":{"from":"<start_utc>","to":"<end_utc>"},"dataset":{"granularity":"Daily","aggregation":{"totalCost":{"name":"PreTaxCost","function":"Sum"}}}}' --output json
```

## Analysis rules

1. Bucket UTC daily rows into six calendar months by currency, separately summing services and unallocated cost. Reconcile monthly sums to the independent totals with a declared decimal rounding tolerance.
2. Compute month to month absolute and percentage changes. A zero prior month has percentage null and a new spend label; a missing month has both cost and change null.
3. Rank the top three positive service contributions using final month minus first month cost, and also show each service's month to month contributions so a late spike is visible.
4. Report first to last growth and the full monthly series without extrapolating a seasonal pattern from only six observations. Label partial periods and historical retention gaps.
5. Keep Usage/PreTaxCost as the stated cost basis throughout; do not compare with amortized cost or a different billing currency.

## Known limits

- Six months do not establish annual seasonality or a reliable forecast.
- Historical visibility depends on agreement and accessible billing history; absent months are unknown, not free.

## Expected validation cases

- Healthy: six complete months with reconciled constant cost show zero growth.
- Finding: one service rises by 300 while others stay flat and is ranked first for growth contribution.
- Denied or missing: one inaccessible month remains null and the assessment is Partial.

## Sources

- [Cost query time periods and grouping](https://learn.microsoft.com/en-us/rest/api/cost-management/query/usage?view=rest-cost-management-2025-03-01) (consulted 2026-10-21).
- [Cost completeness and billing data](https://learn.microsoft.com/en-us/azure/cost-management-billing/costs/understand-cost-mgt-data) (consulted 2026-10-21).
