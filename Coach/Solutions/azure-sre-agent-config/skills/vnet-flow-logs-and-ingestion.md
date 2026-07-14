# vnet-flow-logs-and-ingestion

Use this skill when investigating missing, delayed, duplicated, disabled, mis-scoped, or unexpected Azure Virtual Network Flow Logs for the hub, app, or data VNets in this Terraform project, and when validating that the flow-log pipeline is writing raw blobs to the configured Azure Storage Account and enriching them into Log Analytics / Traffic Analytics (`NTANetAnalytics`).

This skill unifies flow-log configuration troubleshooting with Storage-side raw-blob ingestion checks: they are the same diagnostic funnel (flow-log enabled → raw blobs in Storage → Traffic Analytics enrichment in Log Analytics).

## Builder Upload Settings

| Field | Value |
| --- | --- |
| Skill name | `vnet-flow-logs-and-ingestion` |
| Primary purpose | Diagnose VNet Flow Logs enablement and the raw-blob → Storage → Log Analytics / Traffic Analytics ingestion pipeline. |
| Recommended tools | `RunAzCliReadCommands`, `QueryLogAnalyticsByWorkspaceId`, `GetAzCliHelp` |
| Recommended knowledge files | `vnet-flow-logs/vnet-flow-logs-traffic-analytics-terraform-guide.md`, `vnet-flow-logs/troubleshooting-scenarios.md`, `vnet-flow-logs/kql-catalog.md` |
| Default run mode | Read-only diagnostics can run autonomously if the response plan allows; Review for any Storage lifecycle, firewall, RBAC, or flow-log enable/disable change. |

## Trigger Conditions

Load this skill when the user asks about any of the following:

- VNet Flow Logs are not visible in Storage, or raw flow-log blobs appear missing.
- Traffic Analytics (`NTANetAnalytics`) does not show recent records.
- One VNet has data while another VNet is missing.
- The agent sees a flow log resource but no `NTANetAnalytics` records.
- Flow log records appear delayed beyond the expected Traffic Analytics cycle.
- Flow logs appear duplicated or unexpectedly high volume.
- Storage retention, region, SKU/kind, access, private endpoint, or authorization is questioned as a cause of missing data.
- The user asks whether VNet Flow Logs and their Storage destination are correctly configured by Terraform.

## Non-Goals

- Do not perform packet capture unless a human explicitly requests it.
- Do not disable, delete, or recreate flow log resources.
- Do not edit, overwrite, delete, or modify the block structure of blobs written by VNet Flow Logs.
- Do not rotate keys, change customer-managed keys, change network rules, or alter lifecycle policies without explicit Review-mode approval.
- Do not use Shared Key if the environment requires Entra-based auth and Shared Key is disabled.
- Do not infer application payload behavior from flow logs. VNet Flow Logs are Layer 4 flow records, not packet payload traces.

## Safety And Permissions

Start with read-only evidence. For any write action, produce a Review-mode recommendation and wait for approval.

Required minimum Azure permissions:

- Reader on the project resource group.
- Log Analytics Reader on the project resource group or workspace.
- Monitoring Reader on the project resource group.
- Storage data-plane read permissions only if raw blob inspection is required and allowed by policy.

If access fails, invoke or recommend `rbac-and-resource-access-check`.

## Storage Requirements To Validate

| Requirement | Expected state for VNet Flow Logs | Source |
| --- | --- | --- |
| Region | Storage Account should be in the same region as the virtual network. | VNet Flow Logs storage considerations |
| Account type | Standard Storage Account; premium is not supported. | VNet Flow Logs storage considerations |
| Subscription/tenant | Same subscription as the VNet, or a subscription associated with the same Entra tenant. | VNet Flow Logs storage considerations |
| Blob operations | Do not modify blob block structure while ingestion is active. | VNet Flow Logs storage considerations |
| Retention | Retention should match lab/demo or operational requirements. | Project Terraform |

## Procedure

1. Identify the affected VNet scope: hub, spoke-app, spoke-data, subnet, NIC, or all VNets.
2. Identify the Terraform source of truth:
   - `Infra/monitoring.tf` for `azurerm_network_watcher_flow_log`.
   - `Infra/outputs.tf` for workspace, storage, and Network Watcher outputs.
   - `Infra/network.tf` for VNet/subnet topology.
3. Confirm the flow log resource exists and is enabled.
4. Confirm the target resource ID is the expected VNet resource ID.
5. Confirm the Storage Account is the configured flow-log destination, and validate account kind, SKU, and region against the Storage Requirements table.
6. Check raw Storage blob presence and freshness with read-only list operations, and compare blob timestamps with expected flow-log and Traffic Analytics intervals.
7. Confirm Traffic Analytics is enabled when the investigation expects `NTANetAnalytics` records, and that the Log Analytics workspace ID matches the Terraform output.
8. Check `NTANetAnalytics` freshness and target coverage.
9. Classify the result using the classification table below.
10. Return evidence, root cause hypothesis, confidence, and next action.

## Classification

