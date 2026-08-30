[< Previous Challenge](./Challenge-09.md) — **[Home](./README.md)** — [Next Challenge >](./Challenge-11.md)

# Challenge 10 — Heartbeat Triage and Deep RCA

> **Capabilities added in this challenge**: Azure Monitor Alerting · Automated Incident Triage · RCA Deep Dive

## Introduction

A missing heartbeat is a simple signal with several possible causes: the VM may be stopped, the monitoring agent may be unhealthy, or telemetry may be delayed. In this challenge, you create one heartbeat alert and let the SRE Agent distinguish the symptom from the root cause using current Azure state and recent telemetry.

## Description

> **Customer demo script:** Run `pwsh -File '.\SRE SignalOps\Scripts\Challenge-10.ps1' -WorkspaceId '<workspace-id>' -VmResourceId '<resource-id>'`. Lab VM changes require `-Execute`; recovery requires `-Restore`. See the [presenter runbook](./Scripts/README.md).

The Grubify deployment does not create a VM or Azure Monitor Agent. Complete this mission in one of two supported modes:

- **Live mode:** use a coach-provided lab VM with Azure Monitor Agent, a data collection rule, and recent `Heartbeat` records in the connected Log Analytics workspace.
- **Evidence-pack mode:** use a coach-provided alert, heartbeat timeline, VM power-state evidence, Activity Log evidence, and agent-health snapshot. Simulate routing and recovery; do not claim that a live alert fired.

Keep the exercise scoped to that single VM and achieve these outcomes:

- Create an enabled heartbeat alert that evaluates every 5 minutes over a 15-minute window and fires when the selected VM reports no heartbeat.
- Route the alert to the Azure SRE Agent through the existing Azure Monitor incident connection and a dedicated response plan.
- Safely create a missing-heartbeat condition on the lab VM, then observe the alert and automated investigation.
- Ask the agent for a deep RCA containing a timeline, evidence matrix, competing hypotheses, rejected hypothesis, root-cause assessment, contributing factors, confidence level, and recommended recovery action.
- Restore the VM or monitoring path and confirm that heartbeat data resumes and the alert resolves.

Do not make the response plan restart or modify the VM automatically. Investigation and recommendation are sufficient for this customer-friendly exercise.

## Success Criteria

- [ ] Live mode has one enabled heartbeat alert with the required scope and timing; evidence-pack mode identifies the supplied rule and labels the run as an exercise
- [ ] A live or simulated incident is routed to the intended SRE Agent response plan and accurately labeled
- [ ] The agent correlates missing heartbeat data with current VM state and monitoring status
- [ ] The RCA clearly separates observed symptoms, supporting evidence, likely root cause, contributing factors, confidence, and next action
- [ ] The RCA compares at least two plausible hypotheses and explains why one was rejected
- [ ] Live mode proves resumed heartbeat and alert resolution; evidence-pack mode states the exact evidence required to prove recovery
- [ ] **Explain to your coach** — why is “heartbeat missing” a symptom rather than a root cause, and what additional evidence would increase your confidence in the diagnosis?

## Learning Resources

- [Azure Monitor log search alerts](https://learn.microsoft.com/en-us/azure/azure-monitor/alerts/alerts-create-log-alert-rule)
- [Azure Monitor Agent overview](https://learn.microsoft.com/en-us/azure/azure-monitor/agents/azure-monitor-agent-overview)
- [Azure Monitor alerts and state](https://learn.microsoft.com/en-us/azure/azure-monitor/alerts/alerts-overview)
- [Automate incident response with Azure SRE Agent](https://learn.microsoft.com/en-us/azure/sre-agent/automate-incidents)

## Tips

- Confirm that the VM has recent heartbeat records before creating the failure condition. A missing baseline is a monitoring setup issue, not an incident.
- Compare the alert timestamp with VM power-state changes and the most recent heartbeat timestamp.
- A strong RCA states uncertainty. Do not call a stopped VM a monitoring-agent failure unless the evidence supports it.