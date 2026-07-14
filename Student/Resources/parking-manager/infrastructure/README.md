# Azure Infrastructure for SRE Demo Manager

This directory contains the Bicep templates to deploy the complete Azure infrastructure for the Parking Manager application.

## Architecture Overview

The infrastructure is organized into multiple resource groups for better management and cost tracking:

### Resource Groups

1. **Hub Resource Group** (`rg-parking-hub-{env}`)
   - Virtual Network (VNet) with subnets
   - Log Analytics Workspace (shared across all components)
   - Azure Container Registry (ACR)
   - Network Security Groups

2. **Frontend Resource Group** (`rg-parking-frontend-{env}`)
   - Azure App Service Plan (Linux, B1 tier)
   - Azure App Service (React + Express proxy, port 8080)
   - Application Insights

3. **Lisbon API Resource Group** (`rg-parking-lisbon-{env}`)
   - Container App Environment
   - Container App (Docker-based API, port 3001)
   - Application Insights

4. **Berlin API Resource Group** (`rg-parking-berlin-{env}`)
   - Container App Environment
   - Container App (Docker-based API, port 3004)
   - Application Insights

5. **Madrid API Resource Group** (`rg-parking-madrid-{env}`)
   - Windows Server 2022 VM (Standard_B2s)
   - Network Interface
   - Public IP (optional)
   - Application Insights

6. **Paris API Resource Group** (`rg-parking-paris-{env}`)
   - Ubuntu Server 22.04 LTS VM (Standard_B2s)
   - Network Interface
   - Public IP (optional)
   - Application Insights

7. **Chaos Control Resource Group** (`rg-parking-chaos-{env}`)
   - Container App Environment
   - Container App for Chaos Control service (port 3090)
   - Application Insights

8. **Berlin MCP Server Resource Group** (`rg-parking-berlin-mcp-{env}`) *(optional)*
   - Container App for the Berlin MCP Server
   - Application Insights
   - Enable by setting `deployBerlinMcp=true` in your parameters file.

> **Note**: The `vm-health-control` service is an application-layer service only (not provisioned by Bicep). It runs locally via `start-chaos-stack.sh` or can be deployed to an existing Container App environment.

## Cost Optimization Strategy

The infrastructure is designed for cost optimization:

- **App Service Plan**: B1 tier (Basic) — approximately $13/month
- **Virtual Machines**: Standard_B2s (2 vCPUs, 4 GB RAM) — approximately $30/month each
- **Container Apps**: Consumption-based pricing with 0.25 vCPU and 0.5 Gi memory
- **Storage**: StandardSSD_LRS for VM disks
- **Log Analytics**: Pay-as-you-go with 30-day retention
- **Network**: Standard public IPs (optional, can be disabled)

**Estimated Monthly Cost**: ~$120–180 (varies by region, usage, and optional components)

## Prerequisites

1. **Azure CLI** version 2.50.0 or later
2. **Azure Subscription** with Contributor access
3. **Bicep CLI** (automatically installed with Azure CLI 2.20.0+)

To verify your setup:
```bash
az --version
az bicep version
```

## Parameters

### Required Parameters

| Parameter | Description | Example |
|-----------|-------------|---------|
| `location` | Azure region for resources | `westeurope` |
| `environment` | Environment name (dev/test/prod) | `dev` |
| `adminUsername` | Admin username for VMs | `azureadmin` |
| `adminPassword` | Admin password for VMs (secure) | `P@ssw0rd123!` |

### Optional Parameters

| Parameter | Description | Default |
|-----------|-------------|---------|
| `lisbonContainerImage` | Container image for Lisbon API | `mcr.microsoft.com/azuredocs/containerapps-helloworld:latest` |
| `containerRegistry` | Private container registry URL | `""` (empty) |
| `createPublicIps` | Create public IPs for VMs | `true` |
| `vnetAddressPrefix` | VNet address space | `10.0.0.0/16` |
| `vmSubnetPrefix` | VM subnet address space | `10.0.1.0/24` |
| `containerSubnetPrefix` | Container Apps subnet address space | `10.0.2.0/23` |

## Deployment

### Step 1: Login to Azure

```bash
az login
az account set --subscription "<your-subscription-id>"
```

### Step 2: Validate the Bicep Template

```bash
cd infrastructure
az deployment sub validate \
  --location westeurope \
  --template-file main.bicep \
  --parameters main.parameters.json \
  --parameters adminPassword='<your-secure-password>'
```

### Step 3: Deploy the Infrastructure

#### Quick Deploy (with inline parameters)

