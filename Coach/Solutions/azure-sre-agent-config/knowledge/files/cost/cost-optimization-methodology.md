# Cost Optimization Methodology

Reference knowledge for the `cost-optimization-agent`. It defines the method, the data sources,
the de-duplication rules, and the Well-Architected guardrails the agent applies when reasoning
about Azure cost. The agent searches this document automatically when a cost question is in scope.

## Objective

Reduce Azure spend across a scope (subscription by default) **without degrading** the reliability,
performance, security, or compliance any workload requires. The agent is strictly **read-only**:
it produces prioritized recommendations with trade-offs; it never mutates a resource.

## The four data planes

Cost optimization is only credible when configuration, spend, utilization, and native
recommendations are correlated. Reason over all four, never one in isolation.

| Data plane | Question it answers | Tool / command |
| --- | --- | --- |
| Inventory + configuration | What exists, and how is it provisioned (SKU, tier, redundancy, tags)? | `RunAzCliReadCommands` → `az graph query` (Azure Resource Graph) |
| Actual spend | What does each resource group / service actually cost, and is it trending up? | `RunAzCliReadCommands` → `az rest` POST to `Microsoft.CostManagement/query` |
| Utilization / consumption | Is the resource actually used, or over-provisioned? | `QueryLogAnalyticsByWorkspaceId`, `QueryAppInsightsByResourceId`, `az monitor metrics list` |
| Native recommendations | What does Azure itself flag as idle, right-sizable, or commitment-eligible? | `RunAzCliReadCommands` → `az advisor recommendation list --category Cost` |

Business context (criticality, SLA, resiliency, performance, budget) is not an API: read it from
the `workload-cost-profiles` knowledge file before judging any candidate.

## The 8-step method

1. **Establish scope and business context.** Read `workload-cost-profiles`. Map each resource to a
   workload via resource group or tags. Unknown production defaults to business-critical
   (conservative).
2. **Inventory and configuration.** `az graph query` for every resource with SKU, tier,
   redundancy, and tags.
3. **Actual spend.** Cost Management Query for cost by resource group and service, `TheLastMonth`
   and `MonthToDate`; flag any group up more than ~20% versus the prior period.
4. **Utilization.** For each right-sizing or shutdown candidate, confirm low utilization from
   Monitor metrics / Log Analytics / App Insights **before** recommending a smaller SKU.
5. **Azure Advisor.** `az advisor recommendation list --category Cost` at subscription and per
   resource-group scope. Read-only; never pass `--refresh`. Capture `impactedValue`,
   `shortDescription`, `impact`, and `extendedProperties` savings.
6. **Correlate and de-duplicate.** Merge overlapping signals into a single recommendation; never
   double-count Advisor and configuration findings for the same resource.
7. **Apply Well-Architected guardrails.** Filter candidates against each workload's criticality,
   SLA, resiliency, performance, and budget (see below).
8. **Prioritized savings report.** One ranked table: action, evidence, estimated saving, risk,
   rollback, scope, decision criteria. Sort by impact × confidence.

## Advanced FinOps signals

Beyond spend, configuration, utilization, and Advisor, correlate these to see *where value per
euro is dropping* and *which commitments to make* (all read-only):

| Signal | What it answers | Tool / command |
| --- | --- | --- |
| Unit economics (cost-to-serve) | Is cost per transaction rising faster than volume? | App Insights `requests` count (`QueryAppInsightsByResourceId`) ÷ workload spend |
| Forecast (30/60/90) | Where is spend heading; will it breach budget? | `POST .../Microsoft.CostManagement/forecast?api-version=2025-03-01` |
| Budget variance | Actual + forecast vs the workload budget | `az consumption budget list` / `show` |
| Reservation / Savings Plan coverage and utilization | Are commitments under/over-used? Any expiring? Break-even? | `GET .../Microsoft.Consumption/reservationSummaries?api-version=2024-08-01&grain=monthly` + Advisor expiring-reservation finding |
| Cost allocation | Spend per team / environment / subscription | Cost Management Query `grouping` on `TagKey` (`team`, `env`) |

Interpretation: unit cost rising 18% while volume rises 4% points to structural waste
(over-provisioning, excessive retention, oversized DB, non-prod left running), not traffic growth.

## Action classification

Classify each recommendation so humans can route it (advisory only — this agent never executes):

| Class | Meaning |
| --- | --- |
| `low-risk / fast-track` | Reversible, dev-test, no SLA impact — fast human approval |
| `requires-approval` | Production or capability-affecting — owner / change approval |
| `strategic-commitment` | Reservation / savings plan — finance decision, break-even justified |
| `needs-more-data` | Insufficient evidence — gather more before deciding |

## Well-Architected Cost Optimization guardrails

The five WAF Cost Optimization design principles bound every recommendation
(https://learn.microsoft.com/en-us/azure/well-architected/cost-optimization/):

| Principle | What the agent does |
| --- | --- |
| Develop cost-management discipline | Tie spend to workloads and budgets; report budget adherence. |
| Design with a cost-efficiency mindset | Prefer the cheapest option that still meets the requirement. |
| Design for usage optimization | Eliminate waste first: idle, orphaned, over-provisioned, duplicate. |
| Design for rate optimization | Reservations, savings plans, commitment tiers, Basic logs — only for steady-state, profile-confirmed workloads. |
| Monitor and optimize over time | Recommend cadence/scope tuning; track recommendations across runs. |

**Order of preference:** eliminate waste → optimize rate → consolidate → only then reduce a
capability, and never below what the workload's criticality tier or compliance requires.

## De-duplication rules

Merge overlapping signals into one recommendation; do not double-count:

- Advisor "Consider Changing Pricing Tier" / "Basic logs" on a Log Analytics workspace **and** a
  retention review of the same workspace → one Log Analytics recommendation.
- Advisor "Right-size or shut down underutilized VM" **and** a low-CPU utilization finding for the
  same VM → one right-sizing recommendation, utilization as evidence.
- Advisor "reserved instance" **and** a steady-state spend pattern for the same service → one
  reservation/savings-plan recommendation.

## Confidence and prioritization

Score each recommendation by **impact × confidence**:

- Impact: estimated monthly saving (use Advisor `extendedProperties` when present; otherwise label
  "estimate, confirm with pricing workflow").
- Confidence: High when Advisor + utilization + configuration agree; Medium when two agree; Low
  when only one signal supports it.

## Escalation criteria

Escalate (flag for human decision, do not bury in the list) when a recommendation could:

- reduce redundancy/retention/capacity of a mission-critical workload;
- affect compliance-mandated retention or data residency;
- weaken DR/HA posture (zone or region redundancy);
- be blocked by a hard budget cap that would impair incident response.

When exact pricing is required, say so and point to a pricing / cost-analysis workflow rather than
guessing.

## References

- Azure Well-Architected — Cost Optimization: https://learn.microsoft.com/en-us/azure/well-architected/cost-optimization/
- Azure Advisor — Cost recommendations: https://learn.microsoft.com/en-us/azure/advisor/advisor-reference-cost-recommendations
- Cost Management — Query (Usage) REST API: https://learn.microsoft.com/en-us/rest/api/cost-management/query/usage
- Azure Resource Graph — Overview: https://learn.microsoft.com/en-us/azure/governance/resource-graph/overview
- Azure SRE Agent — Tools: https://learn.microsoft.com/en-us/azure/sre-agent/tools
- Azure SRE Agent — Pricing and billing: https://learn.microsoft.com/en-us/azure/sre-agent/pricing-billing
