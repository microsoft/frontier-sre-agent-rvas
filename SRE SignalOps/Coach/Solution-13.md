[< Previous Solution](./Solution-12.md) | **[Home](./README.md)** | [Next Solution >](./Solution-14.md)

# Coach Guide — Challenge 13: Resolve a Critical Assurance Risk

## Purpose

- Detect a critical observability, backup, capacity, cost, or governance assurance issue before it becomes a customer-facing incident.
- Turn the selected issue into an owned, approval-gated remediation and validation plan.
- Expected time: 20–25 minutes.

## Mini-Lecture (5 min before challenge)

- A service can be available while its ability to detect, absorb, or recover from the next failure is degraded.
- Strong preventive SRE work combines inventory, spend, utilization, Advisor, monitoring, protection, and workload context.
- The highest-priority assurance issue is selected by customer consequence and evidence, not cost alone.
- Discovery remains read-only until ownership, approval, rollback, and validation are explicit.

## Expected Student Output

- A declared subscription and resource scope.
- At least three prioritized assurance issues supported by multiple evidence sources.
- One selected issue with customer consequence, confidence, owner, approval, remediation, rollback, and validation.
- A recurring detection cadence that would reveal recurrence.

## Coach Runbook

1. Require the student to declare subscriptions, resource groups, time window, and inaccessible evidence before analysis.
2. Check that each issue uses at least two evidence planes and names the affected resource, customer consequence, and owner.
3. Select the highest-priority issue and require approval, reversible remediation, rollback trigger, validation, and recurrence detection.
4. End by confirming no writes occurred and the issue is planned, not falsely reported as resolved.

## Common Issues and Hints

- **Symptom:** The report only paraphrases Azure Advisor. **Fix:** require inventory, utilization, backup, alert, telemetry-freshness, and workload-impact evidence.
- **Symptom:** Cost data is unavailable. **Fix:** report the permission gap and continue with technical optimization evidence.
- **Symptom:** The agent recommends deleting or downsizing a critical resource. **Fix:** apply the knowledge document’s criticality and recovery objectives before prioritization.
- **Symptom:** The student calls the selected risk resolved. **Fix:** distinguish a governed remediation plan from an executed and validated change.

## Debrief Discussion Guide

- Why is an assurance gap an SRE issue before an outage? → It raises the probability, duration, or uncertainty of future customer impact.
- Which preventive actions can be automated safely? → Low-blast-radius, reversible changes with strong validation and clear ownership.
- What proves preventive resolution? → The missing or degraded control is restored, tested, monitored for recurrence, and does not reduce service reliability.

## Success Criteria Notes

- **Require:** declared scope, multi-source evidence, a selected assurance issue, ownership, governed remediation, rollback, validation, and confirmation that no writes occurred.
- **Reject:** Advisor paraphrases presented as analysis, cost-only prioritization, or a planned change reported as completed resolution.
- **Accept:** fewer findings in a small environment and documented permission gaps when uncertainty remains explicit.

## Solution

Ask the SRE Agent to run a recommendation-only assurance review across every accessible lab subscription. Require these evidence planes:

1. Resource Graph inventory and orphan checks.
2. Cost Management spend where permissions allow.
3. Azure Monitor utilization and telemetry freshness.
4. Azure Advisor recommendations.
5. Backup and alert coverage for critical workloads.
6. Knowledge-base criticality, ownership, RTO, and RPO.

Require one de-duplicated table with scope, evidence, customer consequence, value, risk, confidence, effort, trade-off, owner, and approval requirement. Select one issue and add reversible remediation, rollback trigger, validation, and recurrence detection. End with an explicit statement that no resources were changed and the issue is not yet resolved.