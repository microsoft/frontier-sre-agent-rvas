# Evidence collection and analysis

## Collection

### 1. Management group membership

Read hierarchy only after approval for this subtree. Enumerate descendant subscription IDs, intersect with approved_subscription_ids, record inaccessible or unapproved descendants as excluded, and never query them automatically.

```azurecli
az account management-group show --name "<management_group_id>" --expand --recurse --subscription "<subscription_id>" --output json
```

### 2. Current matched period

Repeat per approved descendant, follow properties.nextLink using the same body, map currency columns and retain the query basis and dates.

```azurecli
az rest --method post --subscription "<subscription_id>" --url "https://management.azure.com/subscriptions/<subscription_id>/providers/Microsoft.CostManagement/query?api-version=2025-03-01" --body '{"type":"Usage","timeframe":"Custom","timePeriod":{"from":"<start_utc>","to":"<end_utc>"},"dataset":{"granularity":"Daily","aggregation":{"totalCost":{"name":"PreTaxCost","function":"Sum"}}}}' --output json
```

### 3. Previous year matched period

Do not replace inaccessible historical costs with zero. Follow every nextLink, respect throttling and record retention failures.

```azurecli
az rest --method post --subscription "<subscription_id>" --url "https://management.azure.com/subscriptions/<subscription_id>/providers/Microsoft.CostManagement/query?api-version=2025-03-01" --body '{"type":"Usage","timeframe":"Custom","timePeriod":{"from":"<previous_start_utc>","to":"<previous_end_utc>"},"dataset":{"granularity":"Daily","aggregation":{"totalCost":{"name":"PreTaxCost","function":"Sum"}}}}' --output json
```

## Analysis rules

1. Build the approved current descendant cohort and report excluded children, denied children and total coverage. Historical membership is unknown unless a dated hierarchy snapshot is supplied; do not claim a historical like for like management group boundary.
2. For each subscription and currency, compare the matched elapsed periods using absolute delta and 100 * delta / previous. Zero previous gives a new spend finding and percentage null.
3. Highlight subscriptions above 25 percent increase. Retain decreases and new subscriptions rather than hiding them in the management group net total.
4. Produce management group subtotals separately for each currency. Never sum different currencies or invent a conversion rate.
5. Display current month to date labels, historical date boundaries and data completeness. If the requested last year month is inaccessible, emit Partial rather than a fabricated trend.

## Known limits

- Management group cost support depends on billing agreement, so this workflow uses child subscription queries instead.
- Current hierarchy does not establish last year's membership and historical billing data may be unavailable.

## Expected validation cases

- Healthy: two approved same currency children reconcile with flat year comparison.
- Finding: a child rises from 100 to 130 and is flagged above 25 percent.
- Denied or missing: a child has no last year data, retaining null prior cost and Partial coverage; mixed currencies stay separate.

## Sources

- [Management group hierarchy CLI](https://learn.microsoft.com/en-us/cli/azure/account/management-group?view=azure-cli-latest) (consulted 2026-10-21).
- [Management groups and billing support](https://learn.microsoft.com/en-us/azure/governance/management-groups/overview) (consulted 2026-10-21).
- [Subscription cost query](https://learn.microsoft.com/en-us/rest/api/cost-management/query/usage?view=rest-cost-management-2025-03-01) (consulted 2026-10-21).
- [Cost data availability](https://learn.microsoft.com/en-us/azure/cost-management-billing/costs/understand-cost-mgt-data) (consulted 2026-10-21).
