[< Previous Challenge](./Challenge-00.md) — **[Home](./README.md)** — [Next Challenge >](./Challenge-02.md)

# Challenge 01 — Deploy the Agent Core with azd

> **Capabilities added in this challenge**: Azure SRE Agent · Managed Identity · Governed RBAC · Managed Scope

## Introduction

Extend the same azd environment with an isolated Azure SRE Agent. This stage mirrors the Terraform agent configuration while narrowing Contributor access to the azd-created workload resource group. Subscription-wide access remains monitoring-only.

## Description

Run this mission only after Mission 00 succeeds.

### 1. Select and verify the azd environment

```powershell
$ErrorActionPreference = 'Stop'
$SubscriptionId = 'b1e100ca-fff5-4e0e-9847-2e44bf47b68c'
$EnvironmentName = 'signalops-core'

Push-Location '.\SRE SignalOps'
azd env select $EnvironmentName
azd env get-values

if ((azd env get-value AZURE_SUBSCRIPTION_ID).Trim() -ne $SubscriptionId) {
  throw 'The azd environment is not targeting the approved MCAPS subscription.'
}
```

### 2. Enable the agent stage

```powershell
azd env set DEPLOY_AGENT true
azd env set DEPLOY_CONNECTORS false
azd provision --preview
```

The preview must retain the Mission 00 workload and add an agent resource group, user-assigned identity, agent Log Analytics workspace, Application Insights, Azure SRE Agent, and role assignments. It must not add connectors yet.

### 3. Provision the agent core

```powershell
azd provision
```

`azd provision` is intentional here: application images were already deployed in Mission 00, so there is no need to rebuild them.

### 4. Verify the deployed agent and RBAC

```powershell
$AgentResourceGroup = (azd env get-value AGENT_RESOURCE_GROUP).Trim()
$AgentName = (azd env get-value SRE_AGENT_NAME).Trim()
$AgentId = (azd env get-value SRE_AGENT_ID).Trim()
$ApiVersion = '2026-01-01'

$Agent = az rest --method GET `
  --url "https://management.azure.com$AgentId`?api-version=$ApiVersion" |
  ConvertFrom-Json

$Agent.properties | Select-Object provisioningState,powerState,agentEndpoint,actionConfiguration
$Agent.properties.knowledgeGraphConfiguration.managedResources

$IdentityName = "uai-$AgentName"
$Identity = az identity show --resource-group $AgentResourceGroup --name $IdentityName | ConvertFrom-Json
az role assignment list --assignee-object-id $Identity.principalId --all `
  --query '[].{Role:roleDefinitionName,Scope:scope}' -o table
Pop-Location
```

Expected configuration:

| Setting | azd deployment |
|---|---|
| Action mode | `Autonomous` |
| Access level | `High` |
| Managed resources | Subscription, isolated workload resource group, workload Log Analytics workspace |
| Workload write scope | Contributor on the isolated workload resource group only |
| Subscription scope | Monitoring Contributor |

## Success Criteria

- [ ] The agent stage preview is reviewed before provisioning
- [ ] The isolated agent reaches `Succeeded` and `Running`, with a populated endpoint
- [ ] Action mode is `Autonomous` and access level is `High`, matching the Terraform reference
- [ ] Managed resources include the subscription, isolated workload group, and workload Log Analytics workspace
- [ ] Contributor is limited to the isolated workload group; subscription access is monitoring-only
- [ ] **Explain to your coach** — why does the azd deployment preserve the lab capability while reducing the Terraform baseline's subscription-wide write blast radius?

## Learning Resources

- [Create an Azure SRE Agent](https://learn.microsoft.com/en-us/azure/sre-agent/create-agent)
- [Azure SRE Agent API reference](https://learn.microsoft.com/en-us/azure/sre-agent/api-reference)
- [Azure RBAC scope](https://learn.microsoft.com/en-us/azure/role-based-access-control/scope-overview)

## Tips

- Do not use `azd up` in this mission; only infrastructure changed.
- If the endpoint is empty, wait for provisioning to reach `Succeeded` and query ARM again.
- Treat Autonomous/High as a controlled workshop setting, not a production default.