```bash
az deployment sub create \
  --location westeurope \
  --template-file main.bicep \
  --parameters environment=dev \
  --parameters adminUsername=azureadmin \
  --parameters adminPassword='<your-secure-password>' \
  --parameters location=westeurope
```

#### Deploy with Parameters File

1. Create a copy of the parameters file:
   ```bash
   cp main.parameters.json main.parameters.local.json
   ```

2. Edit `main.parameters.local.json` and update the values:
   - Replace `{subscription-id}`, `{rg-name}`, `{vault-name}` if using Key Vault
   - Or provide the password directly (not recommended for production)

3. Deploy:
   ```bash
   az deployment sub create \
     --location westeurope \
     --template-file main.bicep \
     --parameters main.parameters.local.json \
     --parameters adminPassword='<your-secure-password>'
   ```

### Step 4: Monitor Deployment

```bash
# List all deployments
az deployment sub list --output table

# Show deployment details
az deployment sub show --name main-deployment
```

## Post-Deployment Steps

### 1. Configure Container Image for Lisbon API

If you're using a custom container image:

```bash
# Build and push your Lisbon API image
cd backend/lisbon-parking-api
docker build -t <acr-name>.azurecr.io/lisbon-parking-api:latest .
az acr login --name <acr-name>
docker push <acr-name>.azurecr.io/lisbon-parking-api:latest

# Update the Container App
az containerapp update \
  --name ca-parking-lisbon \
  --resource-group rg-parking-lisbon-<env> \
  --image <acr-name>.azurecr.io/lisbon-parking-api:latest
```

### 2. Deploy Madrid API to Windows VM

SSH/RDP into the Madrid VM and deploy the Node.js application:

```powershell
# RDP into the Windows VM
# Then download and setup the Madrid API

# Create application directory
New-Item -ItemType Directory -Path C:\parking-api

# Clone or copy the application code
# Install dependencies
cd C:\parking-api
npm install

# Install as Windows Service (optional)
npm install -g node-windows
node install-service.js

# Or run manually
npm start
```

### 3. Deploy Paris API to Linux VM

SSH into the Paris VM and deploy the Node.js application:

```bash
# SSH into the Ubuntu VM
ssh azureadmin@<paris-vm-fqdn>

# Create application directory
sudo mkdir -p /opt/parking-api
sudo chown $USER:$USER /opt/parking-api

# Clone or copy the application code
cd /opt/parking-api
npm install

# Create systemd service
sudo nano /etc/systemd/system/paris-parking-api.service
```

Example systemd service file:
```ini
[Unit]
Description=Paris Parking API
After=network.target

[Service]
Type=simple
User=azureadmin
WorkingDirectory=/opt/parking-api
ExecStart=/usr/bin/node server.js
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

Enable and start the service:
```bash
sudo systemctl daemon-reload
sudo systemctl enable paris-parking-api
sudo systemctl start paris-parking-api
```

### 4. Deploy Frontend to App Service

```bash
# Build the frontend
cd frontend/parking-manager
npm install
npm run build

# Deploy using Azure CLI
az webapp up \
  --name <app-service-name> \
  --resource-group rg-parking-frontend-<env> \
  --plan asp-parking-frontend \
  --runtime "NODE:18-lts" \
  --src-path .
```

Or use GitHub Actions / Azure DevOps for CI/CD.

## Accessing the Resources

After deployment, retrieve the outputs:

```bash
az deployment sub show \
  --name main-deployment \
  --query properties.outputs
```

Key outputs:
- **Frontend URL**: `https://<app-service-name>.azurewebsites.net`
- **Lisbon API URL**: `https://<lisbon-container-app-fqdn>.azurecontainerapps.io`
- **Berlin API URL**: `https://<berlin-container-app-fqdn>.azurecontainerapps.io`
- **Madrid API URL**: `http://<madrid-vm-fqdn>:3002`
- **Paris API URL**: `https://<paris-vm-fqdn>:3003`

## Updating the Infrastructure

To update resources:

```bash
# Modify the Bicep files as needed
# Run deployment again (Bicep is idempotent)
az deployment sub create \
  --location westeurope \
  --template-file main.bicep \
  --parameters main.parameters.local.json \
  --parameters adminPassword='<your-secure-password>'
```

## Cleaning Up

To delete all resources:

