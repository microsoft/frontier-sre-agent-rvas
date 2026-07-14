# Deployment Guide

For a complete guide on activation order, Terraform resources, parameters, RBAC, networking requirements, and operational usage, see [vnet-flow-logs-traffic-analytics-terraform-guide.md](vnet-flow-logs-traffic-analytics-terraform-guide.md).

## Prerequisites

- Authenticated Azure CLI: `az login`.
- Terraform >= 1.7.
- Azure permissions to create network, compute, Azure Firewall, route tables, storage, Log Analytics, Network Watcher Flow Logs, and, if enabled, Workbooks/alerts.
- `Microsoft.Insights` registered: required to log VNet traffic. Source: https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-manage#register-insights-provider
- For the Sample Food Ordering App extension: `Microsoft.App`, `Microsoft.ContainerRegistry`, `Microsoft.Insights`, `Microsoft.OperationalInsights`, and `Microsoft.Network` registered.
- Local admin password for Linux VMs, passed as a Terraform secret. Do not commit passwords in versioned files; use `TF_VAR_admin_password` or a local `terraform.tfvars` ignored by git.

Traffic Analytics requires additional permissions on Log Analytics, DCR/DCE, and network resources. Network Contributor alone does not include all the necessary Storage, OperationalInsights, and Insights actions. Source: https://learn.microsoft.com/en-us/azure/network-watcher/required-rbac-permissions#traffic-analytics

## Deploy

```bash
cd terraform
cp terraform.tfvars.example terraform.tfvars
export TF_VAR_admin_password='Use-A-Strong-Demo-Password-123!'
terraform init
terraform validate
terraform plan
terraform apply
```

VMs are created without public IPs and without SSH keys. Administrative access is through the Azure Portal via Azure Bastion with username/password. Microsoft recommends SSH keys over passwords for Linux; in this lab the password-only choice is compensated by Bastion and the absence of SSH exposed to the Internet. Source: https://learn.microsoft.com/en-us/azure/virtual-machines/linux/create-ssh-keys-detailed

Switching from a previous deployment with SSH keys to password auth recreates the VMs, because authentication arguments for the Terraform Linux VM resource are destructive changes. Always review the `terraform plan` before applying.

Or:

```bash
./scripts/deploy.sh
```

## Optional Sample Food Ordering App Deployment

The Sample Food Ordering App is disabled by default to avoid modifying the behavior of the base lab.

```bash
cd terraform
terraform plan -var enable_sample_food_app_lab=true
terraform apply -var enable_sample_food_app_lab=true
cd ..
./scripts/deploy-sample-food-images.sh
./scripts/validate-sample-food-app.sh
```

Useful outputs:

```bash
cd terraform
terraform output sample_food_api_url
terraform output sample_food_frontend_url
terraform output sample_food_resource_names
```

To regenerate application traffic:

```bash
./scripts/generate-sample-food-app-traffic.sh
```

For controlled fault injection:

```bash
./scripts/break-sample-food-app.sh
```

Note: use Container Apps logs and Application Insights for sample app incidents. Azure Container Apps is not supported by VNet Flow Logs. Source: https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-overview#incompatible-services

## Post-Deploy Validation

Before running the customer demo, validate infrastructure state and observability:

```bash
./scripts/validate-demo.sh
./scripts/generate-baseline-traffic.sh
./scripts/run-kql.sh top-talkers
```

If `top-talkers` returns no data, wait for the Traffic Analytics cycle and verify the raw blobs in the Storage Account. For the complete demo outline, use [demo-runbook.md](demo-runbook.md); for queries and diagnostics, use [kql-catalog.md](kql-catalog.md) and [troubleshooting-scenarios.md](troubleshooting-scenarios.md).

`validate-demo.sh` also checks that Azure Bastion exists, that VMs have no public IP, and that Boot Diagnostics is enabled.

## Existing vs. Created Network Watcher

By default `create_network_watcher = false`, so Terraform looks for `NetworkWatcher_<region>` in `NetworkWatcherRG`. This reflects common Azure behavior: Network Watcher is automatically enabled when VNets are created or updated in a region.

If the tenant has disabled automatic enablement, set:

```hcl
create_network_watcher = true
```

Source: https://learn.microsoft.com/en-us/azure/network-watcher/network-watcher-create

## Cleanup

```bash
cd terraform
terraform destroy
```

Or:

```bash
./scripts/destroy.sh
```

## Cost control

- Keep `flow_log_retention_days = 7` for short demos.
- Shut down or destroy the lab after the demo.
- Keep `azure_firewall_sku_tier = "Basic"` for standard demos; switch to Standard only if DNS proxy, higher throughput, or threat intelligence deny is required.
- Keep `bastion_sku = "Basic"` for browser/portal access; switch to Standard only if native client, tunneling, file copy, IP-based connection, or custom ports are required.
- Enable `enable_private_endpoint_demo` only if you need to demonstrate Private Link.
- Enable `enable_alerts` only if you want to demonstrate operationalization with Azure Monitor Alerts.
- Enable `enable_sample_food_app_lab` only when the SRE Agent application demo is needed; it adds Container Apps, ACR, and App Insights.

Source for VNet Flow Logs and Traffic Analytics pricing: https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-overview#pricing
