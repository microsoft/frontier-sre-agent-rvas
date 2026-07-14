# Demo Runbook

## 0. Pre-check before the demo

Run checks before entering the portal with the customer. The goal is to arrive at the demo with the environment, routing, flow logs, and queries already verified.

```bash
./scripts/validate-demo.sh
```

Checks to confirm:

- Resource group, Storage Account, and Log Analytics Workspace exist.
- The three VNets have VNet Flow Logs enabled.
- Traffic Analytics is configured with a demo interval of 10 minutes.
- Azure Firewall Basic has a private IP consistent with the Terraform output `azure_firewall_private_ip`.
- Azure Bastion is present in the hub and VMs have no public IP.
- Boot Diagnostics is enabled on the Linux VMs.
- The `restore-nsg-block.sh` and `restore-udr-asymmetry.sh` scripts have been run if a previous demo left temporary faults.

Internal note: if this step fails, do not improvise in the portal. Fix the lab state first, then start the demo.

## 1. Open with the business problem

Message: "The network configuration says what should happen; flow logs say what is actually happening. Traffic Analytics transforms raw flow logs into operational signals to understand traffic, security, misconfigurations, and root cause."

Source: https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics

## 2. Show the Terraform deployment

For the full details of resources, parameters, prerequisites, RBAC, and activation order, use [vnet-flow-logs-traffic-analytics-terraform-guide.md](vnet-flow-logs-traffic-analytics-terraform-guide.md) as the reference guide.

Open [../terraform/monitoring.tf](../terraform/monitoring.tf) and show:

- Storage Account dedicated to raw flow logs.
- Log Analytics Workspace.
- `azurerm_network_watcher_flow_log` on each VNet.
- `traffic_analytics.interval_in_minutes = var.traffic_analytics_interval_minutes`.

Explain that the lab uses 10 minutes for demo responsiveness; the documented default is 60 minutes. Source: https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-manage#create-a-flow-log

Then open [../terraform/network.tf](../terraform/network.tf) and show the network baseline:

- Azure Firewall Basic in the hub, `AzureFirewallSubnet` subnet and firewall policy.
- Terraform-managed route tables on the app/data spokes.
- Routes: app -> data, data -> app, and `0.0.0.0/0` toward the firewall private IP.
- Wildcard firewall network rule `allow-all` to permit all flows routed to the firewall; the HTTPS application rule toward Microsoft remains in the lab as a demo reference, but traffic is already permitted by the permissive network rule.
- Azure Bastion in the hub, `AzureBastionSubnet` subnet, static Standard public IP.

Azure Firewall Basic is sufficient for this demo because it includes stateful filtering, SNAT outbound, network rules, and application FQDN filtering. In this configuration the policy is intentionally permissive: the firewall is the centralized transit point, while NSG and UDR demonstrate the controls and faults. Source: https://learn.microsoft.com/en-us/azure/firewall/features-by-sku#azure-firewall-basic-features

Open [../terraform/compute.tf](../terraform/compute.tf) and show the VM access model:

- `admin_password = var.admin_password`.
- `disable_password_authentication = false`.
- no `admin_ssh_key` block.
- `boot_diagnostics {}` on each VM.

Customer message: "The VMs remain private and manageable. We do not expose SSH to the internet: access is via Bastion, while Boot Diagnostics helps us understand startup issues even when the VM is not responding."

Source Bastion: https://learn.microsoft.com/en-us/azure/bastion/bastion-overview
Source Boot Diagnostics: https://learn.microsoft.com/en-us/azure/virtual-machines/boot-diagnostics

## 2.1 Operational Access via Bastion

In the Azure portal:

1. Open a demo Linux VM, for example client.
2. Select Connect.
3. Select Bastion.
4. Use username `azureuser` or the value of `admin_username`.
5. Enter the password passed to Terraform with `TF_VAR_admin_password`.

The Basic SKU supports browser-based connection from the portal with username/password on port 22. If CLI access is needed with `az network bastion ssh --auth-type password`, use Bastion Standard. Source: https://learn.microsoft.com/en-us/azure/bastion/bastion-connect-vm-ssh-linux

## 2.2 Boot Diagnostics Verification

In the Azure portal:

1. Open a demo Linux VM.
2. Go to Help > Boot diagnostics.
3. Check the screenshot and serial log.

This section is useful if cloud-init, routing, or application services seem not to start: it separates a boot problem from a network/application problem.

## 3. Validate the baseline centralized routing

Before the faults, show that the environment already works with centralized hub routing.

In the Azure portal:

1. Open Network Watcher.
2. Open Next Hop.
3. Source: client VM `10.20.1.10`.
4. Destination: DB `10.30.2.10`.
5. Verify `Next hop type = VirtualAppliance` and next hop IP equal to the Terraform output `azure_firewall_private_ip`.

Next Hop returns the next hop type, IP, and route table when applicable. Source: https://learn.microsoft.com/en-us/azure/network-watcher/next-hop-overview

Customer message: "We are not activating central routing as a fault. Central routing is the healthy baseline; the fault will be introduced later, with an incorrect more-specific route."

Optional CLI validation, useful if you want to avoid lengthy portal clicks:

```bash
cd terraform
terraform output azure_firewall_private_ip
```

Then show the Effective routes on the data spoke VM NIC and verify that the route `10.20.0.0/16` points to the firewall. This prepares the storytelling for the UDR scenario: a more-specific route overrides the less-specific route.

## 4. Generate baseline traffic

```bash
./scripts/generate-baseline-traffic.sh
```

