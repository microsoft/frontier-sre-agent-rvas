# Evidence collection and analysis

## Collection

### 1. Workspace inventory

Retain resource ID, customerId, SKU, retention and region; intersect with approved workspace scope. A denied workspace remains in the coverage manifest.

```azurecli
az monitor log-analytics workspace list --subscription "<subscription_id>" --output json
```

### 2. Billable ingestion by table and day

Inspect QuantityUnit before conversion to decimal GB, do not assume every row uses bytes. Split by day if query limits or partial errors appear. Query charges may apply under the selected table plan.

```azurecli
az monitor log-analytics query --subscription "<subscription_id>" --workspace "<workspace_id>" --timespan "<start_utc>/<end_utc>" --analytics-query "Usage | where TimeGenerated >= datetime(<start_utc>) and TimeGenerated < datetime(<end_utc>) | where StartTime >= datetime(<start_utc>) and StartTime < datetime(<end_utc>) | summarize quantity=sum(Quantity) by day=bin(StartTime,1d), DataType, QuantityUnit, IsBillable | order by day asc" --output json
```

### 3. Table plan and retention configuration

Read each table's plan, analytics retention and total retention when returned. Table eligibility for Basic must be checked against supported table metadata/documentation, not inferred from high volume.

```azurecli
az monitor log-analytics workspace table list --subscription "<subscription_id>" --resource-group "<resource_group>" --workspace-name "<workspace_name>" --output json
```

## Analysis rules

1. For each workspace convert Usage quantities according to QuantityUnit and group daily billable and nonbillable GB by DataType. Rank the top five tables by billable ingestion over the full 30 days.
2. Show daily trends, valid observation days and any lag. Usage records describe ingestion accounting and should not be treated as a complete scan of every event table.
3. Calculate per table estimated ingestion cost only where the effective billing model and rate are available. Commitment tiers, Sentinel billing, free ingestion and included allowances can prevent exact marginal allocation; mark allocation method and keep unsupported table_cost null.
4. Consider Basic only for eligible tables after checking query frequency, alert/analytics dependencies, retention and feature requirements. High volume alone does not establish eligibility or savings.
5. Recommend shorter retention only when current table settings exceed the customer's legal and operational minimum. Do not claim shorter retention reduces ingestion cost, and distinguish analytics retention from total retention.
6. Present a local recommendation with table name, rationale, possible operational impact, owner and estimated change only where rates support it.

## Known limits

- Exact per table invoice allocation may be impossible with commitment tiers, Sentinel meters and shared allowances.
- Missing Usage history or unsupported Basic queries leaves the period unassessed; retention must not be shortened without compliance review.

## Expected validation cases

- Healthy: 30 days of Usage data with documented units reconcile and show five ranked tables.
- Finding: an eligible high volume table with verified lower cost and no incompatible dependencies becomes a Basic review candidate.
- Denied or missing: inaccessible Usage or unknown effective price produces null ingestion coverage or cost, not zero spend.

## Sources

- [Log Analytics CLI queries](https://learn.microsoft.com/en-us/cli/azure/monitor/log-analytics?view=azure-cli-latest) (consulted 2026-10-21).
- [Log ingestion billing, decimal GB and billing plans](https://learn.microsoft.com/en-us/azure/azure-monitor/logs/cost-logs) (consulted 2026-10-21).
