# Evidence collection and analysis

## Collection

### 1. All eight candidate families and their references

Preserve every page using skipToken and --skip-token. Include classic Front Door and Standard/Premium origin resources. A graph projection is an index, not sufficient evidence for a destructive conclusion.

```azurecli
az graph query --subscriptions "<subscription_id>" --first 1000 -q "Resources | where type in~ ('microsoft.compute/disks','microsoft.network/publicipaddresses','microsoft.network/networkinterfaces','microsoft.network/networksecuritygroups','microsoft.network/loadbalancers','microsoft.compute/snapshots','microsoft.network/applicationgateways','microsoft.network/frontdoors','microsoft.cdn/profiles','microsoft.cdn/profiles/afdendpoints','microsoft.cdn/profiles/origingroups','microsoft.cdn/profiles/origingroups/origins','microsoft.web/serverfarms','microsoft.web/sites') | project id, name, type, subscriptionId, resourceGroup, managedBy, properties, sku" --output json
```

### 2. Authoritative candidate and referenced source resource

Repeat for each candidate and an observed source disk reference only inside approved scope. Read actual attachment arrays and provider timeCreated/systemData metadata when returned. A repeatable authorized source 404 differs from a graph miss, denied read or transient failure.

```azurecli
az resource show --subscription "<subscription_id>" --ids "<resource_id>" --output json
```

### 3. Candidate metric definitions

Discover load balancer health/byte metrics and Application Gateway or Front Door requests with backend/origin dimensions. Retain unsupported metrics explicitly.

```azurecli
az monitor metrics list-definitions --subscription "<subscription_id>" --resource "<resource_id>" --output json
```

### 4. Backend traffic evidence

The declared array queries one validated metric per iteration and preserves spaces inside names. Use Total for bytes/requests, repeat with Average for a supported health metric. Split by documented backend dimensions rather than inferring unused pools from an aggregate endpoint. Missing dimension series are unknown.

```azurecli
[string[]]$METRIC_NAMES = '<metric_names>' -split ','
foreach ($METRIC_NAME in $METRIC_NAMES) {
    az monitor metrics list --subscription "<subscription_id>" --resource "<resource_id>" --metrics $METRIC_NAME --start-time "<start_utc>" --end-time "<end_utc>" --interval PT1H --aggregation Total --output json
}
```

### 5. Apps actually assigned to a plan

Join site serverFarmId to the plan including function apps represented as sites. Inspect app state rather than assuming stopped apps make a paid plan unnecessary. Graph count and CLI list must reconcile.

```azurecli
az appservice plan show --subscription "<subscription_id>" --resource-group "<resource_group>" --name "<plan_name>" --output json
az webapp list --subscription "<subscription_id>" --output json
```

### 6. Monthly cost attribution

Follow properties.nextLink, map columns and retain currencies. Shared charges and resource IDs without attribution remain unknown rather than zero.

```azurecli
az rest --method post --subscription "<subscription_id>" --url "https://management.azure.com/subscriptions/<subscription_id>/providers/Microsoft.CostManagement/query?api-version=2025-03-01" --body '{"type":"Usage","timeframe":"Custom","timePeriod":{"from":"<month_start_utc>","to":"<month_end_utc>"},"dataset":{"granularity":"Daily","aggregation":{"totalCost":{"name":"PreTaxCost","function":"Sum"}},"grouping":[{"type":"Dimension","name":"ResourceId"}]}}' --output json
```

## Analysis rules

1. Classify disks only when managedBy and all shared attachment references are empty and diskState is unattached. For public IPs check ipConfiguration, NAT gateway and other owner references; for NICs check VM and private endpoint ownership; for NSGs check both subnet and NIC association arrays.
2. For load balancers report zero healthy backends and zero processed bytes over seven complete days as distinct review signals. Require metric coverage and account for internal, HA and standby designs.
3. For snapshots require an observed creation timestamp older than 90 days and an absent source disk confirmed by a scoped resource read, not merely missing ARG rows. Retention and recovery ownership must be reviewed.
4. For Application Gateway pools and both Front Door generations require fourteen days of requests with backend/origin attribution. A zero aggregate or missing diagnostic stream does not establish every backend is unused.
5. For App Service plans distinguish zero assigned apps from all assigned apps stopped. Shared capacity, slots, function apps and restart plans can justify the plan; emit review candidates rather than deletion recommendations.
6. Join observed monthly cost by normalized resource ID and currency; report candidate_cost separately from confirmed_avoidable_cost. Without owner validation and a feasible removal plan confirmed avoidable cost remains null.
7. Keep age null when systemData.createdAt or a provider creation field is missing. Enumerate evidence and coverage for each of eight patterns and preserve denied subcases as Not assessed.

## Known limits

- Unattached or idle resources may be recovery assets, reserved endpoints or standby capacity; orphan candidates are not established waste.
- Backend metrics, source disk history and creation dates are not universally available. Empty queries and denied reads cannot prove absence.

## Expected validation cases

- Healthy: attached disks, referenced IPs and active backend traffic yield no orphan finding.
- Finding: unattached disk with confirmed empty shared attachments and billed cost becomes a review candidate, not confirmed waste.
- Denied or missing: a missing backend metric and a forbidden source disk read leave those two patterns Not assessed.

## Sources

- [Resource Graph inventory and paging](https://learn.microsoft.com/en-us/cli/azure/graph?view=azure-cli-latest) (consulted 2026-10-21).
- [Backend and traffic metric discovery](https://learn.microsoft.com/en-us/cli/azure/monitor/metrics?view=azure-cli-latest) (consulted 2026-10-21).
- [Observed resource cost](https://learn.microsoft.com/en-us/rest/api/cost-management/query/usage?view=rest-cost-management-2025-03-01) (consulted 2026-10-21).
- [Cost attribution limitations](https://learn.microsoft.com/en-us/azure/cost-management-billing/costs/understand-cost-mgt-data) (consulted 2026-10-21).
- [Confirm resource references with resource reads](https://learn.microsoft.com/en-us/cli/azure/resource?view=azure-cli-latest) (consulted 2026-10-21).
