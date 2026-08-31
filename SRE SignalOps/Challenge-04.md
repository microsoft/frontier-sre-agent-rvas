[< Previous Challenge](./Challenge-03.md) — **[Home](./README.md)** — [Next Challenge >](./Challenge-05.md)

# Challenge 04 — Investigate an Evidence Blind Spot

> **Incident capability exercised in this challenge**: Evidence Availability · Source Validation · Fallback Reasoning

## Introduction

An SRE investigation can stall when the evidence source it depends on is stale, unauthorized, or unreachable. Investigate an evidence blind spot during the Grubify HTTP-health exercise and determine what can still be concluded safely.

## Description

> **Customer demo script:** Run `pwsh -File '.\SRE SignalOps\Scripts\Challenge-04.ps1'` to inventory live connectors and print the customer prompt. See the [presenter runbook](./Scripts/README.md).

Continue the reported Grubify HTTP-error scenario from Challenge 03. During triage, treat one unavailable, failed, or stale evidence source as the issue to investigate. If every live source is healthy, use a coach-provided failed-read result; do not disable a production connector to create the exercise.

Ask the SRE Agent to identify which evidence is needed, attempt harmless reads, and produce a matrix containing source, authentication state, authorization scope, reachability, data freshness, and allowed actions. Include GitHub, Azure telemetry, knowledge, and any configured MCP servers.

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

Classify the blind spot as configuration, authentication, authorization, network, schema, source-data, or freshness failure. State how it limits the incident diagnosis, which alternate evidence remains available, who owns the failed source, and what proof would restore confidence. Do not call a source healthy merely because it exists in configuration.

## Success Criteria

- [ ] The incident identifies the required evidence source and the failed or stale read that created the blind spot
- [ ] Each relevant source has an observed reachability test, timestamp, freshness assessment, and authorization scope
- [ ] The failure is classified without exposing credentials or inventing evidence
- [ ] The SRE Agent states the diagnostic limitation, alternate evidence path, owner, and recovery proof
- [ ] **Explain to your coach** — when should an SRE continue with partial evidence, and when should the investigation stop or escalate?

## Learning Resources

- [Azure SRE Agent connectors](https://learn.microsoft.com/en-us/azure/sre-agent/connectors)
- [Model Context Protocol overview](https://learn.microsoft.com/en-us/azure/sre-agent/mcp)
- [Azure SRE Agent API connectors](https://learn.microsoft.com/en-us/azure/sre-agent/api-reference#connector-types)

## Tips

- Use read-only calls for evidence validation.
- Never print connector secrets or bearer tokens.
- A successful stale read is still an incident evidence risk.
