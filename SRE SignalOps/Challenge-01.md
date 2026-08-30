[< Previous Challenge](./Challenge-00.md) — **[Home](./README.md)** — [Next Challenge >](./Challenge-02.md)

# Challenge 01 — Establish the Agent Core

> **Capabilities added in this challenge**: Azure SRE Agent · PowerShell Context · Least-Privilege Scope

## Introduction

Create the control plane that will operate on the Grubify environment. This mission uses the Azure SRE Agent portal for the preview resource workflow and PowerShell for deterministic scope, identity, and readiness checks.

## Description

> **Customer demo script:** Run `pwsh -File '.\SRE SignalOps\Scripts\Challenge-01.ps1'`. Add `-Execute` only to create the agent resource group and register the provider. See the [presenter runbook](./Scripts/README.md).

### 1. Restore the azd deployment context

```powershell
Set-Location '.\Student\Resources\grubify'
azd env select signalops

$SubscriptionId = azd env get-value AZURE_SUBSCRIPTION_ID
$WorkloadResourceGroup = azd env get-value AZURE_RESOURCE_GROUP
$Location = 'eastus2'
$AgentResourceGroup = 'rg-signalops-agent'
$AgentName = 'signalops-agent'

az account set --subscription $SubscriptionId
az group create --name $AgentResourceGroup --location $Location -o table
az provider register --namespace Microsoft.App --wait
```

### 2. Create the agent

Open [Azure SRE Agent](https://sre.azure.com), select **Create agent**, and use:

| Setting | Value |
|---|---|
| Subscription | `$SubscriptionId` |
| Resource group | `rg-signalops-agent` |
| Name | `signalops-agent` |
| Region | East US 2 |
| Managed resource group | The value in `$WorkloadResourceGroup` |
| Action mode | Review |

Keep action mode at **Review**. Do not enable automatic writes during setup.

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
$Agent.properties | Select-Object provisioningState, powerState, agentEndpoint

az role assignment list --scope $AgentId --all -o table
```

The provisioning state must be `Succeeded`, power state must be `Running`, and `agentEndpoint` must be populated.

## Success Criteria

- [ ] The provider is registered and the agent reaches `Succeeded`
- [ ] The Grubify resource group is in the agent's managed scope
- [ ] Action mode is `Review`
- [ ] PowerShell retrieves the agent endpoint from ARM
- [ ] **Explain to your coach** — why should the agent start in Review mode, and which later evidence would justify broader autonomy?

## Learning Resources

- [Create an Azure SRE Agent](https://learn.microsoft.com/en-us/azure/sre-agent/create-agent)
- [Azure SRE Agent API reference](https://learn.microsoft.com/en-us/azure/sre-agent/api-reference)
- [Azure SRE Agent RBAC roles](https://learn.microsoft.com/en-us/azure/sre-agent/api-reference#rbac-roles)

## Tips

- Supported regions can change during preview; use a currently supported region if East US 2 is unavailable.
- Do not paste access tokens into a file or chat.
- A successful ARM deployment does not prove the data plane is ready; verify `agentEndpoint`.
