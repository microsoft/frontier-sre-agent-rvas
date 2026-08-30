[< Previous Challenge](./Challenge-12.md) — **[Home](./README.md)**

# Challenge 13 — Backup-to-Teams Resilience

> **Capabilities added in this challenge**: Azure Backup Alerting · Response Plans · Teams Notifications · Application Resilience

## Introduction

A resilient application needs more than a backup policy. Responders must know when protection is at risk, understand application impact, communicate quickly, follow an approved recovery path, and validate service after recovery. In this challenge, you build that automation workflow around an existing protected lab workload.

## Description

> **Customer demo script:** Run `pwsh -File '.\SRE SignalOps\Scripts\Challenge-13.ps1'` to inventory vaults and produce a review-ready Teams update. See the [presenter runbook](./Scripts/README.md).

The Grubify deployment does not create a Backup vault, protected workload, or Teams connector. Complete this mission in one of two supported modes:

- **Live mode:** use an existing Recovery Services vault or Backup vault with a protected lab workload, plus an authorized Teams connector whose post-message tool is granted to the response agent.
- **Evidence-pack mode:** use coach-provided vault, protected-item, job, recovery-point, and application-health evidence. Build and exercise the response plan, and produce a review-ready Teams message without posting it.

Achieve these outcomes:

- Enable Azure Monitor alerts for backup failures and route them to the Azure SRE Agent through the existing incident connection.
- Create a response plan covering detection, evidence collection, classification, Teams notification, approval, recovery guidance, validation, and escalation.
- Ground the investigation in live vault, protected-item, job, recovery-point, and application-health evidence plus the knowledge document’s owner, RTO, and RPO.
- Post one concise update to the intended Teams channel containing severity, affected workload, application impact, latest job state, latest usable recovery point, RPO risk, confidence, recommended action, and a portal link.
- Demonstrate the workflow with a genuine alert when available or a clearly labeled exercise incident based on live evidence.
- Explain how the application would be validated after an approved restore or recovery action and when the workflow must escalate.

Resolve the Teams destination at runtime or use a connector-managed destination. Do not commit OAuth tokens, webhook URLs, Team IDs, or Channel IDs. Do not label an in-progress job or pending initial recovery point as a confirmed backup failure.

## Success Criteria

- [ ] Live mode enables backup-failure alerting; evidence-pack mode identifies the supplied alert scope and labels the run as an exercise
- [ ] The response plan implements the complete detect-to-validate workflow with an explicit approval boundary
- [ ] The assessment correlates backup evidence with application criticality, RTO, RPO, and current health
- [ ] Live mode posts one concise incident update; evidence-pack mode produces an equivalent review-ready message without claiming delivery
- [ ] The message distinguishes confirmed failure, assurance risk, and healthy in-progress work
- [ ] The recovery guidance includes post-recovery application validation and escalation conditions
- [ ] **Explain to your coach** — why are a successful restore and a healthy application different outcomes, and which validation signals are required before closing the incident?

## Learning Resources

- [Monitor Azure Backup with Azure Monitor](https://learn.microsoft.com/en-us/azure/backup/backup-azure-monitoring-use-azuremonitor)
- [Azure Backup alerts overview](https://learn.microsoft.com/en-us/azure/backup/backup-azure-monitoring-built-in-monitor)
- [Send notifications from Azure SRE Agent](https://learn.microsoft.com/en-us/azure/sre-agent/send-notifications)
- [Connect Azure SRE Agent to Microsoft Teams](https://learn.microsoft.com/en-us/azure/sre-agent/teams-bot)
- [Application resilience in the Azure Well-Architected Framework](https://learn.microsoft.com/en-us/azure/well-architected/reliability/design-resilience)

## Tips

- Report protection state, job state, and recovery-point state separately.
- Keep detailed evidence in the SRE Agent investigation and put only the decision summary in Teams.
- Validation should cover application availability and correctness, not only Azure resource provisioning state.