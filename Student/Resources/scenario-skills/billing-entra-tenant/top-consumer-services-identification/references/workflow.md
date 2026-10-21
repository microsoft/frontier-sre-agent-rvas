# Evidence collection and analysis

## Collection

### 1. Daily service costs for ranking and comparison

Retain all returned columns and currencies, follow properties.nextLink with the same body, and record missing approved subscriptions explicitly.

```azurecli
az rest --method post --subscription "<subscription_id>" --url "https://management.azure.com/subscriptions/<subscription_id>/providers/Microsoft.CostManagement/query?api-version=2025-03-01" --body '{"type":"Usage","timeframe":"Custom","timePeriod":{"from":"<start_utc>","to":"<end_utc>"},"dataset":{"granularity":"Daily","aggregation":{"totalCost":{"name":"PreTaxCost","function":"Sum"}},"grouping":[{"type":"Dimension","name":"ServiceName"}]}}' --output json
```

### 2. Current instance inventory

Page unchanged via --skip-token from skipToken until complete. Count distinct IDs locally rather than summarized rows that can obscure paging. Current inventory is not a historic month snapshot.

```azurecli
az graph query --subscriptions "<subscription_id>" --first 1000 -q "Resources | project id, name, type, subscriptionId, resourceGroup, kind" --output json
```

## Analysis rules

1. Sum the last 30 complete days by service and currency across only approved subscriptions and rank ten descending per currency.
2. For each ranked service, report current calendar month to date, previous full calendar month, and previous month through the same elapsed day. Show full versus partial comparison labels and use the aligned periods for the primary percentage change.
3. Calculate percentage only for nonzero previous cost, retaining absolute changes and new spend when zero. Do not silently combine credits with gross usage amounts from another cost basis.
4. Count distinct current resources only through the reviewed service to type mapping. Shared services, marketplace charges and deleted resources can make billed service and instance count non equivalent; report null rather than infer from service names.
5. Show missing subscriptions and unmapped service costs next to the ranking so an apparently small service cannot be treated as complete estate coverage.

## Known limits

- Billing services are not necessarily one to one with ARM resource types or instances.
- A current month and a previous full month are not directly comparable without elapsed day alignment.

## Expected validation cases

- Healthy: eleven services with distinct costs return the ten largest for each currency.
- Finding: a service doubles on matched elapsed days and reports 100 percent growth.
- Denied or missing: service mapping absent leaves instance_count null; a denied subscription makes ranking Partial.

## Sources

- [Cost Query API](https://learn.microsoft.com/en-us/rest/api/cost-management/query/usage?view=rest-cost-management-2025-03-01) (consulted 2026-10-21).
- [Cost data semantics](https://learn.microsoft.com/en-us/azure/cost-management-billing/costs/understand-cost-mgt-data) (consulted 2026-10-21).
- [Resource inventory query and pagination](https://learn.microsoft.com/en-us/cli/azure/graph?view=azure-cli-latest) (consulted 2026-10-21).
