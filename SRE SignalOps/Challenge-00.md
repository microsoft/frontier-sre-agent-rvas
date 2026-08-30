**[Home](./README.md)** — [Next Challenge >](./Challenge-01.md)

# Challenge 00 — Validate the Existing Workload

> **Capabilities added in this challenge**: Existing Grubify Workload · Azure Container Apps · Read-Only Validation

## Introduction

SignalOps begins with the existing MCAPS hybrid lab. The workload was deployed with Terraform and must not be redeployed during this track. Validate the live Grubify-compatible food application and its observability resources from Windows PowerShell.

## Description

> **Customer demo script:** Run `pwsh -File '.\SRE SignalOps\Scripts\Challenge-00.ps1'`. This mission is read-only; `-Execute` is intentionally rejected. See the [presenter runbook](./Scripts/README.md).

Open **PowerShell 7** at the repository root and run the following configuration sequence.

### 1. Verify the tools

```powershell
$ErrorActionPreference = 'Stop'
az version
git --version
jq --version
yq --version
```

If the configuration tools are missing, install them and open a new PowerShell window:

```powershell
winget install --id jqlang.jq --exact
winget install --id MikeFarah.yq --exact
```

### 2. Verify the deployed subscription

```powershell
$ExpectedSubscription = 'MCAPS-Hybrid-REQ-150072-2026-rakau'
$Account = az account show | ConvertFrom-Json
if ($Account.name -ne $ExpectedSubscription) {
	throw "Select $ExpectedSubscription before continuing. No resources were changed."
}
az account show --query '{Subscription:name, Id:id, Tenant:tenantId}' -o table
```

### 3. Inventory the existing workload

```powershell
$WorkloadResourceGroup = 'rg-sre-spoke-foodapp-paas'
az group show --name $WorkloadResourceGroup --query '{Name:name,Location:location,State:properties.provisioningState}' -o table
az resource list --resource-group $WorkloadResourceGroup --query '[].{Name:name,Type:type,Location:location}' -o table
```

The expected workload includes `ca-food-api`, `ca-food-frontend`, `cae-food`, `appi-food`, `vnet-food`, NSGs, routes, and alerting resources in Sweden Central. Its shared Log Analytics workspace is `law-rgn3ao` in `rg-sre-hub-connectivity`.

### 4. Validate the live services

```powershell
$Apps = az containerapp list --resource-group $WorkloadResourceGroup | ConvertFrom-Json
$Apps | Select-Object name,@{n='State';e={$_.properties.runningStatus}},@{n='FQDN';e={$_.properties.configuration.ingress.fqdn}}

$Frontend = $Apps | Where-Object name -eq 'ca-food-frontend'
$FrontendUrl = "https://$($Frontend.properties.configuration.ingress.fqdn)"
Invoke-WebRequest -Uri $FrontendUrl -UseBasicParsing | Select-Object StatusCode

az monitor app-insights component show --resource-group $WorkloadResourceGroup --app appi-food --query '{Name:name,Workspace:properties.WorkspaceResourceId}' -o table
az monitor log-analytics workspace show --resource-group rg-sre-hub-connectivity --workspace-name law-rgn3ao --query '{Name:name,Location:location,State:provisioningState}' -o table
```

The current API does not expose `/` or `/health`; HTTP `404` on those paths is not a deployment failure. Use Container App running state, frontend HTTP `200`, and telemetry resources as the baseline checks.

## Pre-flight Validation Checklist

```powershell
az account show --query id -o tsv
az account show --query name -o tsv
az group show --name rg-sre-spoke-foodapp-paas --query properties.provisioningState -o tsv
az containerapp list --resource-group rg-sre-spoke-foodapp-paas --query '[].{Name:name,State:properties.runningStatus}' -o table
jq --version
yq --version
```

## Success Criteria

- [ ] The active subscription is `MCAPS-Hybrid-REQ-150072-2026-rakau`
- [ ] The existing food workload resources are present in `rg-sre-spoke-foodapp-paas` in Sweden Central
- [ ] `ca-food-api` and `ca-food-frontend` report `Running`, and the frontend returns HTTP `200`
- [ ] `appi-food` is workspace-backed by `law-rgn3ao`
- [ ] **Explain to your coach** — which checks prove the existing application is available without redeploying or changing it?

## Learning Resources

- [Azure Container Apps overview](https://learn.microsoft.com/en-us/azure/container-apps/overview)
- [Monitor Azure Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/observability)
- [Workspace-based Application Insights](https://learn.microsoft.com/en-us/azure/azure-monitor/app/create-workspace-resource)

## Tips

- Run all commands in PowerShell 7, not Command Prompt.
- Treat Terraform state and credentials as sensitive; do not display or upload them.
- Do not run `terraform apply`, `terraform destroy`, `azd up`, or `azd down` during this mission.
