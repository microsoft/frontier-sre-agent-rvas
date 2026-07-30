# cost-optimization

Use this skill to analyze and optimize Azure cost across a scope (subscription by default).
Correlate inventory and configuration, actual spend, utilization, and Azure Advisor with each
workload's criticality, SLA, resiliency, performance, and budget, then propose prioritized,
read-only optimizations with trade-offs.

## Builder Upload Settings

| Field | Value |
| --- | --- |
| Skill name | `cost-optimization` |
| Description | Optimize Azure cost across a scope from inventory, spend, utilization, and Advisor, weighted by workload criticality and budget. |
| Recommended tools | `RunAzCliReadCommands`, `QueryLogAnalyticsByWorkspaceId`, `QueryAppInsightsByResourceId`, `ExecutePythonCode`, `GetAzCliHelp` |
| Recommended knowledge files | `cost/cost-optimization-methodology.md`, `cost/workload-cost-profiles.md`, `cost/azure-cost-levers-by-service.md` |
| Default run mode | Autonomous for read-only reporting; the skill never applies changes |

## Operating Principles

1. Cost optimization must not silently reduce reliability, performance, security, or compliance.
2. Reason over four data planes — inventory, spend, utilization, Advisor — never one in isolation.
3. Weight every recommendation against the workload's criticality, SLA, resiliency, performance,
   and budget (read `workload-cost-profiles`).
4. Eliminate waste first, then optimize rate, then consolidate; only then consider reducing a
   capability, and never below what the criticality tier or compliance requires.
5. Provide evidence, estimated saving, risk, rollback, and a decision criterion for each item.
6. Stay strictly read-only: propose, never apply.

## Trigger Conditions

Load this skill when the user asks to reduce Azure cost, explain a spend increase, right-size or
shut down resources, review reservations/savings plans, check budget adherence, or adapt an
environment from demo to production-like operations.

## Non-Goals

- Do not modify SKUs, retention, diagnostic settings, alert thresholds, or any resource.
- Do not recommend reducing redundancy, retention, or capacity below the workload's requirement.
- Do not optimize the Azure bill while ignoring MTTR, SLA, auditability, or DR posture.
- Do not produce exact invoices; for precise pricing use a dedicated pricing/cost-analysis workflow.

## Procedure

### Step 1 — Establish scope and business context

Read `workload-cost-profiles`. Map each resource to a workload by resource group or tag. Record
criticality tier, SLA, resiliency, performance need, and budget. Treat unknown production as
business-critical.

### Step 2 — Inventory and configuration (Azure Resource Graph)

```bash
az graph query --first 1000 -q "
Resources
| project name, type, kind, sku=sku.name, tier=sku.tier, location, resourceGroup, tags
| order by type asc"
```

Flag obvious waste: resources with no dependents, premium SKUs in dev-test, GRS/ZRS where the
profile allows LRS.

### Step 3 — Actual spend (Cost Management Query API)

Cost by resource group and service, last month and month-to-date. Compare to flag anomalies.

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

Re-run with `"timeframe": "MonthToDate"` to derive the trend. Flag any resource group up more than
~20% versus the prior period. Use `ExecutePythonCode` to aggregate large responses and compute
saving percentages. For line-item detail, `az consumption usage list`.

### Step 3b — Forecast, budget variance, and cost allocation

Forecast the next 30/60/90 days and compare to budget; allocate spend by team and environment.

