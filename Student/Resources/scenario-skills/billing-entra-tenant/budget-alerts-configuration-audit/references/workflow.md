# Evidence collection and analysis

## Collection

### 1. CostCenter scope inventory

Page using --skip-token from skipToken. Select resource groups containing a nonempty CostCenter tag using customer approved tag key normalization. Retain all approved subscriptions in the denominator.

```azurecli
az graph query --subscriptions "<subscription_id>" --first 1000 -q "ResourceContainers | where type in~ ('microsoft.resources/subscriptions','microsoft.resources/subscriptions/resourcegroups') | project id, name, type, subscriptionId, tags" --output json
```

### 2. Subscription budgets

Capture amounts, timeGrain, active timePeriod, filters and every enabled notification threshold/type/recipient. The command is preview and billing agreement restrictions can cause Not assessed.

```azurecli
az consumption budget list --subscription "<subscription_id>" --output json
```

### 3. Resource group budgets

Repeat only for approved CostCenter groups. Do not assume a filtered subscription budget automatically satisfies the customer's requirement for an independent resource group budget.

```azurecli
az consumption budget list --subscription "<subscription_id>" --resource-group "<resource_group>" --output json
```

### 4. Three month spend baseline

Follow properties.nextLink, bind the resource group and Currency columns by returned names. Keep empty group charges in subscription totals but not allocated to a resource group.

```azurecli
az rest --method post --subscription "<subscription_id>" --url "https://management.azure.com/subscriptions/<subscription_id>/providers/Microsoft.CostManagement/query?api-version=2025-03-01" --body '{"type":"Usage","timeframe":"Custom","timePeriod":{"from":"<start_utc>","to":"<end_utc>"},"dataset":{"granularity":"Daily","aggregation":{"totalCost":{"name":"PreTaxCost","function":"Sum"}},"grouping":[{"type":"Dimension","name":"ResourceGroup"}]}}' --output json
```

## Analysis rules

1. For each approved subscription and CostCenter resource group, determine whether an active budget exists for the assessed period, its filters cover that scope and notifications are enabled.
2. Flag no applicable budget, no enabled notifications, or all enabled actual cost thresholds above 100 percent. Report exactly 100 percent separately as at limit, not above it. Distinguish forecast alerts from actual alerts.
3. Inspect recipient/action group references and missing destinations without sending a test notification. A configured address alone does not prove successful delivery.
4. Sum three complete months by scope and currency and propose amount = arithmetic mean * 1.20. New scopes or missing months have a null recommendation with the missing history reason.
5. Compare proposed and current amount in matching currency and cost basis. Subscription and resource group budgets overlap, so never add their amounts into one estate spend total.
6. Explain that budgets notify on evaluated costs and do not stop consumption. Recommend practical warning levels for owner review, never create budgets or change recipients.

## Known limits

- Budget availability and behavior depend on billing agreement, scope and currency; denied reads do not prove no budget.
- Budget evaluation is not instantaneous and a budget does not cap or stop resource consumption.

## Expected validation cases

- Healthy: active applicable budget with enabled 80 and 100 percent actual alerts passes coverage.
- Finding: only an enabled 120 percent alert produces a late warning finding; costs 100, 200 and 300 suggest 240.
- Denied or missing: denied budget listing is Not assessed; only two months of spend leaves recommended_amount null.

## Sources

- [Budget CLI and scope](https://learn.microsoft.com/en-us/cli/azure/consumption/budget?view=azure-cli-latest) (consulted 2026-10-21).
- [Budget thresholds, permissions and evaluation](https://learn.microsoft.com/en-us/azure/cost-management-billing/costs/tutorial-acm-create-budgets) (consulted 2026-10-21).
- [Historical scope cost baseline](https://learn.microsoft.com/en-us/rest/api/cost-management/query/usage?view=rest-cost-management-2025-03-01) (consulted 2026-10-21).
- [Scope tag inventory](https://learn.microsoft.com/en-us/cli/azure/graph?view=azure-cli-latest) (consulted 2026-10-21).
