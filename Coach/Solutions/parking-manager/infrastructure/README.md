# Azure Infrastructure for Parking Manager

This directory contains the subscription-scope Bicep templates used to provision the Azure infrastructure for the Parking Manager demo environment.

## Operating model

- `main.bicep` is the canonical infrastructure definition.
- `../workflows/infra-whatif.yml` is the preview path for infrastructure changes.
- `../workflows/infra-deploy.yml` is the canonical apply path for infrastructure changes.
- `../workflows/deploy-container-apps.yml` handles routine image rollouts for Lisbon, Berlin, Chaos Control, optional Berlin MCP, and `vm-health-control`.
- `../workflows/deploy-vm-apps.yml` handles routine application redeploys for Madrid and Paris.
- `../scripts/start-local-stack.sh` is local-only and does not deploy Azure resources.

## Architecture overview

The deployment is organized into multiple resource groups so networking, compute, monitoring, and app workloads can evolve independently.

### Resource groups

Base deployment creates these 7 resource groups:

1. `rg-parking-hub-{env}`
2. `rg-parking-frontend-{env}`
3. `rg-parking-lisbon-{env}`
4. `rg-parking-madrid-{env}`
5. `rg-parking-paris-{env}`
6. `rg-parking-berlin-{env}`
7. `rg-parking-chaos-{env}`

Optional resource group:

- `rg-parking-berlin-mcp-{env}` when `deployBerlinMcp=true`

### What each resource group contains

#### Hub resource group

`rg-parking-hub-{env}` contains shared infrastructure:

- Virtual network and subnets
- Network security groups
- Log Analytics workspace
- Deployment storage account
- Optional Azure Container Registry
- VM health table and alerting resources
- Data collection rules and endpoint for VM log collection
- Optional GitHub-hosted runner private networking resources

#### Frontend resource group

`rg-parking-frontend-{env}` contains:

- Linux App Service Plan
- Frontend App Service
- Application Insights

#### Lisbon resource group

`rg-parking-lisbon-{env}` contains:

- Lisbon Container App

#### Berlin resource group

`rg-parking-berlin-{env}` contains:

- Berlin Container App

#### Madrid resource group

`rg-parking-madrid-{env}` contains:

- Windows VM and related network resources

#### Paris resource group

`rg-parking-paris-{env}` contains:

- Ubuntu VM and related network resources

#### Chaos resource group

`rg-parking-chaos-{env}` contains:

- Chaos Control Container App
- VM Health Control Container App

#### Optional Berlin MCP resource group

`rg-parking-berlin-mcp-{env}` contains:

- Berlin MCP Container App
- Its monitoring resources when enabled

## Bootstrap and redeploy model

- Paris first-time VM bootstrap is handled by `modules/paris-api.bicep` using cloud-init.
- Madrid first-time VM bootstrap is handled by `modules/madrid-api.bicep`.
- VM health supporting infrastructure is provisioned by `main.bicep`, but normal day-2 rollouts happen through `../workflows/deploy-container-apps.yml`.
- Routine application rollouts should not use ad-hoc bootstrap scripts.

## Cost profile

The environment is designed for demo and workshop cost efficiency.

- Frontend App Service Plan: B1 Linux, about $13/month
- Madrid VM: Standard_B2s, about $30/month
- Paris VM: Standard_B2s, about $30/month
- Container Apps: consumption-based for Lisbon, Berlin, Chaos Control, and VM Health
- Azure Container Registry: Basic SKU when enabled
- Log Analytics and Application Insights: pay-as-you-go
- VM disks: StandardSSD_LRS
- Public IPs: optional Standard IPs

Estimated baseline monthly cost is typically around $110-$160, with Berlin MCP adding a small extra amount when enabled.

## Prerequisites

1. Azure CLI 2.50.0 or newer
2. Access to an Azure subscription with permissions to deploy at subscription scope
3. Bicep support through Azure CLI

Verify your setup:

```bash
az --version
az bicep version
```

## Parameters

### Required parameters