Wait for at least one Traffic Analytics cycle. Raw flow logs are collected at one-minute intervals, while Traffic Analytics processes every 10 or 60 minutes and may require additional ingestion time. Source: https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-schema#data-aggregation

If you want immediate evidence before Traffic Analytics completes its cycle, show the Storage Account and the `insights-logs-flowlogflowevent` container. This clearly separates the two planes:

- raw evidence: arrives in Storage;
- operational analytics: arrives in Log Analytics after processing.

## 5. Show the Traffic Analytics dashboard

In the Azure portal:

1. Open Network Watcher.
2. Open Traffic Analytics.
3. Show hotspots, top talkers, top protocols, VNet topology, and NSG rule hits.

Operational value: see who is talking to whom, on which ports, with what volume, and whether traffic is allowed or denied. Source: https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-usage-scenarios

Recommended demo path:

1. Start from top talkers/hotspots: makes the generated traffic visible.
2. Move to VNet/subnet topology: links technical evidence and hub-spoke architecture.
3. Show NSG rule hits: prepares the deny scenario.
4. Show public IP information: explains how to use Traffic Analytics for egress review.
5. Close with custom workbook: shows how to bring the value into a repeatable NOC/SOC view.

## 6. Show raw logs vs enriched logs

Raw logs:

1. Open the Storage Account.
2. Container `insights-logs-flowlogflowevent`.
3. Download a `PT1H.json` file.

Source: https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-manage#download-a-flow-log

Enriched logs:

```kql
NTANetAnalytics
| where SubType == "FlowLog"
| take 10
```

Source schema: https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-schema

Customer message: "Storage preserves the raw data; Traffic Analytics makes it navigable. They are not alternatives: for a mature operational model, both are used together."

If the query returns no data:

```bash
./scripts/run-kql.sh top-talkers
```

Then verify:

- query time window;
- baseline traffic generated;
- flow log enabled;
- Traffic Analytics enabled;
- presence of raw blobs;
- wait for the processing cycle.

## 7. NSG block scenario

```bash
./scripts/trigger-nsg-block.sh
```

Show denied query:

```bash
./scripts/run-kql.sh denied
```

Then open Network Watcher > IP Flow Verify and verify client -> DB on TCP 5432. IP Flow Verify returns allowed/denied and the responsible rule. Source: https://learn.microsoft.com/en-us/azure/network-watcher/ip-flow-verify-overview

Restore:

```bash
./scripts/restore-nsg-block.sh
```

Customer message: "Here Traffic Analytics does not replace IP Flow Verify. It makes it prioritizable: I can see which denies actually matter, then use Network Watcher to confirm the exact rule."

## 8. Asymmetric UDR scenario on centralized routing

```bash
./scripts/trigger-udr-asymmetry.sh
```

The fault adds a temporary more-specific route on the data spoke: `10.20.1.0/24 -> None`. The baseline client -> DB continues to point to the central firewall, but the return path toward the client is broken by the more-specific route.

Show:

- Network Watcher > Next Hop from the client toward DB: should remain `VirtualAppliance` toward Azure Firewall.
- Effective routes on the data spoke: the temporary route `10.20.1.0/24 -> None` overrides the Terraform-managed route `10.20.0.0/16 -> firewall`.
- Traffic Analytics/KQL: unbalanced bytes, incomplete flows, or absence of the expected return.

This is the most instructive part: the central configuration is correct, but a more-specific route breaks only one direction. Source UDR: https://learn.microsoft.com/en-us/azure/virtual-network/virtual-networks-udr-overview#user-defined-routes

Restore:

```bash
./scripts/restore-udr-asymmetry.sh
```

After the restore, repeat Next Hop or Effective Routes to demonstrate that the fault was temporary and that the Terraform-managed baseline is clean again.

Customer message: "This is the Principal Architect value: we are not just saying traffic is not passing; we demonstrate which routing decision prevails and where the return path breaks."

## 9. Private Endpoint scenario

If Private Endpoint is enabled in the demo, show that visibility must be interpreted correctly:

- traffic toward the Private Endpoint is observed from the source VM side;
- you should not expect the flow log captured on the Private Endpoint itself;
- validation must be correlated with private DNS, the Private Endpoint's private IP, and `PrivateEndpointResourceId` when populated.

Recommended query: use the Private Endpoint section in [kql-catalog.md](kql-catalog.md).

Source: https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-overview#private-endpoint-traffic

## 10. Close with operationalization

Show the Workbook created by Terraform and the optional alerts.

Explain the operational model:

- Traffic Analytics dashboard for exploration.
- KQL for root cause analysis.
- Workbook for shared dashboards.
- Alerts for proactive notification.
- Azure Policy for enterprise audit/remediation, outside the base path but useful for scale.

Fonti: https://learn.microsoft.com/en-us/azure/azure-monitor/visualize/workbooks-overview, https://learn.microsoft.com/en-us/azure/azure-monitor/alerts/alerts-create-log-alert-rule

Recommended executive closing:

| Message | Why it matters |
| --- | --- |
| VNet Flow Logs shows what is actually happening on IP traffic. | Reduces diagnosis based on assumptions. |
| Traffic Analytics transforms raw logs into navigable insights. | Reduces time-to-triage for network/security operations. |
| Centralized routing is the baseline, not a fault. | Aligns the demo to a real enterprise design. |
| NSG and UDR faults are temporary and restorable. | Demonstrates operational control and demo safety. |
| Raw logs and Traffic Analytics are complementary. | Forensics + dashboard/analytics. |
