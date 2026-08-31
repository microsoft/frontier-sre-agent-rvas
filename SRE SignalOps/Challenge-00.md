**[Home](./README.md)** — [Next Challenge >](./Challenge-01.md)

# Challenge 00 — Deploy the Workload with azd

> **Capabilities added in this challenge**: Azure Developer CLI · Azure Container Apps · Workspace-Backed Observability

## Introduction

The original MCAPS lab was deployed with Terraform. In this track, that deployment is the parity reference, not the deployment tool. Use the SignalOps azd project to create a new isolated food workload with the same operational roles: API, frontend, Container Apps environment, registry, Log Analytics, and workspace-backed Application Insights.

## Description

> **Deployment boundary:** This azd template deploys the approved SignalOps core subset. It does not reproduce the later hub/spoke IaaS, Firewall, Bastion, or parking-service scenarios.

Run these commands from **PowerShell 7** at the repository root.

### 1. Verify tools and Azure context

```powershell
$ErrorActionPreference = 'Stop'
$SubscriptionId = 'b1e100ca-fff5-4e0e-9847-2e44bf47b68c'
$TenantId = '16b3c013-d300-468d-ac64-7eda0820b6d3'
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

Do not rely on global azd defaults. The environment must show the MCAPS subscription ID and `swedencentral`.

### 3. Preview and deploy the workload

```powershell
azd provision --preview
azd up
```

Review the preview before continuing. Mission 00 should create only the isolated workload resource group; the agent resource group is introduced in Mission 01.

### 4. Verify workload parity

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

The deployed names include the azd environment token so they cannot take ownership of the Terraform-managed `rg-sre-spoke-foodapp-paas` resources.

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

- [ ] The active azd environment uses subscription `b1e100ca-fff5-4e0e-9847-2e44bf47b68c` and Sweden Central
- [ ] `azd provision --preview` is reviewed before `azd up`
- [ ] The isolated workload includes a registry, Container Apps environment, API, frontend, Log Analytics, and workspace-backed Application Insights
- [ ] Both Container Apps report `Running` and the frontend returns HTTP `200`
- [ ] The deployment does not modify the Terraform-managed resource groups
- [ ] **Explain to your coach** — how do azd environment values, Bicep parameters, and post-deployment checks prove workload parity without taking over Terraform state?

## Learning Resources

- [Azure Developer CLI environments](https://learn.microsoft.com/en-us/azure/developer/azure-developer-cli/manage-environment-variables)
- [Provision and deploy with azd](https://learn.microsoft.com/en-us/azure/developer/azure-developer-cli/azd-templates)
- [Azure Container Apps overview](https://learn.microsoft.com/en-us/azure/container-apps/overview)

## Tips

- Use `azd env list` and `azd env select signalops-core` when returning to an existing environment.
- If remote build is unavailable in the subscription, start Docker and set `remoteBuild: false` for both services.
- A successful ARM deployment is not enough; verify running state and the frontend response.
- Use `azd down` only when the coach explicitly authorizes removal of the isolated environment.