```bash
# Replace <env> with your environment (e.g., dev, test, prod)
az group delete --name rg-parking-hub-<env>            --yes --no-wait
az group delete --name rg-parking-frontend-<env>       --yes --no-wait
az group delete --name rg-parking-lisbon-<env>         --yes --no-wait
az group delete --name rg-parking-berlin-<env>         --yes --no-wait
az group delete --name rg-parking-madrid-<env>         --yes --no-wait
az group delete --name rg-parking-paris-<env>          --yes --no-wait
az group delete --name rg-parking-chaos-<env>          --yes --no-wait
# Optional Berlin MCP:
az group delete --name rg-parking-berlin-mcp-<env>     --yes --no-wait
```

> ⚠️ **Cost reminder**: Azure resources continue to accrue charges until deleted. Run the cleanup commands above when the demo environment is no longer needed.

## Troubleshooting

### GitHub Runners Subnet Deployment

**Issue**: Deployment fails with `InUseSubnetCannotBeDeleted` for `snet-github-runners` subnet.

**Cause**: The subnet has a service association link from GitHub Actions networking that prevents deletion during VNet state reconciliation.

**Solution**: VNet subnets are created as separate child resources instead of inline definitions to prevent Azure from attempting to delete existing subnets during redeployment. The `snet-github-runners` subnet is managed by the `github-runner-network.bicep` module.

If you encounter this error on an older deployment:
- Pull the latest infrastructure code and redeploy (preferred — prevents future occurrences).
- Or remove the GitHub Network Settings resource first:
  ```bash
  az resource delete \
    --resource-group rg-parking-hub-<env> \
    --name github-actions-network-settings \
    --resource-type GitHub.Network/networkSettings
  ```
  Then redeploy the infrastructure.

### Bicep Compilation Errors

```bash
# Validate Bicep syntax
az bicep build --file main.bicep
```

### Deployment Errors

```bash
# Get deployment error details
az deployment sub show \
  --name main-deployment \
  --query properties.error

# View deployment operations
az deployment operation sub list \
  --name main-deployment
```

### VM Access Issues

```bash
# Reset VM password
az vm user update \
  --resource-group rg-parking-madrid-<env> \
  --name vm-madrid-api \
  --username azureadmin \
  --password '<new-password>'

# Enable boot diagnostics
az vm boot-diagnostics enable \
  --resource-group rg-parking-madrid-<env> \
  --name vm-madrid-api
```

## Security Considerations

> **This is a demo/development project.** The default settings below are intentionally permissive for ease of setup. Review all settings before exposing this environment to the internet.

### Critical Security Settings

1. **SSH/RDP Access**: By default, the NSG allows SSH (port 22) and RDP (port 3389) from any IP address (`*`). **This is for demo purposes only.**

   For restricted access:
   ```bash
   az deployment sub create \
     --location westeurope \
     --template-file main.bicep \
     --parameters allowedSourceIpPrefix='<your-ip>/32'
   ```

   Or use **Azure Bastion** for secure VM access without public IPs:
   ```bash
   --parameters createPublicIps=false
   ```

2. **Self-signed certificates**: Paris and Madrid APIs use self-signed TLS certificates in Azure deployments. The Express proxy server disables certificate verification (`NODE_TLS_REJECT_UNAUTHORIZED=0`) to connect to these services. Do not use self-signed certificates in production.

3. **Container Registry Authentication**: The default configuration uses admin credentials for private registries. For production, use **Managed Identity** authentication and disable the admin user.

### Additional Security Best Practices

4. **Use Key Vault** for storing VM passwords and container registry credentials
5. **Enable Azure AD authentication** for App Service and Container Apps
6. **Configure NSG rules** to restrict inbound access to what is needed
7. **Use Managed Identities** instead of connection strings where possible
8. **Enable HTTPS only** for web applications
9. **Regular patching** of VMs through Azure Update Management
10. **Enable Microsoft Defender for Cloud** for advanced threat protection

## Networking

The infrastructure uses a hub-and-spoke network topology:

- **Hub VNet**: 10.0.0.0/16
  - VM Subnet: 10.0.1.0/24 (254 addresses)
  - Container Apps Subnet: 10.0.2.0/23 (510 addresses)

All resources are connected to the hub VNet for centralized management and monitoring.

## Monitoring

All resources send logs to the centralized Log Analytics Workspace:

```kusto
// Query all API requests
AppRequests
| where TimeGenerated > ago(1h)
| summarize count() by cloud_RoleName, resultCode

// Check VM performance
Perf
| where TimeGenerated > ago(1h)
| where ObjectName == "Processor" and CounterName == "% Processor Time"
| summarize avg(CounterValue) by Computer
```

## Contributing

When modifying the infrastructure:

1. Test changes in a dev environment first
2. Use `az deployment sub what-if` to preview changes
3. Document any new parameters or outputs
4. Update this README with relevant information

## License

ISC
