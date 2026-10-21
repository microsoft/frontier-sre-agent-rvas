# Evidence collection and analysis

## Collection

### 1. Resource group metadata

Retain group IDs and tags. Creation time is not guaranteed on group metadata; report null unless a trustworthy provider field or archived creation event exists.

```azurecli
az group list --subscription "<subscription_id>" --output json
```

### 2. Group membership

Count distinct ARM resource IDs per normalized resource group. A denied or incomplete inventory cannot prove a group is empty; include child resources only according to the stated counting method.

```azurecli
az resource list --subscription "<subscription_id>" --output json
```

### 3. Group cost

Follow every properties.nextLink and preserve Currency. Deleted resources can leave cost in an otherwise currently empty group.

```azurecli
az rest --method post --subscription "<subscription_id>" --url "https://management.azure.com/subscriptions/<subscription_id>/providers/Microsoft.CostManagement/query?api-version=2025-03-01" --body '{"type":"Usage","timeframe":"Custom","timePeriod":{"from":"<start_utc>","to":"<end_utc>"},"dataset":{"granularity":"Daily","aggregation":{"totalCost":{"name":"PreTaxCost","function":"Sum"}},"grouping":[{"type":"Dimension","name":"ResourceGroup"}]}}' --output json
```

## Analysis rules

1. Left join all approved resource groups with distinct current resource counts. Zero is valid only after the inventory is complete and authorized.
2. Flag zero resource groups and single resource groups as organizational review candidates, not automatically removable or mergeable; resource groups can be deliberate lifecycle, permission or deployment boundaries.
3. Apply customer approved temporary/test naming patterns only within documented production scope. Naming is a heuristic and must not override tags or owner confirmation.
4. Evaluate required tag presence, empty values and allowed values, preserving exemptions. Do not invent required tags from common conventions.
5. Attach monthly cost by group/currency and creation date only if proven. Recommend owner actions including retain, investigate or consolidation review, never execute a move or deletion.

## Known limits

- Empty resource groups can be intentional boundaries, and current resource count does not eliminate historical charges.
- Group creation timestamps are not uniformly available and naming alone cannot establish environment or ownership.

## Expected validation cases

- Healthy: multi resource group with compliant tags and production naming is not flagged.
- Finding: an empty production group named with the approved temporary pattern and missing CostCenter receives separate findings.
- Denied or missing: incomplete resource enumeration leaves count unknown rather than zero.

## Sources

- [Resource membership inventory](https://learn.microsoft.com/en-us/cli/azure/resource?view=azure-cli-latest) (consulted 2026-10-21).
- [Resource group cost query](https://learn.microsoft.com/en-us/rest/api/cost-management/query/usage?view=rest-cost-management-2025-03-01) (consulted 2026-10-21).
- [Resource group dependency and move considerations](https://learn.microsoft.com/en-us/azure/azure-resource-manager/management/move-resource-group-and-subscription) (consulted 2026-10-21).
