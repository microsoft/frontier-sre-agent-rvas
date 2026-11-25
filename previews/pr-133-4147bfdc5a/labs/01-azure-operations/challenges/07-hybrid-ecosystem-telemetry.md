---
title: Hybrid Ecosystem Telemetry
summary: The Parking Manager spans Container Apps, VMs, and a third-party OpenTelemetry API. Use the agent to query all three platforms and produce a unified cross-system view.
phase: Autonomous
group: Observability and health reporting
tags:
- Log Analytics
- Syslog
- OpenTelemetry
highlight: false
---

# Challenge 07 — Hybrid Ecosystem Telemetry

> **Application focus:** Parking Manager only

> **Capabilities added in this challenge**: Log Analytics · Application Insights · Syslog · OpenTelemetry · Cross-platform observability

## Purpose

- Run one investigation that combines Azure Monitor data with a non-Azure telemetry source, and cite evidence from each.
- Real fleets rarely live entirely inside one monitoring stack.
- Expected time: 20–25 minutes.

## Introduction

Parking Manager uses Azure Container Apps with Azure Monitor, VMs with Windows Event Logs and Linux Syslog, and an OpenTelemetry API that simulates an external partner's telemetry.

Query Azure-native logs and third-party telemetry in one agent session, then compare API health across the two sources.

## Description

### Before you start

Confirm the Parking Manager is running and generating data:

```bash
make validate-parking
```

### Step 1 — Query Azure-native logs for the Madrid API

Ask the agent:

```text
Check the status of the Madrid-API and check any relevant logs. Highlight the top 3 failures and output the results in a summary table including the average response time.
```

The agent will:

- Query the Log Analytics workspace for HTTP status codes, error rates, and latency
- Pull Windows Event Log data from the VM-hosted backend
- Identify the top error patterns by frequency

### Step 2 — Query third-party telemetry

Now query the OpenTelemetry-monitored component. The Berlin MCP server is deployed with the lab infrastructure, and the `berlin-mcp` connector ships in `labs/01-azure-operations/resources/azure-sre-agent-config/connectors/`.

> **Note:** If you ran `make connectors` during Challenge 01, the berlin-mcp connector is already registered. The command is idempotent: running it again updates the connector with the latest `parking_berlin_mcp_url` Terraform output.

```bash
make connectors
```

The connector endpoint comes from the `parking_berlin_mcp_url` Terraform output.

Then ask:

```text
/agent access-to-3rd-party-logs

Check the status of the Berlin parking API and provide a summary of calls, top errors, and average response time over the last hour.
```

> **`/agent` routing syntax:** `/agent <subagent-name>` at the start of a prompt routes it directly to that specialist. The `access-to-3rd-party-logs` subagent was configured in Challenge 05 and uses the `berlin-mcp` connector to reach the OpenTelemetry feed. The shorthand `@access-to-3rd-party-logs:` works too.

The agent uses the **OpenTelemetry MCP server** to retrieve metrics from the external telemetry API. That data never flows into Azure Monitor.

### Step 3 — Cross-platform comparison

Combine both data sources:

```text
Compare the health of the Madrid API (from Azure Monitor) and the Berlin API (from the OpenTelemetry feed). Which is performing better? Are there any correlated failure patterns?
```

### Step 4 — Identify the skill

Ask the agent to name the skill it used and explain its structure:

```text
Which skill did you use to fetch HTTP calls, average response time, and errors from Windows Event Logs and Linux Syslogs? What does that skill's KQL look like?
```

## Success Criteria

- [ ] The agent returns a summary table with error counts and average response time for the Madrid API from Log Analytics
- [ ] The agent retrieves Berlin API metrics using the OpenTelemetry MCP server
- [ ] The agent produces a cross-platform comparison of both APIs
- [ ] You can identify which skill provides the Windows Event Log and Syslog query capability
- [ ] **Explain in your own words** (two or three written sentences) — why does the Berlin API use an MCP server instead of Azure Monitor? What architectural pattern does this represent in hybrid enterprise environments?

## Learning Resources

- [Azure Monitor Logs overview](https://learn.microsoft.com/en-us/azure/azure-monitor/logs/data-platform-logs)
- [Azure Monitor Agent — Syslog collection](https://learn.microsoft.com/en-us/azure/azure-monitor/agents/data-collection-syslog)
- [OpenTelemetry overview](https://opentelemetry.io/docs/)
- [Model Context Protocol — custom servers](https://modelcontextprotocol.io/docs/concepts/servers)

## Tips

- `/agent access-to-3rd-party-logs` routes the prompt to the `access-to-3rd-party-logs` subagent, which uses the `berlin-mcp` connector's OpenTelemetry tools. The `@access-to-3rd-party-logs:` shorthand is equivalent.
- Log Analytics query latency for Syslog and Windows Event Logs is typically a few minutes behind real time. If the last-1-hour window returns no data, expand to last 6 hours.

## Hints and notes

> Hidden until you click. Expand a section only when you want it.

<details>
<summary><strong>Background</strong></summary>

- The data split: Madrid lives in Azure-native telemetry; Berlin is third-party/OpenTelemetry via MCP.
- The Azure side may include Log Analytics plus Windows Event Logs/Linux Syslog reasoning, while Berlin comes from `@Access-to-3rd-Party-Logs`.
- The likely reusable skill for the Azure side: `connectivity-diagnostics` or related log/telemetry skills, depending on the agent’s routing.
- The Berlin MCP connector ships in `labs/01-azure-operations/resources/azure-sre-agent-config/connectors/` and is applied with `make connectors`.

</details>

<details>
<summary><strong>Expected Output</strong></summary>

- You get a Madrid summary table with error counts and average response time from Azure-native telemetry.
- Berlin metrics are returned through the bundled MCP connector and compared with Azure-native telemetry.
- You can name the skill or investigation structure used on the Azure side.

</details>

<details>
<summary><strong>Common Issues and Hints</strong></summary>

- **Symptom:** Madrid query returns no recent data. **Fix:** run `make validate-parking` again and widen the window from 1 hour to 6 hours.
- **Symptom:** Your platform comparison doesn't distinguish sources. **Fix:** label which findings came from Azure Monitor and which from MCP.
- **Symptom:** `/agent access-to-3rd-party-logs` returns "subagent not found" or routes to the main agent instead. **Fix:** confirm the `access-to-3rd-party-logs` subagent was applied in Challenge 05 (`make subagents`) and that `make connectors` was re-run to register the `berlin-mcp` connector endpoint.

</details>

<details>
<summary><strong>Debrief Discussion Guide</strong></summary>

- Why use MCP for Berlin instead of forcing everything into Azure Monitor? → Reflects real hybrid/partner telemetry boundaries.
- What breaks operationally if one monitoring plane is absent? → You still need graceful degradation, not silent omission.
- What did the agent add compared with a human manually switching dashboards? → Unified narrative and cross-source correlation.

</details>
