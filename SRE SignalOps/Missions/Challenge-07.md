[< Previous Challenge](./Challenge-06.md) — **[Home](./README.md)** — [Next Challenge >](./Challenge-08.md)

# Challenge 07 — Respond to a VM Backup Failure with External Approval

> **Capabilities added in this challenge**: Azure VM Backup · Native Backup Alerts · Teams Approval Gate · Incident-Bound Retry

## Introduction

A virtual machine is not recoverable until its backups and response controls are proven. In this challenge, you will protect one VM, route a failed-backup incident to a specialist, and exercise a retry that cannot run until an engineer approves it in Microsoft Teams and the incident is at least five minutes old.

Start by asking the SRE Agent whether `vm-parking-madrid` has backup protection, a successful recovery point, and an approval-enforced backup response. Record the capability gap or evidence it returns before configuring the workflow.

## Description

This is an advanced live integration, not a default core-deployment capability.
The [Mission 07 add-on](../infra/backup.bicep) requires an existing
`vm-parking-madrid`, explicit VM resource group and Teams group/channel IDs, and
the workload's actual workspace/Application Insights names. The VM and vault
must use a supported matching region; verify the VM is not protected by a
different vault. The coach must deploy the approval Function code, authorize the
Teams connection, register the constrained backup connector/specialist/plan and
five-minute task, and prove a baseline recovery point before the live exercise.
The [coach guide](../Coach/Missions/Solution-07.md) owns that preparation.

If those integrations are unavailable, use the
[evidence-pack contract](./README.md#evidence-pack-and-network-sandbox-contract).
Analyze supplied job, recovery-point and approval records; do not run the
workflow or claim live approval, retry, delivery or recovery. Without a prepared
live environment or evidence pack, stop and record the missing prerequisites.

Build and validate an operational backup response for one VM:

- Protect only `vm-parking-madrid` with Azure VM Backup and establish a successful recovery point.
- Enable native Azure Backup failed-job alerts and route the resulting incident to the backup specialist in Review mode.
- Connect the specialist to the constrained approval gate and authorize its Teams workflow for the assigned channel.
- Preserve the Azure Monitor incident ID and original creation timestamp throughout the workflow.
- Require a connector-authenticated engineer decision and a minimum incident age of five minutes before retrying the backup.
- Prove denied, early, malformed, and replayed executions fail closed.
- After an approved retry, verify a completed backup job and a newer recovery point.

> **Safety boundary:** The only remediation is one on-demand backup retry. Do not grant the specialist a generic Azure write tool. Do not start, restart, or restore the VM.

## Success Criteria

Apply the criteria below to live observations or explicitly labeled supplied
evidence. Only a live run can certify the gate and connector integrations.

- [ ] `vm-parking-madrid` is the only protected item created for this challenge, and it has a successful recovery point.
- [ ] Native Azure Backup failed-job alerting is enabled and a backup incident routes to the backup specialist in Review mode.
- [ ] The Teams approval card appears in the assigned channel, and the durable record contains the connector-authenticated responder identity and decision time.
- [ ] The gate rejects execution before five minutes, after denial, for malformed or mismatched input, and after the action has already been claimed.
- [ ] One approved retry after five minutes completes and produces a recovery point newer than the pre-remediation point.
- [ ] No restore, VM start, VM restart, generic Azure write grant, callback URL, Function key, OAuth token, or other credential appears in the workflow or evidence.
- [ ] **Explain to your coach** — why must the five-minute and one-time execution rules be enforced by the approval service rather than only by the SRE Agent prompt or schedule?

## Learning Resources

- [Back up an Azure VM](https://learn.microsoft.com/azure/backup/quick-backup-vm-portal)
- [Monitor Azure Backup with Azure Monitor](https://learn.microsoft.com/azure/backup/backup-azure-monitoring-use-azuremonitor)
- [Azure Backup built-in alerts](https://learn.microsoft.com/azure/backup/backup-azure-monitoring-built-in-monitor)
- [Azure SRE Agent incident response plans](https://learn.microsoft.com/azure/sre-agent/incident-response-plans)
- [Connect Azure SRE Agent to an MCP server](https://learn.microsoft.com/azure/sre-agent/mcp-connectors)
- [Workflow actions for Microsoft Teams](https://learn.microsoft.com/connectors/teams/)

## Tips

- Treat VM power state, backup protection, recovery-point freshness, and remediation authorization as separate evidence.
- Native backup alerts arrive sooner than diagnostic logs; do not use Log Analytics ingestion time as the incident clock.
- A completed retry is not enough: compare recovery-point timestamps before closing the incident.
