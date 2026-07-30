# Operations And Cost

## Operational Best Practices

- Use VNet Flow Logs as the strategic default; avoid duplication with NSG Flow Logs on the same workloads. Source: https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-overview#virtual-network-flow-logs-compared-to-network-security-group-flow-logs
- Use a dedicated Storage Account for flow logs, Standard tier, same region as the VNet. Source: https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-overview#considerations-for-virtual-network-flow-logs
- Do not manually modify blobs while they are being written. Source: https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-manage#create-a-flow-log
- Do not manually modify DCR/DCE with the `NWTA` prefix, as they are managed by Traffic Analytics. Source: https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-manage#enable-or-disable-traffic-analytics
- Use 10 minutes for demos or urgent troubleshooting; use 60 minutes for steady state when higher latency is acceptable.
- Maintain baseline routes managed by Terraform. Demo scripts should only add temporary faults and then remove them with `restore-*`.
- Use Azure Bastion as the sole administrative access path to private VMs; do not add public IPs to VMs.
- Treat `admin_password` as an operational secret: pass it via `TF_VAR_admin_password` or a pipeline secret, not in documentation or outputs.

## Pre-Demo Operations

Before a customer session:

```bash
Student/Resources/scenarios/scripts/validate-demo.sh
Student/Resources/scenarios/scripts/restore-nsg-block.sh
Student/Resources/scenarios/scripts/restore-udr-asymmetry.sh
Student/Resources/scenarios/scripts/generate-baseline-traffic.sh
```

Then wait at least one Traffic Analytics cycle and validate:

```bash
Student/Resources/scenarios/scripts/run-kql.sh top-talkers
Student/Resources/scenarios/scripts/run-kql.sh flow-types
```

If the queries return empty results, check the raw blobs in the Storage Account first. This distinguishes a raw collection issue from a Traffic Analytics delay/error.

## Security Operations

- Treat flow logs as operational evidence: they contain IPs, ports, protocols, directions, and volumes.
- Use Microsoft Entra ID for Blob access when Shared Key is disabled. Source: https://learn.microsoft.com/en-us/azure/storage/blobs/authorize-access-azure-active-directory
- Keep deploy permissions, raw Storage read, and Log Analytics read separate. Source: https://learn.microsoft.com/en-us/azure/network-watcher/required-rbac-permissions
- Avoid manual modifications to `NWTA` DCR/DCE managed by Traffic Analytics. Source: https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-manage#enable-or-disable-traffic-analytics
- Microsoft recommends SSH keys over passwords for Linux. The lab uses password-only due to demo requirements; mandatory mitigations: VMs without public IP, access via Bastion, strong password, and protected Terraform state. Source: https://learn.microsoft.com/en-us/azure/virtual-machines/linux/create-ssh-keys-detailed
- Terraform stores sensitive values such as passwords in the state. Restrict access to the state and do not commit `terraform.tfvars` or state files.
- Boot Diagnostics exposes serial logs and screenshots useful for startup troubleshooting; use it before attributing an issue to routing or flow logs. Source: https://learn.microsoft.com/en-us/azure/virtual-machines/boot-diagnostics

## Costs

Cost-generating components:

- Linux VM.
- Standard Load Balancer.
- Storage Account for raw flow logs.
- Log Analytics ingestion and retention.
- Traffic Analytics processing.
- Azure Firewall Basic, Standard public IP, and traffic processed by the firewall.
- Azure Bastion Basic and its associated static Standard public IP.
- Private Endpoint if enabled.
- Sample Food Ordering App if enabled: Azure Container Apps, Container Apps Environment, Azure Container Registry, Application Insights, log ingestion and alerts.

Microsoft states that VNet Flow Logs are charged per GB collected, Traffic Analytics has separate pricing per GB processed, and storage is billed separately. Source: https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-overview#pricing

Azure Firewall Basic adds a separate fixed/variable cost. For short demos and non-production environments, Basic is the most cost-effective option compatible with the centralized routing and outbound SNAT requirement. Source for feature SKU: https://learn.microsoft.com/en-us/azure/firewall/features-by-sku#azure-firewall-basic-features

Azure Bastion incurs hourly costs from the moment of deployment, regardless of usage. For this demo, `Basic` is the simplest default; use `Standard` only when native client or tunneling is required. Source: https://learn.microsoft.com/en-us/azure/bastion/bastion-overview#pricing-and-sla

## Cleanup

Always run:

```bash
Student/Resources/scenarios/scripts/destroy.sh
```

Verify that no resources created outside Terraform by the demo scripts remain, particularly temporary NSG rules or routes. The `restore-*` scripts remove them before destroy.

## Sample Food Ordering App Operations

The sample app is optional and should be treated as a separate application layer from the network lab:

- `Student/Resources/scenarios/scripts/deploy-sample-food-images.sh` uses ACR cloud build and updates the Container Apps.
- `Student/Resources/scenarios/scripts/validate-sample-food-app.sh` verifies status, endpoints, and log presence.
- `Student/Resources/scenarios/scripts/break-sample-food-app.sh` generates a controlled fault on the cart endpoint.
- `Student/Resources/scenarios/scripts/generate-sample-food-app-traffic.sh` generates non-destructive HTTP traffic.

Cost guardrails:

1. Keep `enable_sample_food_app_lab = false` when not needed.
2. Use Log Analytics retention consistent with the demo duration.
3. Enable `enable_alerts` only if you need to show a response plan.
4. Do not enable `enable_sample_food_vnet_flow_logs` expecting Container Apps workload visibility: the service is not supported by VNet Flow Logs.

Source for Container Apps logs: https://learn.microsoft.com/en-us/azure/container-apps/log-monitoring
