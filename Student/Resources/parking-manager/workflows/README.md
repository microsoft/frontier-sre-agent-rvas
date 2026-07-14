# GitHub Actions Setup for Deployment

This document explains the GitHub Actions workflows configured for the Azure SRE Demo Manager project.

## Overview

The project uses multiple deployment workflows:

1. **Infrastructure** — Azure infrastructure provisioning using Bicep (IaC)
2. **Lisbon API** — Container App deployment
3. **Berlin API** — Container App deployment
4. **Berlin MCP Server** — Container App deployment (optional)
5. **Chaos Control** — Container App deployment
6. **Lisbon Chaos Alerts** — Azure Monitor scheduled query alerts deployment
7. **Madrid API** — Windows VM deployment (self-hosted runner)
8. **Paris API** — Linux VM deployment (self-hosted runner)
9. **Frontend** — Azure App Service deployment

---

## Infrastructure Workflows

### 1. Infrastructure What-If Analysis

**File:** `.github/workflows/infra-whatif.yml`

Runs a preview analysis of infrastructure changes for pull requests without making any actual deployments.

**Triggers:** Pull requests affecting `infrastructure/**` paths

**Required Secrets:** `AZURE_CREDENTIALS`

**How it works:**
1. Validates Bicep templates before merging
2. Runs `az deployment sub what-if` and posts results to the PR summary
3. Fails if template validation fails

---

### 2. Infrastructure Deployment (Manual)

**File:** `.github/workflows/infra-deploy.yml`

Manually deploys Azure infrastructure using Bicep templates at subscription scope.

**Trigger:** Manual only (`workflow_dispatch`)

**Required Secrets:** `AZURE_CREDENTIALS`

**Workflow Inputs:**
- `environment` — Environment to deploy (`dev`/`test`/`prod`) — **Required**
- `location` — Azure region (default: `westeurope`) — **Required**
- `parametersFile` — Path to parameters file — **Required**
- `confirmDeployment` — Type `DEPLOY` to confirm — **Required**

**What it deploys:**
- Hub resource group (VNet, Log Analytics, ACR)
- Frontend App Service
- Lisbon and Berlin Container Apps
- Madrid Windows VM and Paris Linux VM
- Chaos Control Container App
- Berlin MCP Server Container App (if `deployBerlinMcp=true`)

