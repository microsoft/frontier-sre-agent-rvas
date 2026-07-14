# Quick Reference Guide

## Azure Resources Created

### Resource Groups (5 total)
- `rg-parking-hub-{env}` - Networking and monitoring
- `rg-parking-frontend-{env}` - React frontend
- `rg-parking-lisbon-{env}` - Lisbon API (Container)
- `rg-parking-madrid-{env}` - Madrid API (Windows VM)
- `rg-parking-paris-{env}` - Paris API (Ubuntu VM)

## Cost Breakdown (Monthly Estimates)

| Resource | SKU/Size | Estimated Cost |
|----------|----------|----------------|
| App Service Plan | Basic B1 (Linux) | $13 |
| Windows Server VM | Standard_B2s | $30 |
| Ubuntu VM | Standard_B2s | $30 |
| Container App | Consumption (0.25 vCPU, 0.5Gi) | $5-10 |
| Log Analytics Workspace | Pay-as-you-go | $5-10 |
| Application Insights (3x) | Pay-as-you-go | $5-10 |
| VNet | Free | $0 |
| Storage (VM disks) | StandardSSD_LRS | $5-10 |
| Public IPs (2x) | Standard | $5-10 |
| **Total** | | **$120-150** |

## Network Configuration

### VNet Address Space
- **Hub VNet**: `10.0.0.0/16`
  - VM Subnet: `10.0.1.0/24` (254 usable IPs)
  - Container Apps Subnet: `10.0.2.0/23` (510 usable IPs)

### NSG Rules (VM Subnet)
- HTTP (80)
- HTTPS (443)
- API Port 3002 (Madrid)
- API Port 3003 (Paris)
- SSH (22)
- RDP (3389)

## Common Commands

### Deployment
```bash
# Interactive deployment
cd infrastructure
./deploy.sh

# Direct deployment
az deployment sub create \
  --location westeurope \
  --template-file main.bicep \
  --parameters main.parameters.example.json \
  --parameters adminPassword='SecurePassword123!'
```

### Check Deployment Status
```bash
# List all deployments
az deployment sub list --output table

# Show specific deployment
az deployment sub show --name <deployment-name>

# Get outputs
az deployment sub show --name <deployment-name> --query properties.outputs
```

### Access VMs
```bash
# SSH to Paris VM (Linux)
ssh azureadmin@<paris-vm-fqdn>

# RDP to Madrid VM (Windows)
mstsc /v:<madrid-vm-fqdn>

# Reset VM password
az vm user update \
  --resource-group rg-parking-madrid-dev \
  --name vm-madrid-api \
  --username azureadmin \
  --password 'NewPassword123!'
```

### Container App Management
```bash
# Update container image
az containerapp update \
  --name ca-parking-lisbon \
  --resource-group rg-parking-lisbon-dev \
  --image <your-registry>.azurecr.io/lisbon-parking-api:latest

# View logs
az containerapp logs show \
  --name ca-parking-lisbon \
  --resource-group rg-parking-lisbon-dev \
  --follow

# Scale container app
az containerapp update \
  --name ca-parking-lisbon \
  --resource-group rg-parking-lisbon-dev \
  --min-replicas 1 \
  --max-replicas 5
```

### App Service Management
```bash
# Deploy frontend
cd frontend/parking-manager
npm run build
az webapp up \
  --name <app-service-name> \
  --resource-group rg-parking-frontend-dev

# View logs
az webapp log tail \
  --name <app-service-name> \
  --resource-group rg-parking-frontend-dev

# Configure app settings
az webapp config appsettings set \
  --name <app-service-name> \
  --resource-group rg-parking-frontend-dev \
  --settings REACT_APP_LISBON_API_URL=https://...
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

### Cleanup
```bash
# Delete all resources (by resource groups)
az group delete --name rg-parking-hub-dev --yes --no-wait
az group delete --name rg-parking-frontend-dev --yes --no-wait
az group delete --name rg-parking-lisbon-dev --yes --no-wait
az group delete --name rg-parking-madrid-dev --yes --no-wait
az group delete --name rg-parking-paris-dev --yes --no-wait

# Or delete the entire deployment
az deployment sub delete --name <deployment-name>
```

## Post-Deployment Checklist

### 1. Deploy Applications
- [ ] Build and push Lisbon API container image
- [ ] Deploy Madrid API to Windows VM
- [ ] Deploy Paris API to Ubuntu VM
- [ ] Build and deploy React frontend

### 2. Configure Networking
- [ ] Review NSG rules and adjust if needed
- [ ] Configure custom domains (optional)
- [ ] Set up SSL certificates
- [ ] Configure CORS settings

### 3. Set Up Monitoring
- [ ] Create Application Insights availability tests
- [ ] Configure Log Analytics queries and alerts
- [ ] Set up Azure Monitor alerts for VM health
- [ ] Create dashboards for monitoring

### 4. Security Hardening
- [ ] Rotate VM passwords regularly
- [ ] Enable Azure AD authentication for App Service
- [ ] Configure Key Vault for secrets
- [ ] Review and restrict NSG rules
- [ ] Enable Azure Defender for Cloud

### 5. Cost Optimization
- [ ] Set up budgets and cost alerts
- [ ] Review and adjust VM auto-shutdown schedules
- [ ] Optimize Log Analytics retention
- [ ] Review unused resources monthly

## Troubleshooting

### Deployment Fails
1. Check deployment errors: `az deployment sub show --name <name> --query properties.error`
2. Verify subscription permissions (Contributor role required)
3. Check resource name uniqueness
4. Ensure quota limits are not exceeded

### Cannot Connect to VMs
1. Verify NSG rules allow the traffic
2. Check VM is running: `az vm get-instance-view`
3. Verify public IP is attached (if using)
4. Reset VM password if authentication fails

### Container App Not Starting
1. Check container logs: `az containerapp logs show`
2. Verify container image is accessible
3. Check environment variables are set correctly
4. Ensure Container App Environment is healthy

### Frontend Not Loading
1. Check App Service logs: `az webapp log tail`
2. Verify build was successful
3. Check app settings (API URLs)
4. Ensure App Service Plan is running

## Support and Resources

- [Azure Bicep Documentation](https://learn.microsoft.com/azure/azure-resource-manager/bicep/)
- [Azure App Service Documentation](https://learn.microsoft.com/azure/app-service/)
- [Azure Container Apps Documentation](https://learn.microsoft.com/azure/container-apps/)
- [Azure Virtual Machines Documentation](https://learn.microsoft.com/azure/virtual-machines/)
- [Azure Monitor Documentation](https://learn.microsoft.com/azure/azure-monitor/)
