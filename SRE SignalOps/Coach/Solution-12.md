[< Previous Solution](./Solution-11.md) | **[Home](./README.md)** | [Next Solution >](./Solution-13.md)

# Coach Guide — Challenge 12: Proactive Tenant Optimization

## Purpose

- Teach evidence-backed, read-only optimization before operational issues become incidents.
- Balance cost, reliability, observability, resilience, and governance instead of optimizing one dimension blindly.
- Expected time: 20–25 minutes.

## Mini-Lecture (5 min before challenge)

- Optimization is broader than cost reduction; missing protection and stale observability are tenant risks.
- Good recommendations combine inventory, spend, utilization, Advisor, monitoring, and workload context.
- De-duplication prevents one underlying issue from appearing as several recommendations.
- Read-only is the correct default until ownership, approval, rollback, and validation are explicit.

## Expected Student Output

- A declared subscription and resource scope.
- At least three prioritized recommendations supported by multiple evidence sources.
- Trade-offs, confidence, effort, owner, and expected value for each recommendation.
- A recurring review cadence with approval boundaries.

## Coach Runbook

1. Require the student to declare subscriptions, resource groups, time window, and inaccessible evidence before analysis.
2. Check that each recommendation uses at least two evidence planes and names the affected resource and owner.
3. Ask for value, risk, confidence, effort, trade-off, approval, rollback, and validation for every recommendation.
4. End by confirming no writes occurred and no recommendation bypasses workload criticality or recovery objectives.

## Common Issues and Hints

- **Symptom:** The report only paraphrases Azure Advisor. **Fix:** require inventory, utilization, backup, alert, and telemetry-freshness evidence.
- **Symptom:** Cost data is unavailable. **Fix:** report the permission gap and continue with technical optimization evidence.
- **Symptom:** The agent recommends deleting or downsizing a critical resource. **Fix:** apply the knowledge document’s criticality and recovery objectives before prioritization.
- **Symptom:** Duplicate findings dominate the list. **Fix:** group findings by affected resource and underlying cause.

## Debrief Discussion Guide

- Why is the cheapest configuration not always optimal? → It may reduce availability, capacity, recoverability, or operational safety.
- Which recommendations can be automated safely? → Low-blast-radius, reversible changes with strong validation and clear ownership.
- What makes a recurring review proactive? → A defined cadence, changing evidence, thresholds, ownership, and tracked outcomes.

## Success Criteria Notes

- **Require:** declared scope, multi-source evidence, trade-offs, prioritization, ownership, and explicit confirmation that no writes occurred.
- **Reject:** Advisor paraphrases presented as analysis or destructive recommendations without criticality context.
- **Accept:** fewer findings in a small environment and documented Cost Management permission gaps.

## Solution

Ask the agent to run a recommendation-only optimization review across every accessible lab subscription. Require these evidence planes:

1. Resource Graph inventory and orphan checks.
2. Cost Management spend where permissions allow.
3. Azure Monitor utilization and telemetry freshness.
4. Azure Advisor recommendations.
5. Backup and alert coverage for critical workloads.
6. Knowledge-base criticality, ownership, RTO, and RPO.

Require one de-duplicated table with scope, evidence, value, risk, confidence, effort, trade-off, owner, and approval requirement. End the response with an explicit statement that no resources were changed.