[< Previous Challenge](./Challenge-07.md) — **[Home](../README.md)** — [Next Challenge >](./Challenge-09.md)

# Challenge 08 — Application Dependency Mapping

> **Capabilities added in this challenge**: Service Dependency Analysis · Application Topology · Correlation

## Introduction

When an application fails, the first question is always: *what does it depend on, and which dependency is the culprit?* For a distributed application like **Grubify (Sample Food)** — with its Container Apps API/frontend plus a third-party integration outside Application Insights — mapping the dependency graph is the foundation of every root-cause investigation.

In this challenge you'll use the agent to generate a dependency map from live telemetry, infer backend topology from Application Insights call data, and produce both a visual diagram and a structured summary table.

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
- [ ] **Explain to your coach** — what is the difference between Application Insights `dependencies` telemetry and `requests` telemetry? Which one do you use to build a dependency map, and why?

## Learning Resources

- [Application Insights — dependency tracking](https://learn.microsoft.com/en-us/azure/azure-monitor/app/asp-net-dependencies)
- [Application Insights — application map](https://learn.microsoft.com/en-us/azure/azure-monitor/app/app-map)
- [KQL — summarize operator](https://learn.microsoft.com/en-us/azure/data-explorer/kusto/query/summarize-operator)
- [Mermaid diagram syntax](https://mermaid.js.org/syntax/flowchart.html)

## Tips

- Application Insights dependency telemetry uses the `target` field to identify the downstream service. This field is populated by the SDK's auto-instrumentation and may contain a hostname, IP address, or service name depending on the client library.
- If dependency telemetry is sparse, check that `generate-sample-food-app-traffic.sh` ran recently. The dependency table has a ~5-minute ingestion delay.
- Ask the agent to produce Mermaid syntax for the diagram — it renders natively in GitHub Markdown and many modern editors.
