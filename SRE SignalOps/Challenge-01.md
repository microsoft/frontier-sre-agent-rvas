[< Previous Challenge](./Challenge-00.md) — **[Home](./README.md)** — [Next Challenge >](./Challenge-02.md)

# Challenge 01 — Validate the Existing Agent Core

> **Capabilities added in this challenge**: Azure SRE Agent · PowerShell Context · Least-Privilege Scope

## Introduction

Validate the Azure SRE Agent control plane already deployed by Terraform. Do not create a second agent, register resources, or change its action configuration during this mission.

## Description

> **Customer demo script:** Run `pwsh -File '.\SRE SignalOps\Scripts\Challenge-01.ps1'`. This mission is read-only; `-Execute` is intentionally rejected. See the [presenter runbook](./Scripts/README.md).

### 1. Set the deployed context

```powershell
$SubscriptionId = (az account show --query id -o tsv).Trim()
$AgentResourceGroup = 'rg-sre-agent'
$AgentName = 'contoso-sre-agent-dev'
$Location = 'swedencentral'

az group show --name $AgentResourceGroup --query '{Name:name,Location:location,State:properties.provisioningState}' -o table
```

### 2. Confirm the existing agent

Open [Azure SRE Agent](https://sre.azure.com) and select the existing agent:

| Setting | Value |
|---|---|
| Subscription | `$SubscriptionId` |
| Resource group | `rg-sre-agent` |
| Name | `contoso-sre-agent-dev` |
| Region | Sweden Central |
| Managed resources | MCAPS subscription, SRE workload resource groups, and `law-contoso-sre-agent-dev` |
| Action mode | Autonomous |
| Access level | High |

These action settings describe the existing controlled lab. Do not change or broaden them during the mission; keep all demonstrations read-only or explicitly approval-gated.

### 3. Persist a reusable PowerShell context

Return to the repository root and create local session variables whenever you start a mission:

```powershell
$SignalOps = @{
  SubscriptionId = $SubscriptionId
  WorkloadResourceGroup = $WorkloadResourceGroup
  AgentResourceGroup = $AgentResourceGroup
  AgentName = $AgentName
  ApiVersion = '2025-05-01-preview'
}

$AgentId = "/subscriptions/$($SignalOps.SubscriptionId)/resourceGroups/$($SignalOps.AgentResourceGroup)/providers/Microsoft.App/agents/$($SignalOps.AgentName)"
$AgentUrl = "https://management.azure.com$AgentId?api-version=$($SignalOps.ApiVersion)"
```

### 4. Verify the live agent

```powershell
$Agent = az rest --method GET --url $AgentUrl | ConvertFrom-Json
$Agent.properties | Select-Object provisioningState,powerState,agentEndpoint,actionConfiguration
$Agent.properties.knowledgeGraphConfiguration.managedResources

az role assignment list --scope $AgentId --all -o table
```

The provisioning state must be `Succeeded`, power state must be `Running`, and `agentEndpoint` must be populated.

## Success Criteria

- [ ] `contoso-sre-agent-dev` reaches `Succeeded` and `Running` in Sweden Central
- [ ] The MCAPS subscription and all existing SRE workload resource groups are in managed scope
- [ ] Action mode is `Autonomous` and access level is `High`, matching the deployed Terraform baseline
- [ ] PowerShell retrieves the agent endpoint from ARM
- [ ] **Explain to your coach** — which controls keep a high-access autonomous lab agent from making unintended changes during a customer demonstration?

## Learning Resources

- [Create an Azure SRE Agent](https://learn.microsoft.com/en-us/azure/sre-agent/create-agent)
- [Azure SRE Agent API reference](https://learn.microsoft.com/en-us/azure/sre-agent/api-reference)
- [Azure SRE Agent RBAC roles](https://learn.microsoft.com/en-us/azure/sre-agent/api-reference#rbac-roles)

## Tips

- Do not run `az group create`, provider registration, or agent creation commands in this mission.
- Do not paste access tokens into a file or chat.
- A successful ARM deployment does not prove the data plane is ready; verify `agentEndpoint`.
