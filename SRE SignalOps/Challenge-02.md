[< Previous Challenge](./Challenge-01.md) — **[Home](./README.md)** — [Next Challenge >](./Challenge-03.md)

# Challenge 02 — Connect Ground Truth

> **Capabilities added in this challenge**: GitHub Source · Knowledge Documents · Azure Telemetry

## Introduction

An agent without context guesses. Connect three evidence planes: source code, operational knowledge, and live Azure telemetry. OAuth remains an interactive portal step; PowerShell proves the resulting configuration without exposing credentials.

## Description

> **Customer demo script:** Run `pwsh -File '.\SRE SignalOps\Scripts\Challenge-02.ps1'` to verify source, knowledge, and telemetry evidence planes. See the [presenter runbook](./Scripts/README.md).

### 1. Build the PowerShell API context

```powershell
$SubscriptionId = az account show --query id -o tsv
$AgentResourceGroup = 'rg-signalops-agent'
$AgentName = 'signalops-agent'
$ApiVersion = '2025-05-01-preview'
$AgentBase = "https://management.azure.com/subscriptions/$SubscriptionId/resourceGroups/$AgentResourceGroup/providers/Microsoft.App/agents/$AgentName"
$Agent = az rest --method GET --url "$AgentBase`?api-version=$ApiVersion" | ConvertFrom-Json
$Endpoint = $Agent.properties.agentEndpoint
$Token = az account get-access-token --resource https://azuresre.dev --query accessToken -o tsv
$Headers = @{ Authorization = "Bearer $Token" }
```

### 2. Connect GitHub

In the SRE Agent portal:

1. Open **Connectors**, add GitHub, and complete OAuth.
2. Open **Repositories** and connect `https://github.com/microsoft/frontier-sre-agent-rvas`.
3. Scope source questions to `Student/Resources/grubify/`.

Validate from PowerShell:

```powershell
Invoke-RestMethod -Uri "$Endpoint/api/v2/repos" -Headers $Headers |
  ConvertTo-Json -Depth 8
```

### 3. Add knowledge

Upload the relevant architecture and runbook documents from:

```text
Student/Resources/azure-sre-agent-config/knowledge/files/
```

Use **Knowledge** in the portal. Never upload `.env`, token, state, or secret files.

```powershell
Invoke-RestMethod -Uri "$Endpoint/api/v1/agentmemory/status" -Headers $Headers |
  ConvertTo-Json -Depth 8
Invoke-RestMethod -Uri "$Endpoint/api/v1/agentmemory/indexer-status" -Headers $Headers |
  ConvertTo-Json -Depth 8
```

### 4. Verify Azure evidence

Ask the agent to list the Grubify Container Apps and identify their Log Analytics workspace. Require resource IDs and query timestamps, then compare them with:

```powershell
Set-Location '.\Student\Resources\grubify'
$ResourceGroup = azd env get-value AZURE_RESOURCE_GROUP
az containerapp list --resource-group $ResourceGroup --query '[].{Name:name,State:properties.runningStatus,FQDN:properties.configuration.ingress.fqdn}' -o table
az monitor log-analytics workspace list --resource-group $ResourceGroup -o table
```

## Success Criteria

- [ ] GitHub OAuth is authorized and the repository connectivity test succeeds
- [ ] Knowledge status and indexer status are healthy
- [ ] The agent identifies live Grubify resources with timestamps and resource IDs
- [ ] No credentials or local state files are uploaded
- [ ] **Explain to your coach** — how do source code, knowledge, and telemetry answer different parts of an incident investigation?

## Learning Resources

- [Connect knowledge to Azure SRE Agent](https://learn.microsoft.com/en-us/azure/sre-agent/connect-knowledge)
- [Azure SRE Agent API reference](https://learn.microsoft.com/en-us/azure/sre-agent/api-reference)
- [Azure Container Apps log monitoring](https://learn.microsoft.com/en-us/azure/container-apps/log-monitoring)

## Tips

- Evidence has a timestamp; documentation has a publication date. Record both.
- OAuth authorization cannot be replaced by copying a token into Markdown.
- If indexing is still running, wait before judging response quality.
