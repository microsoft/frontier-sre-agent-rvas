[< Previous Challenge](./Challenge-06.md) — **[Home](../README.md)** — [Next Challenge >](./Challenge-08.md)

# Challenge 07 — Hybrid Ecosystem Telemetry

> **Capabilities added in this challenge**: Log Analytics · Application Insights · Syslog · OpenTelemetry · Cross-platform observability

## Introduction

Modern applications don't live on a single platform. The **Parking Manager** spans Azure Container Apps (integrated with Azure Monitor), virtual machines generating Windows Event Logs and Linux Syslog, and a third-party telemetry API based on OpenTelemetry that simulates an external partner integration. No single dashboard covers all of it.

In this challenge you'll query a hybrid ecosystem from a single agent session — correlating Azure-native logs with third-party telemetry — and produce a consolidated view of an API's health across every monitoring plane.

## Description

### Before you start

Confirm the Parking Manager is running and generating data:

```bash
make validate
```

### Step 1 — Query Azure-native logs for the Madrid API

Ask the agent:

```text
Check the status of the Madrid-API and check any relevant logs. Highlight the top 3 failures and output the results in a summary table including the average response time. The logs are stored in Log Analytics.
```

The agent will:

- Query the Log Analytics workspace for HTTP status codes, error rates, and latency
- Pull Syslog and Windows Event Log data from the VM-hosted backends
- Identify the top error patterns by frequency

### Step 2 — Query third-party telemetry

Now query the OpenTelemetry-monitored component. The Berlin MCP server is deployed with the lab infrastructure, and the `berlin-mcp` connector ships in `Student/Resources/azure-sre-agent-config/connectors/`.

> **Note:** If you ran `make connectors` during Challenge 01, the berlin-mcp connector was already registered at that point. The command is idempotent — running it again updates the connector with the latest `parking_berlin_mcp_url` Terraform output and is safe to re-run.

```bash
make connectors
```

The connector endpoint is sourced from the `parking_berlin_mcp_url` Terraform output during `make connectors`.

Then ask:

```text
/agent access-to-3rd-party-logs

Check the status of the Berlin parking API and provide a summary of calls, top errors, and average response time over the last hour.
```

> **`/agent` routing syntax:** Using `/agent <subagent-name>` at the start of a prompt routes it directly to that specialist. The `access-to-3rd-party-logs` subagent was configured in Challenge 05 and uses the `berlin-mcp` connector to reach the OpenTelemetry feed. You can also write `@access-to-3rd-party-logs:` as an equivalent shorthand — both forms work.

This triggers the agent to use the **OpenTelemetry MCP server** to retrieve metrics from the external telemetry API — data that never flows into Azure Monitor.

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
- [ ] **Explain to your coach** — why does the Berlin API use an MCP server instead of Azure Monitor? What architectural pattern does this represent in hybrid enterprise environments?

## Learning Resources

- [Azure Monitor Logs overview](https://learn.microsoft.com/en-us/azure/azure-monitor/logs/data-platform-logs)
- [Azure Monitor Agent — Syslog collection](https://learn.microsoft.com/en-us/azure/azure-monitor/agents/data-collection-syslog)
- [OpenTelemetry overview](https://opentelemetry.io/docs/)
- [Model Context Protocol — custom servers](https://modelcontextprotocol.io/docs/concepts/servers)

## Tips

- `/agent access-to-3rd-party-logs` routes the prompt to the `access-to-3rd-party-logs` subagent, which uses the `berlin-mcp` connector's OpenTelemetry tools. The `@access-to-3rd-party-logs:` shorthand is equivalent and can be used interchangeably.
- Log Analytics query latency for Syslog and Windows Event Logs is typically a few minutes behind real time. If the last-1-hour window returns no data, expand to last 6 hours.
