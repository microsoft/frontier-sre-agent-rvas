[< Lab Details](../../Lab-Details.md) — **[Home](./README.md)** — [Next Challenge >](./Challenge-01.md)

# Deployment stage 00 — Deploy the Workload with azd

> **Capabilities added in this challenge**: Azure Developer CLI · Azure Container Apps · Workspace-Backed Observability

## Introduction

Create the SignalOps customer workload from this project's azd service manifest and Bicep templates: Grubify API, frontend, Container Apps environment, registry, Log Analytics, and workspace-backed Application Insights.

## Description

> **Deployment boundary:** These stages prepare the SignalOps application and agent. Network and VM missions use their own coach-approved sandbox or evidence pack.

Run these commands from **PowerShell 7** at the repository root.

### 1. Verify tools and Azure context

```powershell
$ErrorActionPreference = 'Stop'
$SubscriptionId = Read-Host 'Approved Azure subscription ID'
$TenantId = Read-Host 'Microsoft Entra tenant ID'
$EnvironmentName = 'signalops-core'
$Location = 'swedencentral'

azd version
az version
azd auth login --tenant-id $TenantId
az login --tenant $TenantId
az account set --subscription $SubscriptionId
az account show --query '{Name:name,Id:id,Tenant:tenantId}' -o table
```

The azd project uses remote container builds, so participants do not need a local Docker daemon.

### 2. Create the isolated azd environment

```powershell
Push-Location '.\SRE SignalOps'
azd env new $EnvironmentName --subscription $SubscriptionId --location $Location
azd env set DEPLOY_AGENT false
azd env set DEPLOY_CONNECTORS false
azd env get-values
```

If the environment already exists, select it instead:

```powershell
azd env select $EnvironmentName
```

Do not rely on global azd defaults. Confirm that the environment shows your
approved subscription and selected region before provisioning.

### 3. Preview and deploy the workload

```powershell
azd provision --preview
azd up
```

Review the preview before continuing. Deployment stage 00 should create only the isolated workload resource group; the agent resource group is introduced in Deployment stage 01.

### 4. Verify workload readiness

```powershell
$WorkloadResourceGroup = (azd env get-value AZURE_RESOURCE_GROUP).Trim()
$FrontendUrl = (azd env get-value FRONTEND_URL).Trim()

az resource list --resource-group $WorkloadResourceGroup `
  --query '[].{Name:name,Type:type,Location:location}' -o table
az containerapp list --resource-group $WorkloadResourceGroup `
  --query '[].{Name:name,State:properties.runningStatus,FQDN:properties.configuration.ingress.fqdn}' -o table
Invoke-WebRequest -Uri $FrontendUrl -UseBasicParsing | Select-Object StatusCode

$AppInsightsName = (azd env get-value APPLICATIONINSIGHTS_NAME).Trim()
az monitor app-insights component show --resource-group $WorkloadResourceGroup --app $AppInsightsName `
  --query '{Name:name,Workspace:properties.WorkspaceResourceId}' -o table
Pop-Location
```

The deployed names include the azd environment token to keep this workload separate from other environments. Review the preview and stop if it targets resources outside the selected environment.

## Pre-flight Validation Checklist

```powershell
azd version
az version
azd auth login --check-status
az account show --query id -o tsv
az account show --query tenantId -o tsv
az bicep build --file '.\SRE SignalOps\infra\main.bicep' --stdout | Out-Null
```

## Success Criteria

- [ ] The active azd environment uses the approved subscription and selected region
- [ ] `azd provision --preview` is reviewed before `azd up`
- [ ] The isolated workload includes a registry, Container Apps environment, API, frontend, Log Analytics, and workspace-backed Application Insights
- [ ] Both Container Apps report `Running` and the frontend returns HTTP `200`
- [ ] The deployment modifies only resource groups owned by the selected azd environment
- [ ] **Explain to your coach** — how do azd environment values, Bicep parameters, and post-deployment checks prove workload readiness and isolation?

## Learning Resources

- [Azure Developer CLI environments](https://learn.microsoft.com/en-us/azure/developer/azure-developer-cli/manage-environment-variables)
- [Provision and deploy with azd](https://learn.microsoft.com/en-us/azure/developer/azure-developer-cli/azd-templates)
- [Azure Container Apps overview](https://learn.microsoft.com/en-us/azure/container-apps/overview)

## Tips

- Use `azd env list` and `azd env select signalops-core` when returning to an existing environment.
- If remote build is unavailable in the subscription, start Docker and set `remoteBuild: false` for both services.
- A successful ARM deployment is not enough; verify running state and the frontend response.
- Use `azd down` only when the coach explicitly authorizes removal of the isolated environment.