```bash
# Forecast (subscription scope, next 90 days)
az rest --method post \
  --url "https://management.azure.com/subscriptions/<sub>/providers/Microsoft.CostManagement/forecast?api-version=2025-03-01" \
  --headers "Content-Type=application/json" \
  --body '{ "type": "ActualCost", "timeframe": "Custom",
    "timePeriod": { "from": "<today>", "to": "<today+90d>" },
    "dataset": { "granularity": "Daily", "aggregation": { "totalCost": { "name": "Cost", "function": "Sum" } } },
    "includeActualCost": true }'

# Budgets (read-only)
az consumption budget list -o json

# Cost allocation by team and environment tags
az rest --method post \
  --url "https://management.azure.com/subscriptions/<sub>/providers/Microsoft.CostManagement/query?api-version=2025-03-01" \
  --headers "Content-Type=application/json" \
  --body '{ "type": "ActualCost", "timeframe": "TheLastMonth",
    "dataset": { "granularity": "None",
      "aggregation": { "totalCost": { "name": "PreTaxCost", "function": "Sum" } },
      "grouping": [ { "type": "TagKey", "name": "team" }, { "type": "TagKey", "name": "env" } ] } }'
```

Compute budget variance (actual + forecast vs budget amount) with `ExecutePythonCode`.

### Step 4 — Utilization / consumption

Confirm low utilization before any right-sizing or shutdown.

```bash
az monitor metrics list --resource "<resource-id>" --metric "Percentage CPU" \
  --interval PT1H --aggregation Average --start-time "<iso>" --end-time "<iso>"
```

```kql
// Log Analytics ingestion by table (cost driver), last 30 days
Usage
| where TimeGenerated > ago(30d)
| summarize IngestedGB = sum(Quantity) / 1000.0 by DataType
| order by IngestedGB desc
```

Use `QueryAppInsightsByResourceId` to confirm an app's throughput/latency tolerates a smaller SKU.

### Step 4b — Unit economics (cost-to-serve)

Divide workload spend by business volume to expose structural waste hidden by volume growth.

```kql
// Business volume: successful requests over the period (Application Insights)
requests
| where timestamp > ago(30d)
| summarize Transactions = count() by bin(timestamp, 1d)
```

Unit cost = workload spend (Step 3) ÷ Transactions. Flag when unit cost rises materially while
volume is flat — e.g. unit cost +18% with volume +4% indicates over-provisioning, excessive
retention, an oversized database, or non-production left running, not traffic growth.

### Step 5 — Azure Advisor cost pass

```bash
az advisor recommendation list --category Cost -o json                 # subscription scope
az advisor recommendation list --category Cost -g <resource-group> -o json
```

Read-only; never pass `--refresh`. For each recommendation extract `impactedValue`,
`shortDescription.problem`/`.solution`, `impact`, and `extendedProperties` (estimated savings such
as `annualSavingsAmount`). Subscription-scope items include reservations and savings plans.

### Step 5b — Commitment analytics (coverage, utilization, break-even)

Assess existing reservations and savings plans before recommending new commitments.

```bash
# Reservation utilization (monthly grain): avgUtilizationPercentage, usedHours/reservedHours
az rest --method get \
  --url "https://management.azure.com/subscriptions/<sub>/providers/Microsoft.Consumption/reservationSummaries?api-version=2024-08-01&grain=monthly"
```

Report coverage and utilization, flag low-utilization commitments and ones expiring soon (Advisor
"Configure automatic renewal for the expiring reservations"), and for any *new* reservation or
savings plan compute the break-even period (commitment cost vs on-demand savings) with
`ExecutePythonCode`. Recommend commitments only for workloads the profile marks steady-state.

### Step 6 — Correlate and de-duplicate

Merge overlapping signals (Advisor + configuration + utilization for the same resource) into one
recommendation. Never double-count. See `cost-optimization-methodology` for the merge rules.

### Step 7 — Apply Well-Architected guardrails

For each candidate, check `workload-cost-profiles` and `azure-cost-levers-by-service`:

- `dev-test` → aggressive right-sizing, off-hours shutdown, LRS, shortest retention.
- `business` → right-size on confirmed low utilization; rate optimization; keep required redundancy.
- `mission-critical` → rate optimization only; never reduce redundancy/retention/capacity/DR.

### Step 8 — Prioritized savings report

Produce the report in the Output Format below, sorted by impact × confidence.

## Recommendation Framework

For each recommendation provide:

