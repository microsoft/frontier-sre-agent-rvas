[< Previous Challenge](./Challenge-15.md) — **[Home](../README.md)** — [Next Challenge >](./Challenge-17.md)

# Challenge 16 — Daily Network Health Report

> **Capability**: Scheduled Tasks · Proactive Operations · Continuous Monitoring

## Introduction

Reactive operations wait for an alert. Proactive operations look for conditions that will become alerts — before the pager goes off.

The **Daily Network Health Report** demonstrates the proactive path: a scheduled task that wakes up every morning, reviews 24 hours of network telemetry, and produces a decision-ready summary — denied flows, top talkers, missing VNet coverage, unusual ports, and ingestion delays — delivered as a narrative, not a dashboard of raw metrics.

While Challenge 09 generated a health report for application-layer APIs, this challenge shifts to the **network layer** — demonstrating that the same proactive reporting pattern applies across every layer of your stack, from application to infrastructure.

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
- Are there any denied flows from the previous challenges (NSG block, UDR asymmetry) that were cleaned up but still appear in the 24-hour window?
- Are all three VNets covered (hub, app spoke, data spoke)?

### Step 3 — Inspect the scheduled task

Read the scheduled task configuration in the portal — navigate to **Scheduled Tasks** and open `daily-network-observability-health`.

Note the cron expression, the subagent assigned, and the execution mode.

### Step 4 — Understand the reuse pattern

Ask the agent:

```text
The network-traffic-analyst subagent is used for both reactive incident response (NSG blocks, routing failures) and this proactive daily report. What is the advantage of reusing one specialist for both paths instead of having separate agents?
```

### Step 5 — Design a modification

Consider how you would modify the scheduled task to:

- Run every 6 hours instead of daily
- Add an alert threshold: if more than 100 denied flows are found, send a notification
- Include cost-of-egress data alongside the flow summary

You don't need to implement this — discuss the approach with your coach.

## Success Criteria

- [ ] The agent produces a structured daily network health report covering all 5 dimensions (denied flows, top talkers, missing coverage, unusual ports, ingestion delays)
- [ ] The report is narrative and decision-ready (not raw KQL output)
- [ ] You can read the scheduled task YAML and describe what it does, when it runs, and which specialist handles it
- [ ] You can explain how the same specialist (`network-traffic-analyst`) serves both the reactive and proactive paths
- [ ] **Explain to your coach** — what is the difference between a proactive scheduled task and a reactive incident response plan in terms of how they trigger the agent and what output they produce?

## Learning Resources

- [Azure SRE Agent — scheduled tasks](https://learn.microsoft.com/en-us/azure/sre-agent/scheduled-tasks)
- [Traffic Analytics overview](https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics)
- [VNet Flow Logs — data schema](https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-overview#log-format)
- [Cron expression syntax](https://crontab.guru/)

## Tips

- The `daily-network-observability-health` scheduled task runs at 06:00 UTC. If you want to see it execute during the workshop, you can trigger it manually from the portal's scheduled tasks section.
- "Missing VNet coverage" is one of the most important signals in this report: if a VNet stops producing flow records, you lose visibility into that segment of the network *before* an incident occurs. The agent checks this by comparing expected VNets (from the Terraform configuration) against records actually present in `NTANetAnalytics`.
- The report intentionally runs in `Autonomous` mode with a narrative-only prompt ("Do not change resources") — no write operations, no resource changes, just the report. This is a different safety mechanism than an `agentMode: Review` gate: it relies on prompt discipline plus a task that never asks the specialist to remediate anything. That's what makes it safe to run frequently and unattended.
