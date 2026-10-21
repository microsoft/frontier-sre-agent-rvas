# Evidence collection and analysis

## Collection

### 1. Approved hierarchy basis

Intersect descendants with approved_subscription_ids before collecting billing. Record child counts, exclusions and inaccessible nodes.

```azurecli
az account management-group show --name "<management_group_id>" --expand --recurse --subscription "<subscription_id>" --output json
```

### 2. Monthly report evidence at daily grain

Repeat per approved child, follow properties.nextLink with the original body only on the approved ARM host, and retain Currency and unattributed resource rows.

```azurecli
az rest --method post --subscription "<subscription_id>" --url "https://management.azure.com/subscriptions/<subscription_id>/providers/Microsoft.CostManagement/query?api-version=2025-03-01" --body '{"type":"Usage","timeframe":"Custom","timePeriod":{"from":"<start_utc>","to":"<end_utc>"},"dataset":{"granularity":"Daily","aggregation":{"totalCost":{"name":"PreTaxCost","function":"Sum"}},"grouping":[{"type":"Dimension","name":"ServiceName"},{"type":"Dimension","name":"ResourceId"}]}}' --output json
```

### 3. Subscription total reconciliation

Independent total prevents service or resource grouping omissions from appearing as savings. Follow all pages and preserve the Usage/PreTaxCost basis.

```azurecli
az rest --method post --subscription "<subscription_id>" --url "https://management.azure.com/subscriptions/<subscription_id>/providers/Microsoft.CostManagement/query?api-version=2025-03-01" --body '{"type":"Usage","timeframe":"Custom","timePeriod":{"from":"<start_utc>","to":"<end_utc>"},"dataset":{"granularity":"Daily","aggregation":{"totalCost":{"name":"PreTaxCost","function":"Sum"}}}}' --output json
```

## Analysis rules

1. Aggregate daily costs into the two complete months and reconcile grouped rows to independent subscription totals by currency. Show unresolved differences and coverage before any executive conclusion.
2. Calculate total monthly change per currency, then rank the top ten services by current month spend.
3. Rank the five fastest growing resources by absolute current minus prior cost; include percentage as a secondary measure and flag zero prior spend as new. Do not rank tiny baselines solely by percentage.
4. Represent non resource charges separately, sum each charge once, and do not add the service ranking to the resource ranking.
5. Write a generic leadership summary with amount, cost basis, month boundaries, approved cohort, principal drivers, confidence, owner recommendations and Sources. State that predicted causes and future savings are not demonstrated results.

## Known limits

- Usage cost can differ from invoiced or amortized cost and may change after collection.
- Subscriptions moved between management groups need historical snapshots to support historical boundary claims.

## Expected validation cases

- Healthy: grouped totals equal independent totals for both months and every approved child.
- Finding: a resource increases by 500 and appears in the top five absolute drivers.
- Denied or missing: one child is denied and the summary clearly says Partial, without presenting a complete management group total.

## Sources

- [Hierarchy CLI](https://learn.microsoft.com/en-us/cli/azure/account/management-group?view=azure-cli-latest) (consulted 2026-10-21).
- [Management group scope](https://learn.microsoft.com/en-us/azure/governance/management-groups/overview) (consulted 2026-10-21).
- [Grouped cost query](https://learn.microsoft.com/en-us/rest/api/cost-management/query/usage?view=rest-cost-management-2025-03-01) (consulted 2026-10-21).
- [Cost reporting semantics](https://learn.microsoft.com/en-us/azure/cost-management-billing/costs/understand-cost-mgt-data) (consulted 2026-10-21).