| Classification | Evidence | Likely cause | Next step |
| --- | --- | --- | --- |
| Healthy | Recent Storage blobs and recent `NTANetAnalytics` records. | None. | Continue at the Traffic Analytics / KQL layer (`traffic-analytics-kql-analysis`). |
| Delayed | Raw blobs exist but `NTANetAnalytics` is not recent. | Traffic Analytics processing delay. | Wait one interval and re-query. |
| No traffic | Flow log enabled but no new records after the traffic window. | Workload did not generate flows. | Run `Infra/scripts/generate-baseline-traffic.sh`. |
| No raw blobs | No recent blobs after generated traffic. | Flow log not enabled, wrong Storage target, or region mismatch. | Check flow-log enabled state, Storage target, and region. |
| Misconfigured target | Flow log target resource does not match the expected VNet. | Wrong VNet/resource scope. | Review `Infra/monitoring.tf`. |
| Storage issue | Flow log enabled but no raw blobs; Storage mismatch, unsupported SKU/region/key/network setting. | Storage account configuration or access problem. | Inspect Storage config and permissions. |
| Workspace issue | Raw blobs exist but the configured workspace differs from the expected workspace. | Traffic Analytics workspace mismatch. | Compare Terraform output and flow-log config. |
| Retention issue | Older data missing but current data healthy. | Storage/workspace retention or lifecycle policy. | Confirm expected retention and lifecycle policy. |
| Permission issue | Azure CLI/KQL calls fail with 403 or missing resources. | Agent RBAC / data-plane permission gap. | Invoke `rbac-and-resource-access-check`. |

## KQL Snippets

### Ingestion smoke test

```kql
NTANetAnalytics
| where SubType == "FlowLog"
| take 10
```

### Freshness by target

```kql
NTANetAnalytics
| where TimeGenerated > ago(48h)
| summarize Records=count(), FirstSeen=min(TimeGenerated), LastSeen=max(TimeGenerated) by SubType, FlowType, TargetResourceId
| order by LastSeen desc
```

### Recent records for expected flow logs

```kql
NTANetAnalytics
| where SubType == "FlowLog" and TimeGenerated > ago(24h)
| summarize Records=count(), LastSeen=max(TimeGenerated) by TargetResourceId, SrcSubnet, DestSubnet, FlowType
| order by LastSeen desc
```

## Azure CLI Read Commands

Use commands only as read-only diagnostics. Replace placeholders with Terraform outputs. Use `GetAzCliHelp` if command syntax differs in the installed Azure CLI version.

```bash
az network watcher flow-log list \
  --location <location> \
  --resource-group <network-watcher-resource-group> \
  --output table
```

```bash
az monitor log-analytics workspace show \
  --resource-group <resource-group> \
  --workspace-name <workspace-name>
```

```bash
az storage account show \
  --name <flow-log-storage-account> \
  --resource-group <resource-group> \
  --query "{name:name, location:location, kind:kind, sku:sku.name, allowSharedKeyAccess:allowSharedKeyAccess, minTlsVersion:minTlsVersion}" \
  --output json
```

```bash
az storage container list \
  --account-name <flow-log-storage-account> \
  --auth-mode login \
  --query "[].name" \
  --output table
```

```bash
az storage blob list \
  --account-name <flow-log-storage-account> \
  --container-name insights-logs-flowlogflowevent \
  --auth-mode login \
  --num-results 20 \
  --query "[].{name:name, lastModified:properties.lastModified, size:properties.contentLength}" \
  --output table
```

If a Storage command fails with data-plane authorization errors, do not request broad permissions immediately. Report the exact missing access and recommend least privilege (hand off to `rbac-and-resource-access-check`).

## Evidence Required

Always collect and return:

- Affected VNet, subnet, NIC, or VM.
- Flow log resource name and target resource ID.
- Storage Account name, resource group, location, SKU/kind, and whether raw blobs are recent.
- Log Analytics workspace ID / customer ID.
- Traffic Analytics enabled state and processing interval if visible.
- KQL query used and time window.
- Most recent `NTANetAnalytics` timestamp.
- Any error code, especially 403/RBAC errors.

## Output Format

Return the final answer in this format:

```text
Finding: <short status>
Affected scope: <VNet/subnet/NIC/resource group>
Storage Account: <name / resource group / location>
Raw blob status: <recent | stale | missing | access denied>
Traffic Analytics status: <recent | stale | missing | not checked>
Evidence:
- <Azure resource evidence>
- <Storage evidence>
- <KQL evidence>
Classification: Healthy | Delayed | No traffic | No raw blobs | Misconfigured target | Storage issue | Workspace issue | Retention issue | Permission issue | Unknown
Root cause hypothesis: <evidence-based explanation>
Confidence: High | Medium | Low
Recommended next step: <read-only step or Review-mode remediation>
References:
- <project doc>
- <official Microsoft URL>
```

## Escalation

Escalate to a human SRE or Cloud Architect when:

- Flow logs are enabled but no raw blobs appear after traffic generation and reasonable waiting time.
- Storage Account constraints violate VNet Flow Logs requirements (unsupported SKU/region/encryption/network configuration).
- Traffic Analytics is not writing to the expected workspace.
- The issue requires disabling/re-enabling flow logs.
- Customer-managed key rotation or Storage network restrictions might affect ingestion.

## Official Sources

- VNet Flow Logs overview: https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-overview
- VNet Flow Logs storage considerations: https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-overview#storage-account
- Traffic Analytics overview: https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics
- Storage Account overview: https://learn.microsoft.com/en-us/azure/storage/common/storage-account-overview
- Log Analytics workspace overview: https://learn.microsoft.com/en-us/azure/azure-monitor/logs/log-analytics-workspace-overview
- Log Analytics API: https://learn.microsoft.com/en-us/azure/azure-monitor/logs/api/overview
