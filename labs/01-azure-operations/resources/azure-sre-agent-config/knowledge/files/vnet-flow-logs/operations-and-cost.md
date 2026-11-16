# Operations And Cost

## Operational best practices

- Use Virtual Network flow logs as the strategic default; avoid duplicating them with Network Security Group flow logs on the same workloads. Source: https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-overview#virtual-network-flow-logs-compared-to-network-security-group-flow-logs
- Use a dedicated Standard storage account for flow logs, in the same region as the virtual network. Source: https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-overview#considerations-for-virtual-network-flow-logs
- Never modify the blobs manually while they are being written. Source: https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-manage#create-a-flow-log
- Never modify data collection rules or data collection endpoints whose name starts with `NWTA` by hand: they are owned by Traffic Analytics. Source: https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-manage#enable-or-disable-traffic-analytics
- Use a ten-minute processing interval for demonstrations and urgent troubleshooting; use sixty minutes for steady state, where higher latency is acceptable.
- The baseline routes are owned by Terraform. Any route or Network Security Group rule that does not match the declared baseline must be treated as drift to investigate, not as expected configuration.
- Use Azure Bastion as the only administrative path to the private virtual machines, and never attach a public IP address to a virtual machine.
- Treat `admin_password` as an operational secret: pass it through `TF_VAR_admin_password` or a pipeline secret, never in documentation or in an output.

## Security operations

- Treat flow logs as operational evidence: they contain IP addresses, ports, protocols, directions and volumes.
- Use Microsoft Entra ID for blob access when shared key authorisation is disabled. Source: https://learn.microsoft.com/en-us/azure/storage/blobs/authorize-access-azure-active-directory
- Keep three permissions separate: deployment, raw storage read, and Log Analytics read. Source: https://learn.microsoft.com/en-us/azure/network-watcher/required-rbac-permissions
- Avoid manual changes to the `NWTA` data collection rules and endpoints owned by Traffic Analytics. Source: https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-manage#enable-or-disable-traffic-analytics
- Microsoft recommends Secure Shell keys instead of passwords for Linux. This laboratory uses password authentication only, as a demonstration requirement. The mandatory mitigations are: no public IP address on any virtual machine, administrative access through Azure Bastion, a strong password, and a protected Terraform state. Source: https://learn.microsoft.com/en-us/azure/virtual-machines/linux/create-ssh-keys-detailed
- Terraform stores sensitive values, including the password, inside its state. Restrict access to the state and never commit `terraform.tfvars` or any state file.
- Boot diagnostics exposes the serial log and a screenshot, both useful when troubleshooting a failed start. Check them before attributing a problem to routing or to flow logs. Source: https://learn.microsoft.com/en-us/azure/virtual-machines/boot-diagnostics

## Cost

The components that generate cost are:

- The Linux virtual machines.
- The Standard load balancer.
- The storage account holding the raw flow logs.
- Log Analytics ingestion and retention.
- Traffic Analytics processing.
- Azure Firewall Basic, its Standard public IP address, and the traffic it processes.
- Azure Bastion Basic and its static Standard public IP address.
- The private endpoint, when enabled.
- The Grubify sample food ordering application, when enabled: Azure Container Apps, the Container Apps environment, Application Insights, log ingestion and alerts. The container images are hosted on GitHub Packages, which adds no Azure cost.

Microsoft states that virtual network flow logs are charged per gigabyte collected, that Traffic Analytics has separate pricing per gigabyte processed, and that storage is charged separately. Source: https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-overview#pricing

Azure Firewall Basic adds a separate fixed and variable cost. For short demonstrations and non-production environments, Basic is the cheapest option compatible with the requirement of centralised routing and outbound source network address translation. Source for the feature comparison by product tier: https://learn.microsoft.com/en-us/azure/firewall/features-by-sku#azure-firewall-basic-features

Azure Bastion is charged per hour from the moment it is deployed, whether it is used or not. For this demonstration the Basic tier is the simplest default; choose Standard only when the native client or tunnelling is required. Source: https://learn.microsoft.com/en-us/azure/bastion/bastion-overview#pricing-and-sla

## Cost profile of the sample food ordering application

The sample application is optional and must be treated as an application layer separate from the network laboratory.

Cost guardrails:

1. Deleting the laboratory when it is not in use stops the always-on cost of every resource.
2. Set Log Analytics retention to match the duration of the demonstration.
3. Enable `enable_alerts` only when an incident response plan has to be shown.
4. Do not enable `enable_sample_food_vnet_flow_logs` expecting visibility over Container Apps workload traffic: that service is not supported by virtual network flow logs.

Source for Container Apps logging: https://learn.microsoft.com/en-us/azure/container-apps/log-monitoring
