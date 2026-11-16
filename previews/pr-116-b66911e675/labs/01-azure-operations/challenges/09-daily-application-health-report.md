---
title: Daily Application Health Report
summary: Ask the agent to generate a structured health report for all four Parking Manager APIs — CPU, memory, error rate, response time — with a health score and recommended remediation for any service falling below threshold.
phase: Autonomous
group: Observability and health reporting
tags:
- SLI/SLO
- health scoring
- operational reporting
highlight: false
---

# Challenge 09 — Daily Application Health Report

> **Application focus:** Parking Manager only

> **Capabilities added in this challenge**: SLI/SLO concepts · Operational reporting · Health scoring

## Purpose

- Generate a daily health report and label each field in it as an SLI or as context, with a proposed SLO threshold for one SLI.
- This bridges raw telemetry and a health narrative an on-call engineer can read.
- Expected time: 20 minutes.

## Introduction

Generate a daily health report for Parking Manager's backend APIs. Compare CPU, memory, request volume, response time, and error rate in one table, then explain the thresholds used to assign each API a health status.

Challenge 08 mapped dependencies. This challenge measures health across services and introduces SLI/SLO concepts.

## Description

### Before you start

Confirm the Parking Manager is running and has enough monitoring data:

```bash
make validate-parking
```

### Step 1 — Generate the health report

Ask the agent:

```text
Summarize the state of the Parking Manager backend APIs: Lisbon, Madrid, Paris, and Berlin. Provide the results in a summary table with the following fields for each API:
- CPU usage (average %)
- Memory usage (average %)
- Total requests (last 24 hours)
- Average response time (ms)
- Error rate (%)
```

The agent will:

- Query Azure Monitor / Log Analytics for the Azure-hosted APIs (Lisbon, Madrid, Paris)
- Use the OpenTelemetry MCP server for the Berlin API (third-party telemetry)
- Format results in a consolidated Markdown table

### Step 2 — Determine health status

Follow up:

```text
Based on these metrics, assign a health status (Healthy / Degraded / Critical) to each API. Explain your scoring logic.
```

### Step 3 — Identify what requires attention

```text
Which APIs, if any, require attention? For each one, state what the issue is and what the recommended first investigation step would be.
```

### Step 4 — Design a scheduled report

Ask the agent how to automate this:

```text
How would you configure a scheduled task to run this health report every morning at 07:00 UTC and post the results somewhere actionable? Walk me through the scheduled task YAML fields you would use.
```

Compare the agent's description with the scheduled tasks already in the lab. Browse them in the portal under **Automation**.

To have the agent create the task, ask:

```text
Create this scheduled task.
```

You can then browse it in the portal under **Automation**.

## Success Criteria

- [ ] The agent produces a summary table covering all four Parking Manager APIs (Lisbon, Madrid, Paris, Berlin) with CPU, memory, requests, response time, and error rate
- [ ] The agent assigns a health status to each API with a clearly stated scoring rationale
- [ ] The agent identifies at least one API that requires attention (or confirms all are healthy) with a recommended first step
- [ ] The agent can describe the scheduled task YAML structure for automating this report
- [ ] **Explain in your own words** (two or three written sentences) — choose one field in your health table. Say why it's an SLI, propose an SLO threshold for it, and say where that threshold would live in the agent's configuration.

## Learning Resources

- [Azure Monitor — metrics overview](https://learn.microsoft.com/en-us/azure/azure-monitor/essentials/data-platform-metrics)
- [Azure Container Apps — metrics](https://learn.microsoft.com/en-us/azure/container-apps/metrics)
- [Azure Monitor Agent — performance counters](https://learn.microsoft.com/en-us/azure/azure-monitor/agents/data-collection-performance)
- [Azure SRE Agent — scheduled tasks](https://learn.microsoft.com/en-us/azure/sre-agent/scheduled-tasks)
- [SRE Book — Service Level Objectives](https://sre.google/sre-book/service-level-objectives/)

## Tips

- For Azure-hosted APIs, CPU and memory metrics come from Container Apps metrics (for ACA services) or from Performance counters in the Log Analytics workspace (for VM-hosted services).
- Berlin API data requires the OpenTelemetry MCP server. If it's unavailable, the table shows "N/A" for Berlin. Note this explicitly; it's a realistic gap in observability coverage.
- The lab ships a real scheduled task you can use as a structural reference for Step 4: `daily-network-observability-health` (runs at 06:00 UTC via the `network-traffic-analyst` specialist in Autonomous mode). Browse it in the portal under **Automation** or open `resources/azure-sre-agent-config/automations/scheduled-tasks/daily-network-observability-health.yaml`.

## Hints and notes

> Hidden until you click. Expand a section only when you want it.

<details>
<summary><strong>Background</strong></summary>

- The SLIs are CPU, memory, requests, response time, and error rate.
- Scoring turns indicators into operational judgments (Healthy/Degraded/Critical), not just raw numbers.
- Berlin may still depend on the missing OpenTelemetry connector; expect an explicit `N/A` when it's absent.
- The YAML design part is conceptual: compare against the scheduled-task patterns already in the lab, even if no Parking Manager-specific task is in this default config bundle.

</details>

<details>
<summary><strong>Expected Output</strong></summary>

- You produce a four-service table for Lisbon, Madrid, Paris, and Berlin (or Berlin marked unavailable).
- Each service has a health status with rationale.
- You explain what first investigation step you would take for any degraded service.
- You can describe the main scheduled-task YAML fields: `metadata.name`, `schedule`, `time_zone`, `agent`, `mode`, `prompt`, `enabled`.

</details>

<details>
<summary><strong>Common Issues and Hints</strong></summary>

- **Symptom:** You report metrics but no judgment. **Fix:** prompt for scoring logic explicitly.
- **Symptom:** Berlin row missing. **Fix:** ask for a row with `N/A` and a note about the missing OpenTelemetry connector.
- **Symptom:** You cannot find a Parking Manager-specific scheduled task in the repo. **Fix:** use `daily-network-observability-health` as the reference pattern and adapt it.

</details>

<details>
<summary><strong>Debrief Discussion Guide</strong></summary>

- Which columns are SLIs and where would SLOs live? → SLIs are measured values; SLOs live in policy/runbooks/knowledge or governance config.
- Why does a daily health report matter if alerts already exist? → It catches trends and low-grade degradation.
- What does the Berlin gap teach? → Reporting must represent missing telemetry honestly.

</details>
