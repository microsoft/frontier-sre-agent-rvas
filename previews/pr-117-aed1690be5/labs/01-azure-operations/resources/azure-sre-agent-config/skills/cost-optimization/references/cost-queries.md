# Cost Analysis Query Reference

Executable calls for each step of the cost optimization procedure. Replace `<sub>`,
`<resource-group>`, `<resource-id>` and the date placeholders with real values. Every call here is
read-only.

## Step 2 — Inventory and configuration

```bash
az graph query --first 1000 -q "
Resources
| project name, type, kind, sku=sku.name, tier=sku.tier, location, resourceGroup, tags
| order by type asc"
```

## Step 3 — Actual spend

Cost by resource group and service. Run once with `TheLastMonth` and once with `MonthToDate` to
derive the trend.

```bash
az rest --method post \
  --url "https://management.azure.com/subscriptions/<sub>/providers/Microsoft.CostManagement/query?api-version=2025-03-01" \
  --headers "Content-Type=application/json" \
  --body '{
    "type": "ActualCost",
    "timeframe": "TheLastMonth",
    "dataset": {
      "granularity": "None",
      "aggregation": { "totalCost": { "name": "PreTaxCost", "function": "Sum" } },
      "grouping": [
        { "type": "Dimension", "name": "ResourceGroup" },
        { "type": "Dimension", "name": "ServiceName" }
      ]
    }
  }'
```

For line-item detail use `az consumption usage list`. Use `ExecutePythonCode` to aggregate large
responses and compute saving percentages.

## Step 3b — Forecast, budget variance and cost allocation

```bash
# Forecast, subscription scope, next 90 days
az rest --method post \
  --url "https://management.azure.com/subscriptions/<sub>/providers/Microsoft.CostManagement/forecast?api-version=2025-03-01" \
  --headers "Content-Type=application/json" \
  --body '{ "type": "ActualCost", "timeframe": "Custom",
    "timePeriod": { "from": "<today>", "to": "<today+90d>" },
    "dataset": { "granularity": "Daily", "aggregation": { "totalCost": { "name": "Cost", "function": "Sum" } } },
    "includeActualCost": true }'
```

```bash
# Budgets, read-only
az consumption budget list -o json
```

```bash
# Cost allocation by team and environment tags
az rest --method post \
  --url "https://management.azure.com/subscriptions/<sub>/providers/Microsoft.CostManagement/query?api-version=2025-03-01" \
  --headers "Content-Type=application/json" \
  --body '{ "type": "ActualCost", "timeframe": "TheLastMonth",
    "dataset": { "granularity": "None",
      "aggregation": { "totalCost": { "name": "PreTaxCost", "function": "Sum" } },
      "grouping": [ { "type": "TagKey", "name": "team" }, { "type": "TagKey", "name": "env" } ] } }'
```

## Step 4 — Utilization and consumption

```bash
az monitor metrics list --resource "<resource-id>" --metric "Percentage CPU" \
  --interval PT1H --aggregation Average --start-time "<iso>" --end-time "<iso>"
```

```kql
// Log Analytics ingestion by table, the dominant cost driver for observability
Usage
| where TimeGenerated > ago(30d)
| summarize IngestedGB = sum(Quantity) / 1000.0 by DataType
| order by IngestedGB desc
```

## Step 4b — Unit economics

```kql
// Business volume: successful requests over the period
requests
| where timestamp > ago(30d)
| summarize Transactions = count() by bin(timestamp, 1d)
```

Unit cost is the workload spend from Step 3 divided by transactions.

## Step 5 — Azure Advisor cost pass

```bash
az advisor recommendation list --category Cost -o json
az advisor recommendation list --category Cost -g <resource-group> -o json
```

Read-only. Never pass `--refresh`. For each recommendation extract `impactedValue`,
`shortDescription.problem`, `shortDescription.solution`, `impact` and `extendedProperties`, which
carries estimated savings such as `annualSavingsAmount`.

## Step 5b — Commitment analytics

```bash
# Reservation utilization, monthly grain: avgUtilizationPercentage, usedHours, reservedHours
az rest --method get \
  --url "https://management.azure.com/subscriptions/<sub>/providers/Microsoft.Consumption/reservationSummaries?api-version=2024-08-01&grain=monthly"
```