| Field | Required content |
| --- | --- |
| Recommendation | What to change or investigate |
| Evidence | Advisor finding, spend figure, or utilization metric |
| Benefit | Estimated monthly/annual saving (or labelled estimate) |
| Risk | What capability could be reduced |
| Rollback | How to revert |
| Scope | Resource, resource group, or subscription setting |
| Decision criteria | When the recommendation is appropriate |
| Payback period | Time for the saving to repay any implementation effort |
| Implementation effort | Relative effort to apply (low / medium / high) |
| Reversibility | How easily the change can be rolled back |
| Confidence | High / Medium / Low based on signal agreement |
| Classification | `low-risk / fast-track` · `requires-approval` · `strategic-commitment` · `needs-more-data` (advisory only) |

## Output Format

```markdown
## Cost Optimization Review — <scope> — <date>

### Posture
- Current monthly run rate / forecast (30/60/90):
- Total actual spend (last month / MTD):
- Top cost services / resource groups / teams:
- Unit economics (cost per transaction + trend):
- Reservation / Savings Plan coverage and utilization:
- Azure Advisor cost recommendations (High/Medium/Low):
- Budget adherence and variance (per workload):

### Findings
| Finding | Evidence | Workload | Criticality | Confidence |
| --- | --- | --- | --- | --- |

### Prioritized Recommendations
| # | Recommendation | Benefit (€/mo, €/yr) | Payback | Effort | Reversibility | Risk | Rollback | Scope | Class |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |

### Anomalies
| Resource group / unit | Δ vs prior period | Likely cause |
| --- | --- | --- |

### Decision
<what to do now vs later, respecting criticality and budget>

---

## Executive Value Summary

- Current monthly run rate:
- Forecast (next period):
- Potential annualized savings:
- Safe short-term savings (low-risk / fast-track):
- Top 3 decisions this week (value, risk, owner):

### References
<official sources + workload profile rows used>
```

## Escalation Criteria

Escalate when a recommendation could reduce a mission-critical workload's redundancy/retention/
capacity, affect compliance retention or data residency, weaken DR/HA, or when a hard budget cap
could impair incident response. When exact cost numbers are required, use a pricing/cost-analysis
workflow rather than estimating here.

## Official References

- Azure Advisor — Cost recommendations: https://learn.microsoft.com/en-us/azure/advisor/advisor-reference-cost-recommendations
- az advisor recommendation: https://learn.microsoft.com/en-us/cli/azure/advisor/recommendation
- Cost Management — Query (Usage) REST API: https://learn.microsoft.com/en-us/rest/api/cost-management/query/usage
- Cost Management — Forecast (Usage) REST API: https://learn.microsoft.com/en-us/rest/api/cost-management/forecast/usage
- Consumption — Reservation Summaries (utilization): https://learn.microsoft.com/en-us/rest/api/consumption/reservations-summaries/list
- az consumption budget: https://learn.microsoft.com/en-us/cli/azure/consumption/budget
- Azure SRE Agent — Send notifications (Outlook/Teams): https://learn.microsoft.com/en-us/azure/sre-agent/send-notifications
- az consumption usage: https://learn.microsoft.com/en-us/cli/azure/consumption/usage
- Cost Management — Assign access to data (RBAC): https://learn.microsoft.com/en-us/azure/cost-management-billing/costs/assign-access-acm-data
- Azure Resource Graph — Overview: https://learn.microsoft.com/en-us/azure/governance/resource-graph/overview
- Well-Architected — Cost Optimization: https://learn.microsoft.com/en-us/azure/well-architected/cost-optimization/
- Azure SRE Agent — Tools: https://learn.microsoft.com/en-us/azure/sre-agent/tools
- Azure SRE Agent — Pricing and billing: https://learn.microsoft.com/en-us/azure/sre-agent/pricing-billing
- Azure SRE Agent — Permissions: https://learn.microsoft.com/en-us/azure/sre-agent/permissions

## Related Skills

- `traffic-analytics-kql-analysis`
- `vnet-flow-logs-and-ingestion`
- `rbac-and-resource-access-check`
