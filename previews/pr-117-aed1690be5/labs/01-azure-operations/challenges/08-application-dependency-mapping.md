---
title: Application Dependency Mapping
summary: Map Grubify dependencies from Application Insights, including call counts and response times. Add Berlin Parking API metrics as a separate telemetry source.
phase: Autonomous
group: Observability and health reporting
tags:
- App Insights
- service topology
- dependency analysis
highlight: false
---

# Challenge 08 — Application Dependency Mapping

> **Application focus:** Grubify (Sample Food) only

> **Capabilities added in this challenge**: Service Dependency Analysis · Application Topology · Correlation

## Purpose

- Produce a dependency map from live telemetry and identify the slowest dependency with its call count and latency.
- This moves you from “what is broken?” to “what depends on what?”
- Expected time: 25 minutes.

## Introduction

A dependency map shows which downstream services may contribute to an application failure. Map the Grubify (Sample Food) frontend and API from Application Insights, then add Berlin Parking API telemetry as a separate integration example.

You use the agent to generate a dependency map from live telemetry, infer backend topology from Application Insights call data, and produce both a visual diagram and a structured summary table.

## Description

### Before you start

Confirm Grubify is healthy and generating Application Insights dependency telemetry:

```bash
make validate-food
make food-traffic   # safe to re-run if skipped in Challenge 00
```

### Step 1 — Generate the dependency diagram

Ask the agent:

```text
Generate a diagram for the application dependencies of the Grubify (Sample Food) application, including the frontend and its backend API. Analyze Application Insights dependency telemetry from the last 24 hours to infer the backend calls if required. Produce two outputs:
1. A visual diagram including, for each dependency, the number of calls and average response time.
2. A summary table with the same data.
```

The agent will:

- Query Application Insights `dependencies` and `requests` tables via KQL
- Infer the call graph from `target` and `name` fields in dependency telemetry
- Identify each backend service, its call volume, and its average response time
- Produce a Mermaid or ASCII diagram plus a Markdown table

### Step 2 — Identify unhealthy dependencies

Follow up:

```text
Which of the dependencies has the highest error rate? Are there any dependencies with response times above 500ms? Highlight them in the table.
```

### Step 3 — Correlate with third-party telemetry

```text
The Berlin Parking API is a separate, third-party-style integration not visible in Grubify's Application Insights. Use the OpenTelemetry MCP server to retrieve its call metrics and add it to the dependency map as an example of blending two different telemetry sources.
```

### Step 4 — Understand the topology

Ask the agent to describe what it found:

```text
Based on the dependency telemetry, describe Grubify's call topology: which service is the entry point, which services are called synchronously, and are there any single points of failure in the dependency graph?
```

## Success Criteria

- [ ] The agent produces a visual dependency diagram with call counts and response times
- [ ] The agent produces a summary table with the same data in structured form
- [ ] The agent identifies the dependency with the highest error rate or highest latency
- [ ] The agent incorporates the Berlin Parking API's OpenTelemetry data into the dependency map
- [ ] **Explain in your own words** (two or three written sentences) — what is the difference between Application Insights `dependencies` telemetry and `requests` telemetry? Which one do you use to build a dependency map, and why?

## Learning Resources

- [Application Insights — dependency tracking](https://learn.microsoft.com/en-us/azure/azure-monitor/app/asp-net-dependencies)
- [Application Insights — application map](https://learn.microsoft.com/en-us/azure/azure-monitor/app/app-map)
- [KQL — summarize operator](https://learn.microsoft.com/en-us/azure/data-explorer/kusto/query/summarize-operator)
- [Mermaid diagram syntax](https://mermaid.js.org/syntax/flowchart.html)

## Tips

- Application Insights dependency telemetry uses the `target` field to identify the downstream service. The SDK's auto-instrumentation fills it in, and it may hold a hostname, IP address, or service name depending on the client library.
- If dependency telemetry is sparse, check that `generate-sample-food-app-traffic.sh` ran recently. The dependency table has a ~5-minute ingestion delay.
- Ask the agent for Mermaid syntax. It renders natively in GitHub Markdown and many modern editors.

## Hints and notes

> Hidden until you click. Expand a section only when you want it.

<details>
<summary><strong>Background</strong></summary>

- `requests` are entry-point work; `dependencies` are downstream calls.
- Expected output formats: Mermaid or ASCII diagram plus a summary table.
- Berlin caveat: the Berlin Parking API's OpenTelemetry data is outside Grubify's Application Insights and is fetched separately via the Berlin MCP connector (deployed in Challenge 04/07 as `berlin-monitoring-v6`).
- The workshop bundle includes `/agent dependency-analyzer` for this challenge.
- Dependency maps stay sparse until telemetry exists, so `make food-traffic` matters.

</details>

<details>
<summary><strong>Expected Output</strong></summary>

- A dependency diagram for Grubify (Sample Food) showing frontend/backend relationships with calls and average response times.
- A matching table highlighting highest error rate and any dependencies above 500 ms.
- The Berlin Parking API's OpenTelemetry data is appended as a separately-sourced dependency, blended in from a connector distinct from Application Insights.
- You can explain why `dependencies` telemetry is the primary map-building source.

</details>

<details>
<summary><strong>Common Issues and Hints</strong></summary>

- **Symptom:** Diagram is too generic or missing numbers. **Fix:** request call counts and average response time explicitly.
- **Symptom:** Dependency table is empty. **Fix:** run `make food-traffic` and retry after ~5 minutes of ingestion.
- **Symptom:** Berlin is omitted without comment. **Fix:** ask for an explicit note that Berlin telemetry comes from the OpenTelemetry MCP connector, not Application Insights, and confirm the connector was applied in an earlier challenge.

</details>

<details>
<summary><strong>Debrief Discussion Guide</strong></summary>

- Why are `dependencies` better than `requests` for topology inference? → They show outbound calls and downstream targets.
- What does a single point of failure look like in a telemetry-derived graph? → Central node with no alternative path.
- Why is adding Berlin separately useful? → It exposes the boundary between first-party and third-party observability.

</details>
