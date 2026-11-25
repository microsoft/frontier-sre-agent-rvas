---
title: Daily Network Health Report
summary: 'Create a scheduled task that reviews 24 hours of network telemetry every morning and produces a decision-ready summary: denied flows, top talkers, missing VNet coverage, and unusual ports.'
phase: Scheduled
group: Proactive and scheduled operations
tags:
- scheduled task
- Traffic Analytics
- proactive ops
highlight: false
---

# Challenge 16 — Daily Network Health Report

> **Application focus:** Infrastructure/platform only

> **Capability**: Scheduled Tasks · Proactive Operations · Continuous Monitoring

## Purpose

- Run a scheduled report that surfaces a network pattern before any incident is raised, and name the evidence it cites.
- Reuse `network-traffic-analyst` for reporting as well as incident response.
- Expected time: 20 minutes.

## Introduction

Review 24 hours of network telemetry without waiting for an alert. The daily report summarizes denied flows, top talkers, missing VNet coverage, unusual ports, and ingestion delays, with enough context to guide an on-call engineer's next action.

Challenge 09 reported application health. This challenge applies scheduled reporting to the network.

## Description

### Before you start

Confirm the Grubify lab network has at least 24 hours of Traffic Analytics data:

```bash
make validate
```

If the lab was deployed today, run the baseline traffic generator to populate recent data:

```bash
make baseline-traffic
```

### Step 1 — Run the report manually

Invoke the `network-traffic-analyst` specialist and run the daily report manually:

```text
/agent network-traffic-analyst

Review the last 24 hours of NTANetAnalytics for this project. Summarize:
1. Denied flows: top source/destination pairs and ports
2. Top talkers: highest-volume flows by source IP
3. Missing VNet coverage: VNets with no flow records
4. Unusual ports: flows on non-standard or unexpected destination ports
5. Ingestion delays: any gaps or delays in Traffic Analytics data

Do not change any resources. Output the results as a structured narrative report.
```

### Step 2 — Review the report structure

Evaluate the output:

- Is it decision-ready? Could an on-call engineer act on it without further investigation?
- Do denied flows from earlier challenges (NSG block, UDR asymmetry) still appear in the 24-hour window, even though you cleaned them up?
- Are all three VNets covered (hub, app spoke, data spoke)?

### Step 3 — Inspect the scheduled task

In the portal, go to **Scheduled Tasks** and open `daily-network-observability-health`.

Note the cron expression, the subagent assigned, and the execution mode.

### Step 4 — Understand the reuse pattern

Ask the agent:

```text
The network-traffic-analyst subagent is used for both reactive incident response (NSG blocks, routing failures) and this proactive daily report. What is the advantage of reusing one specialist for both paths instead of having separate agents?
```

### Step 5 — Design a modification

Think through how you would change the scheduled task to:

- Run every 6 hours instead of daily
- Add an alert threshold: if more than 100 denied flows are found, send a notification
- Include cost-of-egress data alongside the flow summary

You don't need to implement this.

## Success Criteria

- [ ] The agent produces a structured daily network health report covering all 5 dimensions (denied flows, top talkers, missing coverage, unusual ports, ingestion delays)
- [ ] The report is narrative and decision-ready (not raw KQL output)
- [ ] You can read the scheduled task YAML and describe what it does, when it runs, and which specialist handles it
- [ ] You can explain how the same specialist (`network-traffic-analyst`) serves both the reactive and proactive paths
- [ ] **Explain in your own words** (two or three written sentences) — what is the difference between a proactive scheduled task and a reactive incident response plan in terms of how they trigger the agent and what output they produce?

## Learning Resources

- [Azure SRE Agent — scheduled tasks](https://learn.microsoft.com/en-us/azure/sre-agent/scheduled-tasks)
- [Traffic Analytics overview](https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics)
- [VNet Flow Logs — data schema](https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-overview#log-format)
- [Cron expression syntax](https://crontab.guru/)

## Tips

- The `daily-network-observability-health` scheduled task runs at 06:00 UTC. To see it run during the workshop, trigger it manually from the portal's scheduled tasks section.
- Missing VNet coverage is a key signal: if a VNet stops producing flow records, you lose visibility into that segment *before* an incident occurs. The agent checks this by comparing expected VNets (from the Terraform configuration) against records present in `NTANetAnalytics`.
- The report runs in `Autonomous` mode with a narrative-only prompt ("Do not change resources"). Unlike an `agentMode: Review` gate, this relies on the specialist following instructions rather than withholding tool approval. Check the tool-call log for unintended writes before using this pattern unattended.

## Hints and notes

> Hidden until you click. Expand a section only when you want it.

<details>
<summary><strong>Background</strong></summary>

- The scheduled task is `daily-network-observability-health`, cron `0 6 * * *`, agent `network-traffic-analyst`, mode `Autonomous`.
- Look for the five report dimensions: denied flows, top talkers, missing VNet coverage, unusual ports, ingestion delays.
- Faults from earlier challenges (NSG/UDR) may still appear inside the 24-hour window.
- The task is `Autonomous`, not gated by `agentMode: Review`. Its narrative-only prompt ("Do not change resources") tells the specialist not to write. Inspect the tool log to verify.

</details>

<details>
<summary><strong>Expected Output</strong></summary>

- Manual `/agent network-traffic-analyst` run produces a structured 24-hour report over `NTANetAnalytics`.
- Report discusses all three VNets and mentions missing coverage if any are absent.
- You can read the scheduled task in the portal and explain schedule, mode, and assigned specialist.
- You can explain why the same specialist serves both proactive and reactive paths.

</details>

<details>
<summary><strong>Common Issues and Hints</strong></summary>

- **Symptom:** Report is raw KQL dump. **Fix:** ask for a decision-ready narrative report.
- **Symptom:** Missing coverage is not addressed. **Fix:** ask explicitly whether hub, app spoke, and data spoke all produced records.
- **Symptom:** You expect the scheduled task to remediate. **Fix:** its prompt says “Do not change resources”. That is the safety control, since the task mode is `Autonomous`, not `Review`.

</details>

<details>
<summary><strong>Debrief Discussion Guide</strong></summary>

- How is a scheduled report trigger different from an incident filter trigger? → Cron vs alert.
- Why reuse one network specialist for both paths? → Shared domain context and less duplication.
- What is the value of a narrative report over a dashboard? → It highlights what matters without manual interpretation.

</details>
