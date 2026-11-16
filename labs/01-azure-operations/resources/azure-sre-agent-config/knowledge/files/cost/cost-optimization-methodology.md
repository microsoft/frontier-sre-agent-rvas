# Cost Optimization Methodology

Reference knowledge for cost reasoning: the guardrails, the de-duplication rules, the confidence
model, and the escalation criteria that bound every recommendation.

**This document does not contain the procedure.** The ordered method and the executable calls
belong to the `cost-optimization` skill, which owns them as a single source of truth. This document
answers *how to judge a candidate*; the skill answers *how to find one*.

## Objective

Reduce Azure spend across a scope, subscription by default, **without degrading** the reliability,
performance, security, or compliance any workload requires. The analysis is strictly **read-only**:
it produces prioritized recommendations with trade-offs; it never mutates a resource.

## The four data planes

Cost optimization is only credible when configuration, spend, utilization, and native
recommendations are correlated. Reason over all four, never one in isolation: configuration alone
shows what could be wasteful, spend alone shows what is expensive, and only their intersection
shows what is actually waste.

| Data plane | Question it answers | Why it is insufficient alone |
| --- | --- | --- |
| Inventory and configuration | What exists, and how is it provisioned in SKU, tier, redundancy and tags? | An oversized SKU that runs hot is not waste. |
| Actual spend | What does each resource group and service actually cost, and is it trending up? | A high bill can be correct for a critical workload. |
| Utilization and consumption | Is the resource actually used, or over-provisioned? | Low utilization can be a deliberate headroom or DR choice. |
| Native recommendations | What does Azure itself flag as idle, right-sizable, or commitment-eligible? | Advisor does not know the workload's criticality or compliance constraints. |

Business context, meaning criticality, SLA, resiliency, performance and budget, is not an API: read
it from the `workload-cost-profiles` knowledge file before judging any candidate.

## Advanced FinOps signals

Beyond spend, configuration, utilization and Advisor, these signals show *where value per euro is
dropping* and *which commitments to make*.

| Signal | What it answers |
| --- | --- |
| Unit economics, or cost-to-serve | Is cost per transaction rising faster than volume? |
| Forecast over 30, 60 and 90 days | Where is spend heading, and will it breach budget? |
| Budget variance | How does actual plus forecast compare against the workload budget? |
| Reservation and savings plan coverage and utilization | Are commitments under-used or over-used, are any expiring, and what is the break-even? |
| Cost allocation | What is the spend per team, environment or subscription? |

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
