# Evidence collection and analysis

## Collection

### 1. Historical environment cost

Billing tags, not current Resource Graph tags, determine this historical grouping. Retain empty tag buckets. Follow properties.nextLink and bind columns by name.

```azurecli
az rest --method post --subscription "<subscription_id>" --url "https://management.azure.com/subscriptions/<subscription_id>/providers/Microsoft.CostManagement/query?api-version=2025-03-01" --body '{"type":"Usage","timeframe":"Custom","timePeriod":{"from":"<start_utc>","to":"<end_utc>"},"dataset":{"granularity":"Daily","aggregation":{"totalCost":{"name":"PreTaxCost","function":"Sum"}},"grouping":[{"type":"TagKey","name":"Environment"}]}}' --output json
```

### 2. Current environment tag inventory

Follow skipToken using --skip-token without changing the query. Capture missing tags separately; a later tag edit must not retroactively relabel earlier costs.

```azurecli
az graph query --subscriptions "<subscription_id>" --first 1000 -q "Resources | project id, subscriptionId, resourceGroup, type, environment=tags.Environment, tags" --output json
```

## Analysis rules

1. Aggregate each complete month by normalized environment and currency; preserve original tag value and an untagged bucket. Reject comparisons that mix cost bases.
2. Compute each environment's ratio to production for the same period and currency. If production is zero or unavailable return ratio null with the reason.
3. Flag environment month growth above 15 percent, and combined development plus test spend above 30 percent of production. Also show separate development and test ratios to support the customer's interpretation.
4. Report unattributed cost share and present day missing tag counts. Do not apply resource group or subscription tags to resources as if they were automatically inherited.
5. Provide both raw values and normalized grouping so naming drift such as Prod versus Production is visible rather than hidden in a total.

## Known limits

- Not every charge supports tags, and current tags do not reconstruct historical billing attribution.
- Production spend can be absent or zero, making the requested ratio undefined.

## Expected validation cases

- Healthy: development plus test 20 against production 100 gives a 0.2 ratio with no ratio finding.
- Finding: development plus test 40 against production 100 triggers the 30 percent rule.
- Denied or missing: missing production costs produce null ratios and untagged costs remain visible.

## Sources

- [Cost query tag grouping](https://learn.microsoft.com/en-us/rest/api/cost-management/query/usage?view=rest-cost-management-2025-03-01) (consulted 2026-10-21).
- [Cost data and attribution limits](https://learn.microsoft.com/en-us/azure/cost-management-billing/costs/understand-cost-mgt-data) (consulted 2026-10-21).
- [Current resource tag inventory](https://learn.microsoft.com/en-us/cli/azure/graph?view=azure-cli-latest) (consulted 2026-10-21).
