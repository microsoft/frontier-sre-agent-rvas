---
name: vnet-flow-logs-and-ingestion
description: Diagnose VNet Flow Logs enablement and the Storage-write to Log Analytics / Traffic Analytics ingestion pipeline - missing, delayed, mis-scoped, duplicated, or storage-blocked flow data.
---

# vnet-flow-logs-and-ingestion

Use this skill when investigating missing, delayed, duplicated, disabled, mis-scoped, or unexpected Azure Virtual Network Flow Logs for the hub, app, or data VNets in this Terraform project, and when validating that the flow-log pipeline reports successful block-blob writes to the configured Azure Storage Account and enriches them into Log Analytics / Traffic Analytics (`NTANetAnalytics`).

This skill unifies flow-log configuration troubleshooting with Storage write metrics: they are the
same diagnostic funnel (flow log enabled → successful `PutBlock` and `PutBlockList` operations →
Traffic Analytics enrichment in Log Analytics).

## Trigger Conditions

Load this skill when the user asks about any of the following:

- Azure Storage metrics show no successful flow-log block-blob writes.
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
- Do not rotate keys, change customer-managed keys, change network rules, or alter lifecycle policies unless the active trigger explicitly permits the exact action.
- Do not use Shared Key if the environment requires Entra-based auth and Shared Key is disabled.
- Do not infer application payload behavior from flow logs. VNet Flow Logs are Layer 4 flow records, not packet payload traces.

## Safety And Permissions

Start with read-only evidence. Any write action must be explicitly permitted by the active trigger, narrowly scoped, reversible, and followed by a telemetry verification.

Required minimum Azure permissions:

- Reader on the project resource group.
- Log Analytics Reader on the project resource group or workspace.
- Monitoring Reader on the project resource group.

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
2. Identify the workload Terraform resources for the flow logs, workspace, storage account, and
   VNet/subnet topology.
3. Confirm the flow log resource exists and is enabled.
4. Confirm the target resource ID is the expected VNet resource ID.
5. Confirm the Storage Account is the configured flow-log destination, and validate account kind, SKU, and region against the Storage Requirements table.
6. Query Azure Monitor Storage metrics for successful `PutBlock` and `PutBlockList` operations in
   the investigation window. Direct Blob listing is not a valid check when public network access is
   intentionally disabled.
7. Confirm Traffic Analytics is enabled when the investigation expects `NTANetAnalytics` records, and that the Log Analytics workspace ID matches the Terraform output.
8. Check `NTANetAnalytics` freshness and target coverage.
9. Classify the result using the classification table below.
10. Return evidence, root cause hypothesis, confidence, and next action.

## Classification

| Classification | Evidence | Likely cause | Next step |
| --- | --- | --- | --- |
| Healthy | Recent successful `PutBlock`/`PutBlockList` operations and recent `NTANetAnalytics` records. | None. | Continue at the Traffic Analytics / KQL layer (`traffic-analytics-kql-analysis`). |
| Delayed | Successful writes exist but `NTANetAnalytics` is not recent. | Traffic Analytics processing delay. | Wait one interval and re-query. |
| No traffic | Flow log enabled but no new records after the traffic window. | Workload did not generate flows. | Report that the window contains no workload traffic and state which generated traffic would confirm it. Do not treat silence as an outage. |
| No successful writes | No successful `PutBlock`/`PutBlockList` operations after generated traffic. | Flow log not enabled, wrong Storage target, or region mismatch. | Check flow-log enabled state, Storage target, and region. |
| Misconfigured target | Flow log target resource does not match the expected VNet. | Wrong VNet/resource scope. | Review the workload Terraform flow-log resources. |
| Storage issue | Flow log enabled but no successful writes; Storage mismatch, unsupported SKU/region, or network setting. | Storage account configuration or trusted-service access problem. | Inspect Storage configuration and write metrics. |
| Workspace issue | Successful writes exist but the configured workspace differs from the expected workspace. | Traffic Analytics workspace mismatch. | Compare Terraform output and flow-log config. |
| Retention issue | Older data missing but current data healthy. | Storage/workspace retention or lifecycle policy. | Confirm expected retention and lifecycle policy. |
| Permission issue | Azure CLI/KQL calls fail with 403 or missing resources. | Agent RBAC / data-plane permission gap. | Invoke `rbac-and-resource-access-check`. |

## Reference File

`vnet-flow-logs-and-ingestion/references/ingestion-diagnostics.md` holds the executable KQL and
Azure CLI read-only commands for every step of the procedure. The path above is the exact name the
file is registered under. Read it when you need a command, rather than composing one from memory.

## Evidence Required

Always collect and return:

- Affected VNet, subnet, NIC, or VM.
- Flow log resource name and target resource ID.
- Storage Account name, resource group, location, SKU/kind, public-network state, and successful
   `PutBlock`/`PutBlockList` totals for the investigation window.
- Log Analytics workspace ID / customer ID.
- Traffic Analytics enabled state and processing interval if visible.
- KQL query used and time window.
- Most recent `NTANetAnalytics` timestamp.
- Any control-plane, metrics, or KQL error code.

## Output Format

Return the final answer in this format:

```text
Finding: <short status>
Affected scope: <VNet/subnet/NIC/resource group>
Storage Account: <name / resource group / location>
Storage write status: <PutBlock count / PutBlockList count / observation window>
Traffic Analytics status: <recent | stale | missing | not checked>
Evidence:
- <Azure resource evidence>
- <Storage evidence>
- <KQL evidence>
Classification: Healthy | Delayed | No traffic | No successful writes | Misconfigured target | Storage issue | Workspace issue | Retention issue | Permission issue | Unknown
Root cause hypothesis: <evidence-based explanation>
Confidence: High | Medium | Low
Recommended next step: <read-only step or active-trigger-permitted remediation>
References:
- <project doc>
- <official Microsoft URL>
```

## Escalation

Escalate to a human SRE or Cloud Architect when:

- Flow logs are enabled but no successful block-blob writes appear after traffic generation and a
   reasonable waiting time.
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
