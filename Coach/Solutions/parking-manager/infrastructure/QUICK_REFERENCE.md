# Quick Reference Guide

## Operating model

- The canonical Azure deployment path is under `../workflows/`.
- Use `infra-whatif.yml` before `infra-deploy.yml` for infrastructure changes.
- Use `deploy-container-apps.yml` for Lisbon, Berlin, Chaos Control, and `vm-health-control` image rollouts.
- Use `deploy-vm-apps.yml` for Paris and Madrid application redeploys.
- Use `../scripts/start-local-stack.sh` only for local development.

## Azure resources created

### Resource groups

Base deployment creates 7 resource groups:

- `rg-parking-hub-{env}`
- `rg-parking-frontend-{env}`
- `rg-parking-lisbon-{env}`
- `rg-parking-madrid-{env}`
- `rg-parking-paris-{env}`
- `rg-parking-berlin-{env}`
- `rg-parking-chaos-{env}`

Optional resource group:

- `rg-parking-berlin-mcp-{env}` when `deployBerlinMcp=true`

### What lives where

- `rg-parking-hub-{env}`: VNet, subnets, NSGs, Log Analytics, deployment storage, optional ACR, VM health table and alerts, DCR/DCE resources, optional GitHub runner networking
- `rg-parking-frontend-{env}`: App Service Plan, App Service, Application Insights
- `rg-parking-lisbon-{env}`: Lisbon Container App
- `rg-parking-berlin-{env}`: Berlin Container App
- `rg-parking-madrid-{env}`: Madrid VM and related VM resources
- `rg-parking-paris-{env}`: Paris VM and related VM resources
- `rg-parking-chaos-{env}`: Chaos Control Container App and `vm-health-control`
- `rg-parking-berlin-mcp-{env}`: Berlin MCP Container App and monitoring resources when enabled

## Cost snapshot

Approximate monthly baseline, excluding unusual traffic and log spikes:

|Resource|SKU or shape|Estimated cost|
|---|---|---|
|Frontend App Service Plan|B1 Linux|$13|
|Madrid VM|Standard_B2s|$30|
|Paris VM|Standard_B2s|$30|
|Container Apps|Consumption for Lisbon, Berlin, Chaos, VM Health|$15-35|
|Optional Berlin MCP|Consumption|$5-10|
|Azure Container Registry|Basic|$5|
|Log Analytics and Application Insights|Pay-as-you-go|$10-25|
|Storage, disks, public IPs|StandardSSD_LRS and Standard IP|$10-20|
|**Total baseline**||**$110-160**|
|**With Berlin MCP enabled**||**$115-170**|

## Network configuration

### VNet address space

- Hub VNet: `10.0.0.0/16`
- VM subnet: `10.0.1.0/24`
- Container Apps subnet: `10.0.2.0/23`
- Optional GitHub-hosted runners subnet: `10.0.3.0/24`

### Access rules

- SSH access to Paris and RDP access to Madrid are controlled by `allowedSourceIpPrefix`.
- Default value is `*`; tighten this for real environments.
- Paris uses port `3003` and Madrid uses port `3002` for app traffic.

## Canonical deployment commands

### Workflow order

1. Run `infra-whatif.yml`
2. Run `infra-deploy.yml`
3. Run `deploy-container-apps.yml`
4. Run `deploy-vm-apps.yml`

### CLI validation and deployment

```bash
# Validate the subscription-scope deployment
cd infrastructure
az deployment sub validate \
  --location swedencentral \
  --template-file main.bicep \
  --parameters @main.parameters.json \
  --parameters adminPassword='<secure-password>'

# Deploy directly with the parameters file
az deployment sub create \
  --location swedencentral \
  --template-file main.bicep \
  --parameters @main.parameters.json \
  --parameters adminPassword='<secure-password>'
```

### Helper script

```bash
cd infrastructure
./deploy.sh
```

## Common commands

### Deployment status

```bash
# List subscription deployments
az deployment sub list --output table

# Show a specific deployment
az deployment sub show --name <deployment-name>

# Show deployment outputs
az deployment sub show --name <deployment-name> --query properties.outputs
```

### Useful outputs

```bash
az deployment sub show --name <deployment-name> \
  --query "properties.outputs.{frontend:frontendUrl.value,lisbon:lisbonApiUrl.value,madrid:madridApiUrl.value,paris:parisApiUrl.value,berlin:berlinApiUrl.value,chaos:chaosControlUrl.value,vmHealth:vmHealthControlUrl.value}" \
  -o json
```