**After a successful deployment**, update GitHub repository variables with the resource names output by the workflow (see [Configuration Setup](#configuration-setup) below).

---

## Application Deployment Workflows

### 1. Lisbon API Deployment (Container App)

**File:** `.github/workflows/deploy-lisbon-api.yml`

**Triggers:** Push to `main` affecting `backend/lisbon-parking-api/**`

**Required Variables:** `AZURE_CONTAINER_REGISTRY`, `LISBON_RESOURCE_GROUP`

**Required Secrets:** `AZURE_CREDENTIALS`

---

### 2. Berlin API Deployment (Container App)

**File:** `.github/workflows/deploy-berlin-api.yml`

**Triggers:** Push to `main` affecting `backend/berlin-parking-api/**`

**Required Variables:** `AZURE_CONTAINER_REGISTRY`, `BERLIN_RESOURCE_GROUP`

**Required Secrets:** `AZURE_CREDENTIALS`

---

### 3. Berlin MCP Server Deployment (Container App)

**File:** `.github/workflows/deploy-berlin-mcp.yml`

Deploys the Berlin MCP Server to its own Azure Container App. Deployment is skipped gracefully if the resource group does not exist (enable by setting `deployBerlinMcp=true` in the infrastructure deployment).

**Triggers:** Push to `main` affecting `backend/berlin-mcp-server/**`, `infrastructure/modules/berlin-mcp-server.bicep`, or the workflow file itself. Also supports manual dispatch.

**Required Variables:** `AZURE_CONTAINER_REGISTRY`

**Required Secrets:**
- `AZURE_CREDENTIALS`
- `MCP_AUTH_TOKEN` — Bearer token for MCP server authentication (optional but recommended)

---

### 4. Frontend Deployment (App Service)

**File:** `.github/workflows/deploy-frontend.yml`

Deploys the React frontend and Express proxy server to Azure App Service.

**Triggers:** Push to `main` affecting `frontend/parking-manager/**`

**Required Variables:**
- `AZURE_WEBAPP_NAME` — App Service name
- `FRONTEND_RESOURCE_GROUP` — Resource group name
- `LISBON_API_URL`, `MADRID_API_URL`, `PARIS_API_URL`, `CHAOS_CONTROL_URL` — Backend API URLs baked into the React build

**Required Secrets:** `AZURE_CREDENTIALS`

---

### 5. Chaos Control Deployment (Container App)

**File:** `.github/workflows/deploy-chaos-control.yml`

**Triggers:** Push to `main` affecting `backend/chaos-control/**`

**Required Variables:**
- `AZURE_CONTAINER_REGISTRY`
- `CHAOS_CONTROL_RESOURCE_GROUP`
- `CHAOS_CONTROL_CONTAINER_APP_NAME`

**Required Secrets:** `AZURE_CREDENTIALS`

---

### 6. Lisbon Chaos Alerts Deployment (Azure Monitor)

**File:** `.github/workflows/deploy-lisbon-chaos-alerts.yml`

Deploys Azure Monitor scheduled query alerts from `infrastructure/modules/lisbon-chaos-alerts.bicep`.

**Triggers:** Push to `main` affecting `infrastructure/modules/lisbon-chaos-alerts.bicep`, or manual dispatch.

**Required Variables:**
- `HUB_RESOURCE_GROUP`
- `LISBON_LOG_ANALYTICS_WORKSPACE_ID` — Full resource ID of the Log Analytics workspace
- `LISBON_CHAOS_ALERTS_ACTION_GROUP_ID` — Full resource ID of the Action Group (optional)

**Required Secrets:** `AZURE_CREDENTIALS`

---

### 7. Madrid API Deployment (Windows VM)

**File:** `.github/workflows/deploy-madrid-api.yml`

Deploys the Madrid Parking API to the Windows VM using a self-hosted runner.

**Setup Required:** Install runner on the Madrid VM using `scripts/setup-madrid-runner.ps1`

**Runner Labels:** `self-hosted`, `windows`, `madrid-vm`

**Triggers:** Push to `main` affecting `backend/madrid-parking-api/**`

See [docs/madrid-deployment-setup.md](../docs/madrid-deployment-setup.md) for runner setup instructions.

---

### 8. Paris API Deployment (Linux VM)

**File:** `.github/workflows/deploy-paris-api.yml`

Deploys the Paris Parking API to the Linux VM using a self-hosted runner.

**Setup Required:** Install runner on the Paris VM using `scripts/setup-paris-runner.sh`

**Runner Labels:** `self-hosted`, `linux`, `paris-vm`

**Triggers:** Push to `main` affecting `backend/paris-parking-api/**`

See [docs/paris-deployment-setup.md](../docs/paris-deployment-setup.md) for runner setup instructions.

---

## Configuration Setup

### GitHub Secrets

Configure secrets in **Settings → Secrets and variables → Actions → Secrets**.

**`AZURE_CREDENTIALS`** (required for ALL workflows)

Create a service principal with Contributor access at the subscription level:

```bash
az ad sp create-for-rbac \
  --name "github-actions-parking-app" \
  --role contributor \
  --scopes /subscriptions/<subscription-id> \
  --sdk-auth
```

Copy the entire JSON output as the `AZURE_CREDENTIALS` secret value.

**Additional secrets for specific workflows:**

| Secret | Used by |
|--------|---------|
| `MCP_AUTH_TOKEN` | Berlin MCP Server workflow |

### GitHub Variables

Configure variables in **Settings → Secrets and variables → Actions → Variables**.

| Variable | Example value | Used by |
|----------|---------------|---------|
| `AZURE_CONTAINER_REGISTRY` | `<acr-name>` | Lisbon, Berlin, Chaos Control, Berlin MCP |
| `LISBON_RESOURCE_GROUP` | `rg-parking-lisbon-<env>` | Lisbon API |
| `BERLIN_RESOURCE_GROUP` | `rg-parking-berlin-<env>` | Berlin API |
| `CHAOS_CONTROL_RESOURCE_GROUP` | `rg-parking-chaos-<env>` | Chaos Control |
| `CHAOS_CONTROL_CONTAINER_APP_NAME` | `ca-chaos-control` | Chaos Control |
| `AZURE_WEBAPP_NAME` | `<app-service-name>` | Frontend |
| `FRONTEND_RESOURCE_GROUP` | `rg-parking-frontend-<env>` | Frontend |
| `HUB_RESOURCE_GROUP` | `rg-parking-hub-<env>` | Lisbon Chaos Alerts |
| `LISBON_API_URL` | `https://<lisbon-fqdn>` | Frontend build |
| `MADRID_API_URL` | `https://<madrid-fqdn>` | Frontend build |
| `PARIS_API_URL` | `https://<paris-fqdn>` | Frontend build |
| `CHAOS_CONTROL_URL` | `https://<chaos-fqdn>` | Frontend build |
| `LISBON_LOG_ANALYTICS_WORKSPACE_ID` | `/subscriptions/…/workspaces/<name>` | Lisbon Chaos Alerts |
| `LISBON_CHAOS_ALERTS_ACTION_GROUP_ID` | `/subscriptions/…/actionGroups/<name>` | Lisbon Chaos Alerts (optional) |

Retrieve your ACR name and other output values from the infrastructure deployment:
```bash
az deployment sub show --name main-deployment --query properties.outputs
```

### Infrastructure Parameters

The infrastructure deployment workflows use parameter files in `infrastructure/`:

- `main.parameters.json` — Default parameters used by workflows
- `main.parameters.example01.json` / `main.parameters.example02.json` — Example configurations

**Key Parameters:**

| Parameter | Description |
|-----------|-------------|
| `location` | Azure region (e.g., `westeurope`) |
| `environment` | Environment tag (`dev`, `test`, `prod`) |
| `adminUsername` | VM administrator username |
| `adminPassword` | VM administrator password |
| `createPublicIps` | Create public IPs for VMs (`true`/`false`) |
| `createContainerRegistry` | Create Azure Container Registry (`true`/`false`) |
| `deployBerlinMcp` | Deploy Berlin MCP Server Container App (`true`/`false`) |

> **Security note**: Never commit `adminPassword` or other secrets to source control. Use GitHub Secrets or Azure Key Vault references for sensitive values.

---

## Deployment Order (Fresh Setup)

1. **Deploy Infrastructure** — Run `Deploy Infrastructure to Azure` (manual workflow)
2. **Note output values** — Copy ACR name, resource group names, App Service name from workflow summary
3. **Update GitHub Variables** — Add all variables listed in the table above
4. **Deploy Applications** — Push to `main` or trigger workflows manually:
   - Lisbon API → Berlin API → Chaos Control → Frontend
   - Madrid/Paris APIs (requires self-hosted runners to be set up first)
   - Berlin MCP Server (if enabled)

---

## Troubleshooting

### Authentication Issues
- Verify `AZURE_CREDENTIALS` is valid and not expired
- Ensure the service principal has Contributor role at the subscription level

### Infrastructure Deployment Issues
- Validate Bicep syntax: `az bicep build --file infrastructure/main.bicep`
- Preview changes: `az deployment sub what-if …`
- Check deployment errors: `az deployment sub show --name main-deployment --query properties.error`

### Container App Deployment Issues
- Verify `AZURE_CONTAINER_REGISTRY` variable matches the actual ACR name
- Ensure the Container App environment is healthy
- Check Container App logs in Azure Portal

### VM Deployment Issues
- Verify the self-hosted runner is online (Settings → Actions → Runners)
- Check workflow logs in the Actions tab
- Ensure the VM is running and has outbound internet access (required for runner)
