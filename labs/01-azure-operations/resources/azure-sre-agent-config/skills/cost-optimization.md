---
name: cost-optimization
description: Analyze and optimize Azure cost across a scope using resource inventory and configuration, actual spend, utilization, and Azure Advisor, weighted by each workload's criticality, SLA, resiliency, performance, and budget. Recommendations only; never modifies resources.
---

# cost-optimization

Use this skill to analyze and optimize Azure cost across a scope (subscription by default).
Correlate inventory and configuration, actual spend, utilization, and Azure Advisor with each
workload's criticality, SLA, resiliency, performance, and budget, then propose prioritized,
read-only optimizations with trade-offs.

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

Every executable call for the steps below lives in
`cost-optimization/references/cost-queries.md`, which is the exact name the file is registered
under. Read it when you need a call. The steps here define what to establish and why, which is
what determines whether a saving is real.

### Step 1 — Establish scope and business context

Read `workload-cost-profiles`. Map each resource to a workload by resource group or tag. Record
criticality tier, SLA, resiliency, performance need, and budget. Treat unknown production as
business-critical.

### Step 2 — Inventory and configuration (Azure Resource Graph)

Inventory every resource with its SKU, tier, location and tags. Flag obvious waste: resources with
no dependents, premium SKUs in dev-test, GRS or ZRS where the profile allows LRS.

### Step 3 — Actual spend (Cost Management Query API)

Get cost by resource group and service for the last full month and for month-to-date, then compare
the two to expose anomalies. Flag any resource group up more than roughly 20% versus the prior
period. Configuration alone never proves waste: spend does.

### Step 3b — Forecast, budget variance, and cost allocation

Forecast the next 30, 60 and 90 days, compare against the budget, and allocate spend by team and
environment. Compute budget variance as actual plus forecast against the budget amount with
`ExecutePythonCode`.

### Step 4 — Utilization / consumption

Confirm low utilization before proposing any right-sizing or shutdown. A resource that looks
oversized on paper but runs hot is not waste. Use `QueryAppInsightsByResourceId` to confirm that an
application's throughput and latency tolerate a smaller SKU.

### Step 4b — Unit economics (cost-to-serve)

Divide workload spend by business volume to expose structural waste that volume growth would
otherwise hide. Unit cost is workload spend from Step 3 divided by transactions. Flag when unit
cost rises materially while volume is flat: unit cost up 18% with volume up 4% indicates
over-provisioning, excessive retention, an oversized database, or non-production left running, not
traffic growth.

### Step 5 — Azure Advisor cost pass

Collect Advisor cost recommendations at subscription and resource-group scope. Subscription-scope
items include reservations and savings plans.

### Step 5b — Commitment analytics (coverage, utilization, break-even)

Assess existing reservations and savings plans before recommending new ones. Report coverage and
utilization, flag low-utilization commitments and ones expiring soon, and for any new reservation
or savings plan compute the break-even period, commitment cost against on-demand savings, with
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
