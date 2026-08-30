**[Home](./README.md)** — [Next Challenge >](./Challenge-01.md)

# Challenge 00 — Launch the Workload

> **Capabilities added in this challenge**: Azure Developer CLI · Grubify on Container Apps · Repeatable Environment

## Introduction

SignalOps begins with a workload you can see, query, and break safely. Deploy Grubify with Azure Developer CLI (`azd`) from Windows PowerShell. Terraform is not used in this track.

## Description

> **Customer demo script:** Run `pwsh -File '.\SRE SignalOps\Scripts\Challenge-00.ps1'` for a preview, or add `-Execute` to deploy. See the [presenter runbook](./Scripts/README.md).

Open **PowerShell 7** at the repository root and run the following configuration sequence.

### 1. Verify the tools

```powershell
$ErrorActionPreference = 'Stop'
az version
azd version
docker version
git --version
jq --version
yq --version
```

Start Docker Desktop if `docker version` cannot reach the engine. If the configuration tools are missing, install them and open a new PowerShell window:

```powershell
winget install --id jqlang.jq --exact
winget install --id MikeFarah.yq --exact
```

### 2. Authenticate and select a subscription

```powershell
az login --use-device-code
azd auth login

$SubscriptionId = '<your-subscription-id>'
az account set --subscription $SubscriptionId
az account show --query '{Subscription:name, Id:id, Tenant:tenantId}' -o table
```

### 3. Create the azd environment

```powershell
Push-Location '.\Student\Resources\grubify'

azd env new signalops
azd env set AZURE_SUBSCRIPTION_ID $SubscriptionId
azd env set AZURE_LOCATION eastus2
azd env list
```

If `signalops` already exists, select it with `azd env select signalops`.

### 4. Preview and deploy

```powershell
azd provision --preview
azd up
```

`azd up` provisions an environment-specific resource group, Container Registry, Container Apps environment, Log Analytics workspace, Application Insights resource, API, frontend, managed identities, and `AcrPull` role assignments. It then builds and deploys both services.

### 5. Capture and validate outputs

```powershell
azd env get-values
$FrontendUrl = azd env get-value FRONTEND_URL
$ApiUrl = azd env get-value API_BASE_URL

Invoke-WebRequest -Uri $FrontendUrl -UseBasicParsing | Select-Object StatusCode
Invoke-RestMethod -Uri "$ApiUrl/health"
az resource list --resource-group (azd env get-value AZURE_RESOURCE_GROUP) -o table
Pop-Location
```

## Pre-flight Validation Checklist

```powershell
az account show --query id -o tsv
azd env get-value AZURE_RESOURCE_GROUP
azd env get-value FRONTEND_URL
azd env get-value API_BASE_URL
docker info --format '{{.ServerVersion}}'
jq --version
yq --version
```

## Success Criteria

- [ ] `azd up` completes without Terraform
- [ ] The frontend and API endpoints return successful responses
- [ ] The selected subscription, region, resource group, and URLs are visible through `azd env get-values`
- [ ] The deployment uses an environment-specific resource group and globally unique registry name
- [ ] **Explain to your coach** — what state does azd retain, and why is an environment name safer than manually repeating resource names?

## Learning Resources

- [Azure Developer CLI overview](https://learn.microsoft.com/en-us/azure/developer/azure-developer-cli/overview)
- [Azure Developer CLI environments](https://learn.microsoft.com/en-us/azure/developer/azure-developer-cli/manage-environment-variables)
- [Deploy to Azure Container Apps with azd](https://learn.microsoft.com/en-us/azure/developer/azure-developer-cli/container-apps-workflows)

## Tips

- Run all commands in PowerShell 7, not Command Prompt.
- Keep `.azure/` local environment values out of screenshots if they contain secrets.
- `azd down` removes this workload later; do not run it during the missions.