### Access VMs

```bash
# Paris VM
ssh azureadmin@<paris-vm-fqdn>

# Madrid VM
mstsc /v:<madrid-vm-fqdn>

# Reset the Madrid VM password
az vm user update \
  --resource-group rg-parking-madrid-dev \
  --name vm-madrid-api \
  --username azureadmin \
  --password 'NewPassword123!'
```

### Container App image updates

```bash
# Example: Lisbon
az containerapp update \
  --name ca-parking-lisbon \
  --resource-group rg-parking-lisbon-dev \
  --image <your-registry>.azurecr.io/lisbon-parking-api:latest

# Example: Chaos Control
az containerapp update \
  --name ca-chaos-control \
  --resource-group rg-parking-chaos-dev \
  --image <your-registry>.azurecr.io/chaos-control:latest

# View logs
az containerapp logs show \
  --name ca-parking-lisbon \
  --resource-group rg-parking-lisbon-dev \
  --follow
```

### Frontend operations

```bash
# Build the frontend bundle
cd ../frontend/parking-manager
npm install
npm run build

# Tail frontend logs
az webapp log tail \
  --name <frontend-app-name> \
  --resource-group rg-parking-frontend-dev
```

### Monitoring

```bash
# Query Log Analytics
az monitor log-analytics query \
  --workspace <workspace-id> \
  --analytics-query "AppRequests | where TimeGenerated > ago(1h) | summarize count() by resultCode"

# View Application Insights metrics
az monitor app-insights metrics show \
  --app <app-insights-name> \
  --resource-group <rg-name> \
  --metric requests/count
```

## Workflow configuration

### Required secret

- `AZURE_CREDENTIALS`

### Required workflow variables

- `AZURE_CONTAINER_REGISTRY`
- `LISBON_RESOURCE_GROUP`
- `BERLIN_RESOURCE_GROUP`
- `CHAOS_CONTROL_RESOURCE_GROUP`
- `CHAOS_CONTROL_CONTAINER_APP_NAME`
- `PARIS_VM_NAME`
- `PARIS_RESOURCE_GROUP`
- `MADRID_VM_NAME`
- `MADRID_RESOURCE_GROUP`
- `DEPLOYMENT_STORAGE_ACCOUNT`
- `CHAOS_CONTROL_URL`

Optional workflow variables:

- `BERLIN_MCP_RESOURCE_GROUP`
- `VM_HEALTH_RESOURCE_GROUP`
- `VM_HEALTH_CONTAINER_APP_NAME`

## Post-deployment checklist

### After infrastructure deployment

- [ ] Confirm deployment outputs were generated
- [ ] Confirm ACR exists if `createContainerRegistry=true`
- [ ] Confirm deployment storage exists and is reachable
- [ ] Review NSG access and tighten `allowedSourceIpPrefix`

### After application deployment

- [ ] Roll out Lisbon, Berlin, Chaos Control, and `vm-health-control`
- [ ] Redeploy Madrid and Paris application code
- [ ] Verify frontend proxy configuration and app settings
- [ ] Verify Berlin MCP only if `deployBerlinMcp=true`

### Monitoring and security

- [ ] Verify VM log collection is working for Madrid and Paris
- [ ] Verify Lisbon chaos alerts and VM health alerts are firing correctly
- [ ] Review Log Analytics retention and ingestion volume
- [ ] Rotate VM passwords and review public IP exposure

## Troubleshooting

### Deployment fails

1. Check deployment errors: `az deployment sub show --name <name> --query properties.error`
2. Verify Contributor-level permissions at subscription scope
3. Check regional quota and naming conflicts
4. Confirm `adminPassword` meets Azure VM requirements

### Cannot connect to VMs

1. Verify the VM is running: `az vm get-instance-view`
2. Verify the public IP exists if `createPublicIps=true`
3. Check NSG rules and `allowedSourceIpPrefix`
4. Reset credentials if authentication fails

### Container App not starting

1. Check `az containerapp logs show`
2. Verify the image exists in ACR or the referenced registry
3. Check environment variables and app settings
4. Confirm the Container Apps subnet and environment are healthy

### Frontend not loading

1. Check App Service logs
2. Verify the frontend build completed successfully
3. Verify frontend app settings point to the deployed backend URLs
4. Confirm the App Service is running and responding on port `8080`

## Local development

Use the restored local helper for demo or development runs:

```bash
cd ../scripts
./start-local-stack.sh
```

This is local-only and does not replace the Azure deployment workflows.
