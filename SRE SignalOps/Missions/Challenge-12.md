[< Previous Challenge](./Challenge-11.md) — **[Home](./README.md)**

# Challenge 12 — Plan a Response to an Assurance Risk

> **Incident capability exercised in this challenge**: Assurance-Risk Detection · Preventive Response · Change Validation

## Introduction

A critical workload may be running while its alerting, telemetry, backup, or capacity assurance is already degraded. Use the SRE Agent to find the highest-priority tenant risk, treat it as a preventive SRE issue, and define a governed path to resolution before customer impact occurs.

## Description

> **Customer demo script:** Run `pwsh -File '.\SRE SignalOps\Scripts\Challenge-12.ps1' -EnvironmentName signalops-core` for a read-only inventory, Advisor, and observability review. See the [presenter runbook](../Scripts/README.md).

For Terraform, use `-TerraformPath '<absolute-infra-path>'` instead of the Bicep
environment parameter. The wrapper covers one selected subscription and only
inventory, Advisor and workspace settings. Cost, utilization, backup, alert and
telemetry-freshness assessments require separate authorized read-only queries;
mark each source unassessed until that evidence is collected.

Run a proactive review that combines current Azure evidence with the organizational context from Challenge 06. Keep discovery recommendation-only, then select one highest-priority assurance issue and achieve these outcomes:

- Declare the approved subscription scope and identify the resources included in the review; explicitly approve any additional subscription before inspecting it.
- Examine cost and utilization, Azure Advisor recommendations, backup coverage, alert coverage, stale telemetry, and obvious orphaned resources.
- Produce only evidence-supported issues across cost, reliability, observability, resilience, or governance. Zero issues or fewer than three is valid; distinguish lack of findings from missing evidence.
- For each issue, include affected scope, evidence, expected value or risk reduction, confidence, implementation effort, operational trade-off, and suggested owner.
- If an issue is supported, select the highest-priority one and define the owner, customer consequence, approval boundary, reversible remediation, rollback trigger, and post-change validation.
- Define a recurring review cadence that would detect the issue again.

Do not resize, delete, stop, reconfigure, or remediate any resource. If evidence is unavailable because of permissions or data retention, report the gap instead of guessing.

## Success Criteria

- [ ] The report states which subscriptions and resource types were reviewed
- [ ] Findings combine more than one evidence source rather than repeating Azure Advisor alone
- [ ] Supported assurance issues are prioritized by value, risk, confidence, and effort; zero findings or incomplete evidence is reported honestly
- [ ] Recommendations respect workload criticality, RTO/RPO, and ownership context from the knowledge base
- [ ] Missing access or evidence is reported as a limitation
- [ ] The agent confirms that it performed no write operations
- [ ] Any selected issue has an owner, governed remediation, rollback trigger, and measurable validation plan; no-issue results state what was assessed and what remains unknown
- [ ] **Explain to your coach** — why should an observability, backup, or capacity gap be handled as an SRE issue before it causes an outage?

## Learning Resources

- [Azure Advisor overview](https://learn.microsoft.com/en-us/azure/advisor/advisor-overview)
- [Azure Resource Graph overview](https://learn.microsoft.com/en-us/azure/governance/resource-graph/overview)
- [Azure Cost Management documentation](https://learn.microsoft.com/en-us/azure/cost-management-billing/cost-management-billing-overview)
- [Azure Well-Architected Framework](https://learn.microsoft.com/en-us/azure/well-architected/)

## Tips

- Treat a missing alert, stale data source, or unprotected critical workload as an assurance issue even when it has no immediate customer impact.
- De-duplicate the same issue when Resource Graph, Advisor, and Cost Management expose it independently.
- A preventive issue is not resolved until the control is changed and its protection is validated; this mission produces that governed plan without executing it.