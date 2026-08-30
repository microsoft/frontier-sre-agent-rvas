[< Previous Challenge](./Challenge-11.md) — **[Home](./README.md)** — [Next Challenge >](./Challenge-13.md)

# Challenge 12 — Proactive Tenant Optimization

> **Capabilities added in this challenge**: Resource Inventory · Azure Advisor · Proactive Risk Detection · Governance

## Introduction

Reactive operations begin after an alert. Proactive operations find waste, reliability gaps, and missing controls before they become incidents. In this challenge, you use the SRE Agent to produce a read-only optimization review across the subscriptions available in the lab tenant.

## Description

> **Customer demo script:** Run `pwsh -File '.\SRE SignalOps\Scripts\Challenge-12.ps1'` for a read-only inventory, Advisor, and observability review. See the [presenter runbook](./Scripts/README.md).

Run a proactive review that combines current Azure evidence with the organizational context from Challenge 11. Keep it recommendation-only and achieve these outcomes:

- Inventory the accessible subscriptions and identify the resources included in the review.
- Examine cost and utilization, Azure Advisor recommendations, backup coverage, alert coverage, stale telemetry, and obvious orphaned resources.
- Produce at least three prioritized opportunities across cost, reliability, observability, resilience, or governance.
- For each opportunity, include affected scope, evidence, expected value or risk reduction, confidence, implementation effort, operational trade-off, and suggested owner.
- Define a recurring review cadence and the conditions that would require human approval before implementation.

Do not resize, delete, stop, reconfigure, or remediate any resource. If evidence is unavailable because of permissions or data retention, report the gap instead of guessing.

## Success Criteria

- [ ] The report states which subscriptions and resource types were reviewed
- [ ] Findings combine more than one evidence source rather than repeating Azure Advisor alone
- [ ] At least three recommendations are prioritized by value, risk, confidence, and effort
- [ ] Recommendations respect workload criticality, RTO/RPO, and ownership context from the knowledge base
- [ ] Missing access or evidence is reported as a limitation
- [ ] The agent confirms that it performed no write operations
- [ ] **Explain to your coach** — which recommendation would you implement first, what approval would it require, and how would you prove that the change did not reduce reliability?

## Learning Resources

- [Azure Advisor overview](https://learn.microsoft.com/en-us/azure/advisor/advisor-overview)
- [Azure Resource Graph overview](https://learn.microsoft.com/en-us/azure/governance/resource-graph/overview)
- [Azure Cost Management documentation](https://learn.microsoft.com/en-us/azure/cost-management-billing/cost-management-billing-overview)
- [Azure Well-Architected Framework](https://learn.microsoft.com/en-us/azure/well-architected/)

## Tips

- Treat a missing alert, stale data source, or unprotected critical workload as an optimization opportunity even when it has no immediate cost saving.
- De-duplicate the same issue when Resource Graph, Advisor, and Cost Management expose it independently.
- A recommendation without evidence, trade-offs, and an owner is only a suggestion.