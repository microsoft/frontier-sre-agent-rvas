---
title: Subscription Cost Optimization Review
summary: Review inventory, spend, utilization, and Azure Advisor findings. Rank savings opportunities against workload criticality and SLAs without changing resources.
phase: Scheduled
group: Proactive and scheduled operations
tags:
- FinOps
- Azure Advisor
- cost governance
highlight: false
---

# Challenge 18 — Subscription Cost Optimization Review

> **Application focus:** Infrastructure/platform only

> **Capability**: FinOps · Azure Advisor · Resource Graph · Cost governance

## Purpose

- Review cost opportunities using evidence and workload context, with no resource changes.
- Expected time: 25–30 minutes.

## Introduction

Review subscription costs without changing resources. Combine inventory, spend, utilization, and Azure Advisor findings into a prioritized savings table. Account for workload criticality and SLAs before recommending changes: reducing capacity can affect performance and reliability.

## Description

### Before you start

Confirm you have Cost Management read access on the subscription:

```bash
make check-cost-access
```

The script calls the Cost Management REST Query API directly. The optional Azure CLI
`costmanagement` extension has no `az costmanagement query` command.
An authorization error means your account needs Cost Management Reader access.
The script retries HTTP `429 Too Many Requests` responses with bounded backoff because
Cost Management applies several independent request quotas. Persistent throttling is a
service limit, not missing RBAC. Wait longer before running the challenge.

### Step 1 — Run the full optimization review

Paste the following prompt into the SRE Agent portal:

```text
Run a subscription-wide cost optimization review using the cost-optimization-methodology from the knowledge base. Identify the top savings opportunities across resource inventory, actual spend, utilization, and Azure Advisor recommendations. Cross-reference findings against workload cost profiles so that recommendations respect SLA and criticality constraints. Output a single prioritized savings table and an executive summary paragraph.

Recommend only — do not modify any Azure resource.
```

> The `cost-optimization` skill (`labs/01-azure-operations/resources/azure-sre-agent-config/skills/cost-optimization.md`) holds the ordered 8-step procedure and executable calls. The `cost-optimization-methodology.md` knowledge document holds guardrails, de-duplication rules, the confidence model, and escalation criteria. The prompt names the goal; these files supply the procedure and judgment criteria.

### Step 2 — Review the output

Evaluate the savings table:

- Are orphaned resources identified (unused public IPs, empty load balancers)?
- Are VM sizing recommendations grounded in actual utilization data?
- Do recommendations respect the workload cost profiles (e.g., production workloads are not recommended for B-series burstable VMs)?
- Is the Grubify hub Azure Firewall flagged, and if so, is the business context (hub connectivity) noted?

### Step 3 — Validate one recommendation

Pick the highest-confidence recommendation. Ask the agent to provide the evidence:

```text
For the top recommendation in the savings table, show me the underlying data: the resource, the current SKU/tier, the utilization metrics, and the Azure Advisor finding that supports it.
```

### Step 4 — Inspect the skill and scheduled task

In the portal, open **Skills → cost-optimization** and **Scheduled Tasks → cost-optimization-review**.

The scheduled task runs every Monday at 07:00 UTC (`cron: 0 7 * * 1`). The subagent (`cost-optimization-agent`) has **no write tools**, only read operations. The tool grant configuration enforces this, not the prompt.

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
- [ ] **Explain in your own words** (two or three written sentences) — why is a read-only posture the correct default for a cost optimization agent? What organizational change would be required before you trust an agent to autonomously right-size or delete production resources?

## Learning Resources

- [Azure Cost Management — query API](https://learn.microsoft.com/en-us/rest/api/cost-management/query)
- [Azure Advisor — cost recommendations](https://learn.microsoft.com/en-us/azure/advisor/advisor-cost-recommendations)
- [Azure Resource Graph — KQL queries](https://learn.microsoft.com/en-us/azure/governance/resource-graph/concepts/query-language)
- [Azure Reserved Instances overview](https://learn.microsoft.com/en-us/azure/cost-management-billing/reservations/save-compute-costs-reservations)
- [Azure Well-Architected — Cost Optimization pillar](https://learn.microsoft.com/en-us/azure/well-architected/cost-optimization/)

## Tips

- The `cost-optimization-methodology.md` knowledge document supplies business context. Check that recommendations account for dependencies, such as the firewall handling spoke egress.
- Azure Advisor's `--refresh` flag triggers a scan that takes several minutes. The review reads cached recommendations and never uses `--refresh`, which keeps the run fast and reproducible.
- Unit economics (cost per API request) require correlating Cost Management spend data with Application Insights request volume. The agent needs both data sources simultaneously, which is why the `cost-optimization` skill grants both `QueryLogAnalyticsByWorkspaceId` and `QueryAppInsightsByResourceId`.

## Hints and notes

> Hidden until you click. Expand a section only when you want it.

<details>
<summary><strong>Background</strong></summary>

- The specialist and cadence are `cost-optimization-agent`, task `cost-optimization-review`, cron `0 7 * * 1`.
- The evidence stack is workload cost profiles + Resource Graph inventory + Cost Management Query API + Azure Monitor utilization + Azure Advisor.
- By design, the agent only recommends and has no write tools.
- The sequence is inventory → spend → utilization → Advisor → de-duplicate → prioritized savings table.

</details>

<details>
<summary><strong>Expected Output</strong></summary>

- Agent produces a prioritized savings table with multiple recommendations and trade-offs.
- Recommendations reference workload context from cost knowledge docs.
- Every recommendation is evidence-supported; uncertain items are classified as needs-more-data.
- You can drill into evidence for the top recommendation.

</details>

<details>
<summary><strong>Common Issues and Hints</strong></summary>

- **Symptom:** Azure CLI reports that `costmanagement` is misspelled or unrecognized. **Fix:** use the challenge's `az rest` command. The optional `costmanagement` extension doesn't expose the Query API command.
- **Symptom:** Cost query permissions fail up front. **Fix:** confirm Cost Management Reader access before starting the challenge.
- **Symptom:** Cost Management returns HTTP 429. **Fix:** this is API throttling, not an RBAC failure. `make check-cost-access` retries with 30, 60, and 120-second delays. If it still fails, stop making requests and try later. For deeper diagnosis, inspect the response headers: `x-ms-ratelimit-microsoft.costmanagement-clienttype-retry-after` or `x-ms-ratelimit-microsoft.costmanagement-qpu-retry-after` gives the required backoff in seconds, while the corresponding `remaining` header identifies the exhausted quota.
- **Symptom:** Output is generic Advisor paraphrase. **Fix:** ask for utilization data and knowledge-doc context.
- **Symptom:** Agent suggests immediate deletes/resizes. **Fix:** the agent is read-only and should only recommend.
- **Symptom:** Duplicate recommendations appear. **Fix:** de-duplicate Advisor and inventory findings.
- **Symptom:** New subscription has insufficient cost or utilization history. **Fix:** accept a needs-more-data classification.

</details>

<details>
<summary><strong>Debrief Discussion Guide</strong></summary>

- Why is read-only the right default for cost optimization? → Financial and reliability risk from accidental downsizing or deletion.
- Why are workload cost profiles essential? → Technical savings without business context are often bad recommendations.
- What org change would be needed before enabling writes? → Trust, approvals, rollback, and ownership agreements.

</details>