|Parameter|Description|Example|
|---|---|---|
|`location`|Azure region for the deployment|`swedencentral`|
|`environment`|Environment name|`dev`|
|`adminUsername`|Admin username for the VMs|`azureadmin`|
|`adminPassword`|Secure admin password for the VMs|`P@ssw0rd123!`|

### Common optional parameters

|Parameter|Description|Default|
|---|---|---|
|`lisbonContainerImage`|Lisbon image reference|`mcr.microsoft.com/azuredocs/containerapps-helloworld:latest`|
|`berlinContainerImage`|Berlin image reference|`mcr.microsoft.com/azuredocs/containerapps-helloworld:latest`|
|`chaosControlContainerImage`|Chaos Control image reference|`mcr.microsoft.com/azuredocs/containerapps-helloworld:latest`|
|`vmHealthControlContainerImage`|VM Health Control image reference|`mcr.microsoft.com/azuredocs/containerapps-helloworld:latest`|
|`containerRegistry`|External registry server when not creating ACR|`''`|
|`createPublicIps`|Create public IPs for Madrid and Paris|`true`|
|`deployMadridVm`|Deploy the Madrid VM|`true`|
|`deployParisVm`|Deploy the Paris VM|`true`|
|`deployBerlinMcp`|Deploy Berlin MCP resources|`false`|
|`vnetAddressPrefix`|Hub VNet CIDR|`10.0.0.0/16`|
|`vmSubnetPrefix`|VM subnet CIDR|`10.0.1.0/24`|
|`containerSubnetPrefix`|Container Apps subnet CIDR|`10.0.2.0/23`|
|`allowedSourceIpPrefix`|Source IP prefix for SSH/RDP|`*`|
|`githubOrgDatabaseId`|GitHub org database ID for runner networking|`''`|
|`createContainerRegistry`|Create ACR in the hub resource group|`true`|
|`containerRegistrySku`|ACR SKU|`Basic`|
|`githubActionsPrincipalId`|Service principal object ID for deployment storage access|`''`|

See `main.bicep` and `main.parameters.json` for the full current set.

## Deployment options

### Option 1: GitHub workflows

Preferred path:

1. Run `../workflows/infra-whatif.yml`
2. Review the result
3. Run `../workflows/infra-deploy.yml`

### Option 2: Direct CLI

Validate the deployment:

```bash
cd infrastructure
az deployment sub validate \
  --location swedencentral \
  --template-file main.bicep \
  --parameters @main.parameters.json \
  --parameters adminPassword='<your-secure-password>'
```

Deploy the infrastructure:

```bash
az deployment sub create \
  --location swedencentral \
  --template-file main.bicep \
  --parameters @main.parameters.json \
  --parameters adminPassword='<your-secure-password>'
```

### Option 3: Local helper script

```bash
cd infrastructure
./deploy.sh
```

`deploy.sh` is a convenience wrapper around validation and `az deployment sub create`.

## Monitoring deployment status

```bash
# List subscription-scope deployments
az deployment sub list --output table

# Show a specific deployment
az deployment sub show --name <deployment-name>

# Show deployment outputs
az deployment sub show --name <deployment-name> --query properties.outputs
```

## Key outputs

The deployment exposes outputs for:

- resource group names
- VNet and workspace names
- optional ACR name and login server
- deployment storage account details
- frontend URL
- Lisbon, Berlin, Madrid, Paris, Chaos Control, and VM Health endpoints
- optional Berlin MCP endpoint and related names

Example:

```bash
az deployment sub show --name <deployment-name> \
  --query "properties.outputs.{frontend:frontendUrl.value,lisbon:lisbonApiUrl.value,berlin:berlinApiUrl.value,madrid:madridApiUrl.value,paris:parisApiUrl.value,chaos:chaosControlUrl.value,vmHealth:vmHealthControlUrl.value}" \
  -o json
```

## Post-deployment responsibilities

### Container apps

Use `../workflows/deploy-container-apps.yml` for:

- Lisbon
- Berlin
- Chaos Control
- VM Health Control
- optional Berlin MCP

