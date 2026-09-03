[< Previous Challenge](./Challenge-17.md) — **[Home](../README.md)** — [Next Challenge >](./Challenge-19.md)

# Challenge 18 — Subscription Cost Optimization Review

> **Capability**: FinOps · Azure Advisor · Resource Graph · Cost governance

## Introduction

Cost is a reliability metric. An overprovisioned environment wastes budget that could fund resilience improvements. An underprovisioned one risks performance degradation under load. And orphaned resources — disconnected NICs, empty load balancers, unused public IPs, stale snapshots — are both a cost problem and a security surface.

In this challenge you'll run a **subscription-wide cost optimization review**: from resource inventory through actual spend, utilization, and Azure Advisor recommendations, to a prioritized savings table — grounded in business context so that recommendations are actionable, not just technically correct.

## Description

### Before you start

Ensure you have Cost Management read access on the subscription:

```bash
az costmanagement query --scope "/subscriptions/$(az account show --query id -o tsv)" \
  --type Usage --timeframe MonthToDate \
  --dataset-aggregation '{"totalCost":{"name":"Cost","function":"Sum"}}' \
  -o table
```

### Step 1 — Run the full optimization review

Paste the following prompt into the SRE Agent portal:

```text
Run a subscription-wide cost optimization review using the cost-optimization-methodology from the knowledge base. Identify the top savings opportunities across resource inventory, actual spend, utilization, and Azure Advisor recommendations. Cross-reference findings against workload cost profiles so that recommendations respect SLA and criticality constraints. Output a single prioritized savings table and an executive summary paragraph.

Recommend only — do not modify any Azure resource.
```

> **Why a short prompt?** The ordered 8-step method and its executable calls live in the `cost-optimization` skill (`Student/Resources/azure-sre-agent-config/skills/cost-optimization.md`); the `cost-optimization-methodology.md` knowledge document holds the guardrails, de-duplication rules, confidence model, and escalation criteria used to judge each candidate. Splitting *how to find* (skill) from *how to judge* (knowledge doc) means both stay accurate independently as the lab evolves, and it demonstrates the core SRE Agent design principle: prompts describe the *goal*, skills define the *procedure*, and knowledge documents define the *judgment criteria*.

### Step 2 — Review the output

Evaluate the savings table:

- Are orphaned resources identified (unused public IPs, empty load balancers)?
- Are VM sizing recommendations grounded in actual utilization data?
- Do recommendations respect the workload cost profiles (e.g., production workloads are not recommended for B-series burstable VMs)?
- Is the Grubify hub Azure Firewall flagged — and if so, is the business context (hub connectivity) noted?

### Step 3 — Validate one recommendation

Pick the highest-confidence recommendation. Ask the agent to provide the evidence:

```text
For the top recommendation in the savings table, show me the underlying data: the resource, the current SKU/tier, the utilization metrics, and the Azure Advisor finding that supports it.
```

### Step 4 — Inspect the skill and scheduled task

In the portal, open **Skills → cost-optimization** and **Scheduled Tasks → cost-optimization-review**.

The scheduled task runs every Monday at 07:00 UTC (`cron: 0 7 * * 1`). Note that the subagent (`cost-optimization-agent`) has **no write tools** — only read operations. This read-only posture is enforced by the tool grant configuration, not by the prompt.

### Step 5 — Discuss governance

Ask the agent:

```text
If I asked you to implement one of these recommendations right now, could you? If not, what configuration change would be required, and what governance controls would you put in place before adding write access to the cost optimization agent?
```

## Success Criteria

- [ ] The agent produces a prioritized savings table with at least 5 distinct recommendations
- [ ] Recommendations are grounded in workload cost profiles (criticality and SLA are referenced)
- [ ] At least one orphaned or idle resource is identified
- [ ] Azure Advisor cost recommendations are included and de-duplicated against inventory findings
- [ ] The agent confirms it made no resource changes and all operations were read-only
- [ ] **Explain to your coach** — why is a read-only posture the correct default for a cost optimization agent? What organizational change would be required before you trust an agent to autonomously right-size or delete production resources?

## Learning Resources

- [Azure Cost Management — query API](https://learn.microsoft.com/en-us/rest/api/cost-management/query)
- [Azure Advisor — cost recommendations](https://learn.microsoft.com/en-us/azure/advisor/advisor-cost-recommendations)
- [Azure Resource Graph — KQL queries](https://learn.microsoft.com/en-us/azure/governance/resource-graph/concepts/query-language)
- [Azure Reserved Instances overview](https://learn.microsoft.com/en-us/azure/cost-management-billing/reservations/save-compute-costs-reservations)
- [Azure Well-Architected — Cost Optimization pillar](https://learn.microsoft.com/en-us/azure/well-architected/cost-optimization/)

## Tips

- The `cost-optimization-methodology.md` knowledge document contains the business-context framing that makes this review actionable. Without it, recommendations are technically correct but operationally naive (e.g., "downsize the firewall" without noting it handles all spoke egress).
- Azure Advisor's `--refresh` flag triggers a fresh scan that takes several minutes. The review prompt explicitly says never use `--refresh` — always read cached recommendations to keep the agent run fast and reproducible.
- Unit economics (cost per API request) require correlating Cost Management spend data with Application Insights request volume. The agent needs both data sources simultaneously, which is why the `cost-optimization` skill grants both `QueryLogAnalyticsByWorkspaceId` and `QueryAppInsightsByResourceId`.
