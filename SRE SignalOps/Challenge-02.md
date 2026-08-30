[< Previous Challenge](./Challenge-01.md) — **[Home](./README.md)** — [Next Challenge >](./Challenge-03.md)

# Challenge 02 — Validate Existing Ground Truth

> **Capabilities added in this challenge**: GitHub Source · Knowledge Documents · Azure Telemetry

## Introduction

An agent without context guesses. Audit the evidence planes currently available to `contoso-sre-agent-dev` without adding connectors or uploading content. The deployed baseline has Azure telemetry; repository and knowledge readiness must be reported exactly as observed.

## Description

> **Customer demo script:** Run `pwsh -File '.\SRE SignalOps\Scripts\Challenge-02.ps1'` to verify source, knowledge, and telemetry evidence planes. See the [presenter runbook](./Scripts/README.md).

### 1. Build the PowerShell API context

```powershell
$SubscriptionId = az account show --query id -o tsv
$AgentResourceGroup = 'rg-sre-agent'
$AgentName = 'contoso-sre-agent-dev'
$ApiVersion = '2025-05-01-preview'
$AgentBase = "https://management.azure.com/subscriptions/$SubscriptionId/resourceGroups/$AgentResourceGroup/providers/Microsoft.App/agents/$AgentName"
$Agent = az rest --method GET --url "$AgentBase`?api-version=$ApiVersion" | ConvertFrom-Json
$Endpoint = $Agent.properties.agentEndpoint
$Token = az account get-access-token --resource https://azuresre.dev --query accessToken -o tsv
$Headers = @{ Authorization = "Bearer $Token" }
```

### 2. Inspect source connectivity

List the current repository configuration. The verified baseline currently returns no connected repositories; record that as a source-evidence gap rather than authorizing OAuth during the mission.

```powershell
Invoke-RestMethod -Uri "$Endpoint/api/v2/repos" -Headers $Headers |
  ConvertTo-Json -Depth 8
```

### 3. Inspect knowledge

Query knowledge status without uploading or deleting documents:

```powershell
Invoke-RestMethod -Uri "$Endpoint/api/v1/agentmemory/status" -Headers $Headers |
  ConvertTo-Json -Depth 8
Invoke-RestMethod -Uri "$Endpoint/api/v1/agentmemory/indexer-status" -Headers $Headers |
  ConvertTo-Json -Depth 8
Invoke-RestMethod -Uri "$Endpoint/api/v1/AgentMemory/files" -Headers $Headers |
  ConvertTo-Json -Depth 8
```

The verified baseline has Agent Memory enabled, an indexer whose last execution succeeded, and zero uploaded files. Report the service as healthy but its document knowledge as empty.

### 4. Verify the deployed Azure evidence

Confirm the two deployed ARM connectors, then compare the food workload with live Azure state:

```powershell
$ResourceGroup = 'rg-sre-spoke-foodapp-paas'
az rest --method GET --url "$AgentBase/DataConnectors?api-version=$ApiVersion" --query 'value[].{Name:name,Type:properties.dataConnectorType,Source:properties.dataSource}' -o table
az containerapp list --resource-group $ResourceGroup --query '[].{Name:name,State:properties.runningStatus,FQDN:properties.configuration.ingress.fqdn}' -o table
az monitor app-insights component show --resource-group $ResourceGroup --app appi-food --query '{Name:name,Workspace:properties.WorkspaceResourceId}' -o table
az monitor log-analytics workspace show --resource-group rg-sre-hub-connectivity --workspace-name law-rgn3ao -o table
```

## Success Criteria

- [ ] The repository list is empty and is accurately reported as a current source-evidence gap
- [ ] Agent Memory is enabled, the last indexer execution succeeded, and the zero-file document inventory is reported accurately
- [ ] `log-analytics` and `application-insights` connectors are present
- [ ] The agent identifies the live food workload and shared Log Analytics workspace with timestamps and resource IDs
- [ ] No credentials or local state files are uploaded
- [ ] **Explain to your coach** — how do source code, knowledge, and telemetry answer different parts of an incident investigation?

## Learning Resources

- [Connect knowledge to Azure SRE Agent](https://learn.microsoft.com/en-us/azure/sre-agent/connect-knowledge)
- [Azure SRE Agent API reference](https://learn.microsoft.com/en-us/azure/sre-agent/api-reference)
- [Azure Container Apps log monitoring](https://learn.microsoft.com/en-us/azure/container-apps/log-monitoring)

## Tips

- Evidence has a timestamp; documentation has a publication date. Record both.
- Do not authorize OAuth or upload knowledge during this validation mission.
- An enabled memory service with zero files is healthy infrastructure, not populated document knowledge.