### VM applications

Use `../workflows/deploy-vm-apps.yml` for:

- Madrid application redeploys
- Paris application redeploys

### Frontend

Frontend hosting is provisioned by infrastructure, but there is currently no dedicated frontend deployment workflow in `../workflows/`.

Typical frontend build steps:

```bash
cd ../frontend/parking-manager
npm install
npm run build
```

### Local development

Use the local launcher only for a local demo stack:

```bash
cd ../scripts
./start-local-stack.sh
```

## Updating infrastructure

Infrastructure updates are idempotent. After changing Bicep files, rerun either:

- `../workflows/infra-whatif.yml` and `../workflows/infra-deploy.yml`, or
- `az deployment sub create ...`, or
- `./deploy.sh`

## Cleanup

Delete the environment by resource group:

```bash
az group delete --name rg-parking-hub-<env> --yes --no-wait
az group delete --name rg-parking-frontend-<env> --yes --no-wait
az group delete --name rg-parking-lisbon-<env> --yes --no-wait
az group delete --name rg-parking-berlin-<env> --yes --no-wait
az group delete --name rg-parking-madrid-<env> --yes --no-wait
az group delete --name rg-parking-paris-<env> --yes --no-wait
az group delete --name rg-parking-chaos-<env> --yes --no-wait

# Optional Berlin MCP
az group delete --name rg-parking-berlin-mcp-<env> --yes --no-wait
```

Azure resources continue billing until they are removed.

## Troubleshooting

### GitHub runners subnet deployment

If deployment fails with `InUseSubnetCannotBeDeleted` for `snet-github-runners`:

- pull the latest infrastructure code and redeploy
- keep the runner subnet managed by the dedicated GitHub runner networking module
- if needed, delete the stale GitHub Network Settings resource and rerun the deployment

Example cleanup:

```bash
az resource delete \
  --resource-group rg-parking-hub-<env> \
  --name github-actions-network-settings \
  --resource-type GitHub.Network/networkSettings
```

### Bicep compilation errors

```bash
az bicep build --file main.bicep
```

### Deployment errors

```bash
az deployment sub show \
  --name <deployment-name> \
  --query properties.error
```

### VM access problems

- verify the VM is running
- verify a public IP exists when `createPublicIps=true`
- review NSG rules and `allowedSourceIpPrefix`
- reset credentials if needed

### Container App rollout problems

- inspect container logs
- verify the image exists in ACR or the configured registry
- verify environment variables and networking

### Security considerations

This repository is intended for demo and workshop scenarios. Review the defaults before exposing the environment publicly.

1. Restrict SSH and RDP access by setting `allowedSourceIpPrefix` to a known IP range.
2. Consider `createPublicIps=false` and use Azure Bastion or private access patterns.
3. Replace self-signed certificates with managed or trusted certificates for production use.
4. Use Key Vault for secrets and sensitive deployment values.
5. Prefer managed identities over long-lived credentials where possible.
6. Review NSG rules and inbound exposure regularly.

Example restricted deployment:

```bash
az deployment sub create \
  --location swedencentral \
  --template-file main.bicep \
  --parameters @main.parameters.json \
  --parameters allowedSourceIpPrefix='<your-ip>/32' \
  --parameters adminPassword='<your-secure-password>'
```

### Networking summary

- Hub VNet: `10.0.0.0/16`
- VM subnet: `10.0.1.0/24`
- Container Apps subnet: `10.0.2.0/23`
- Optional GitHub-hosted runners subnet: `10.0.3.0/24`

### Monitoring notes

The deployment centralizes monitoring through Log Analytics and Application Insights.

```kusto
AppRequests
| where TimeGenerated > ago(1h)
| summarize count() by cloud_RoleName, resultCode
```

```kusto
Perf
| where TimeGenerated > ago(1h)
| where ObjectName == "Processor" and CounterName == "% Processor Time"
| summarize avg(CounterValue) by Computer
```

## Related docs

- `QUICK_REFERENCE.md`
- `../workflows/README.md`
- `../scripts/README.md`
