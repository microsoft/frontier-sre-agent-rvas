[< Previous Challenge](./Challenge-03.md) — **[Home](./README.md)** — [Next Challenge >](./Challenge-05.md)

# Challenge 04 — Discover Connected Systems

> **Capabilities added in this challenge**: Connector Inventory · MCP Reachability · Trust Boundaries

## Introduction

A connector icon is not proof of a working system. Build a live connection map that distinguishes configured, authenticated, reachable, and authorized systems.

## Description

> **Customer demo script:** Run `pwsh -File '.\SRE SignalOps\Scripts\Challenge-04.ps1'` to inventory live connectors and print the customer prompt. See the [presenter runbook](./Scripts/README.md).

Ask the agent to enumerate every connected system and produce a matrix containing connector type, endpoint class, authentication state, reachable tools, data freshness, and allowed actions. Include GitHub, Azure telemetry, knowledge, and any configured MCP servers.

Challenge 02 provides the required GitHub, Azure telemetry, and knowledge connections. MCP, Teams, Outlook, and other third-party connectors are external integrations: include them only when a coach or customer has configured and authorized them. Reference or `example-*` manifests do not prove a live connector exists.

From PowerShell, compare the answer with the control plane:

```powershell
$SubscriptionId = az account show --query id -o tsv
$AgentResourceGroup = 'rg-signalops-agent'
$AgentName = 'signalops-agent'
$ApiVersion = '2025-05-01-preview'
$Url = "https://management.azure.com/subscriptions/$SubscriptionId/resourceGroups/$AgentResourceGroup/providers/Microsoft.App/agents/$AgentName/DataConnectors?api-version=$ApiVersion"
az rest --method GET --url $Url --query 'value[].{Name:name,Type:properties.dataConnectorType,State:properties.provisioningState}' -o table
```

Run one harmless read test per connector. Record failures as authentication, network, authorization, schema, or freshness failures. Do not call a connector healthy merely because it exists in configuration.

## Success Criteria

- [ ] The connection map includes every configured system
- [ ] Each system has an observed reachability test and timestamp
- [ ] Authentication and authorization are reported separately
- [ ] Failed or stale connections are clearly labeled
- [ ] **Explain to your coach** — why is configured connectivity weaker evidence than a successful read with known scope?

## Learning Resources

- [Azure SRE Agent connectors](https://learn.microsoft.com/en-us/azure/sre-agent/connectors)
- [Model Context Protocol overview](https://learn.microsoft.com/en-us/azure/sre-agent/mcp)
- [Azure SRE Agent API connectors](https://learn.microsoft.com/en-us/azure/sre-agent/api-reference#connector-types)

## Tips

- Use read-only calls for discovery.
- Never print connector secrets or bearer tokens.
- Treat stale successful results as a freshness risk.
