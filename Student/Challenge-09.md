[< Previous Challenge](./Challenge-08.md) — **[Home](../README.md)** — [Next Challenge >](./Challenge-10.md)

# Challenge 09 — Daily Application Health Report

> **Application focus:** Parking Manager only

> **Capabilities added in this challenge**: SLI/SLO concepts · Operational reporting · Health scoring

## Introduction

Generate a daily health report for Parking Manager's backend APIs. Compare CPU, memory, request volume, response time, and error rate in one table, then explain the thresholds used to assign each API a health status.

Challenge 08 mapped dependencies. This challenge measures health across services and introduces SLI/SLO concepts.

## Description

### Before you start

Confirm the Parking Manager is running and that there is sufficient monitoring data:

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

Ask the agent to describe how this could be automated:

```text
How would you configure a scheduled task to run this health report every morning at 07:00 UTC and post the results somewhere actionable? Walk me through the scheduled task YAML fields you would use.
```

Compare the agent's description to the scheduled task configurations already in the lab — browse them in the portal under **Automation**.

You can ask the agent to create the scheduled task:

```text
Create this scheduled task.
```

The agent will create it and you can browse it in the portal under **Automation**.

## Success Criteria

- [ ] The agent produces a summary table covering all four Parking Manager APIs (Lisbon, Madrid, Paris, Berlin) with CPU, memory, requests, response time, and error rate
- [ ] The agent assigns a health status to each API with a clearly stated scoring rationale
- [ ] The agent identifies at least one API that requires attention (or confirms all are healthy) with a recommended first step
- [ ] The agent can describe the scheduled task YAML structure for automating this report
- [ ] **Explain to your coach** — what is the difference between an SLI (Service Level Indicator) and an SLO (Service Level Objective)? Which fields in the health table are SLIs, and where would SLO thresholds live in the agent's configuration?

## Learning Resources

- [Azure Monitor — metrics overview](https://learn.microsoft.com/en-us/azure/azure-monitor/essentials/data-platform-metrics)
- [Azure Container Apps — metrics](https://learn.microsoft.com/en-us/azure/container-apps/metrics)
- [Azure Monitor Agent — performance counters](https://learn.microsoft.com/en-us/azure/azure-monitor/agents/data-collection-performance)
- [Azure SRE Agent — scheduled tasks](https://learn.microsoft.com/en-us/azure/sre-agent/scheduled-tasks)
- [SRE Book — Service Level Objectives](https://sre.google/sre-book/service-level-objectives/)

## Tips

- For Azure-hosted APIs, CPU and memory metrics come from Container Apps metrics (for ACA services) or from Performance counters in the Log Analytics workspace (for VM-hosted services).
- Berlin API data requires the OpenTelemetry MCP server — if it's unavailable, the table will show "N/A" for Berlin. Note this explicitly; it's a realistic gap in observability coverage.
- The lab ships a real scheduled task you can use as a structural reference for Step 4: `daily-network-observability-health` (runs at 06:00 UTC via the `network-traffic-analyst` specialist in Autonomous mode). Browse it in the portal under **Automation** or open `Resources/azure-sre-agent-config/automations/scheduled-tasks/daily-network-observability-health.yaml`.
