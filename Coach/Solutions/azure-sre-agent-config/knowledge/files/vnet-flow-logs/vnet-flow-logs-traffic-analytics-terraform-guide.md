# VNet Flow Logs and Traffic Analytics with Terraform

## Document Purpose

| Field | Value |
| --- | --- |
| Audience | Principal Architect, Cloud/Network Architect, Platform Engineer, Security/Operations team. |
| Objective | Document how to enable, use, and govern Azure Virtual Network Flow Logs with and without Traffic Analytics using Terraform. |
| Scope | Prerequisites, deployment order, Terraform resources, parameters, networking requirements, IAM/RBAC, troubleshooting scenarios, on-demand activation, and customer checklist. |
| Out of scope | Full migration from NSG Flow Logs, Azure Policy enterprise rollout, Microsoft Sentinel end-to-end, and custom SIEM pipeline. |
| Last reviewed | 2026-05-20. |
| Source criteria | Microsoft Learn for Azure behavior; HashiCorp Registry for Terraform topics; local files for lab implementation. |

Primary sources:

- VNet Flow Logs overview: https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-overview
- VNet Flow Logs management: https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-manage
- Traffic Analytics overview: https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics
- Traffic Analytics schema: https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-schema
- Traffic Analytics queries: https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-queries
- Traffic Analytics usage scenarios: https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-usage-scenarios
- RBAC Network Watcher: https://learn.microsoft.com/en-us/azure/network-watcher/required-rbac-permissions
- Hub-spoke networking: https://learn.microsoft.com/en-us/azure/architecture/networking/architecture/hub-spoke
- User-defined routes: https://learn.microsoft.com/en-us/azure/virtual-network/virtual-networks-udr-overview
- Azure Firewall features by SKU: https://learn.microsoft.com/en-us/azure/firewall/features-by-sku
- Storage Blob authorization with Microsoft Entra ID: https://learn.microsoft.com/en-us/azure/storage/blobs/authorize-access-azure-active-directory
- Azure Storage encryption: https://learn.microsoft.com/en-us/azure/storage/common/storage-service-encryption
- Log Analytics access control: https://learn.microsoft.com/en-us/azure/azure-monitor/logs/manage-access
- Terraform `azurerm_network_watcher_flow_log`: https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/resources/network_watcher_flow_log

## Requirements Coverage

| Requirement | Where to read it | Key evidence |
| --- | --- | --- |
| 1. What VNet Flow Logs and Traffic Analytics are | [Executive Summary](#executive-summary), [VNet Flow Logs and Traffic Analytics](../documentation/kql-catalog.md#vnet-flow-logs-e-traffic-analytics) | Definition, raw/enriched model, `NTANetAnalytics` and `NTAIpDetails` tables. |
| 2. What they are used for and what problems they solve | [Using VNet Flow Logs Without Traffic Analytics](#using-vnet-flow-logs-without-traffic-analytics), [Using VNet Flow Logs With Traffic Analytics](#using-vnet-flow-logs-with-traffic-analytics), [Combined Value](#combined-value-raw-logs--traffic-analytics) | Troubleshooting, security, audit, capacity, dashboards, and forensics. |
| 3. How to enable them | [Activation Order](#activation-order), [Prerequisites](#prerequisites), [Terraform Procedure](#terraform-procedure-vnet-flow-logs-without-traffic-analytics) | Subscription/provider/Network Watcher/Storage/Workspace/flow log sequence. |
| 4. How to use them | [Using VNet Flow Logs Without Traffic Analytics](#using-vnet-flow-logs-without-traffic-analytics), [Using VNet Flow Logs With Traffic Analytics](#using-vnet-flow-logs-with-traffic-analytics), [Lab Validation Commands](#lab-validation-commands) | Storage raw, Log Analytics, KQL, dashboards, workbooks, alerts. |
| 5. Limitations | [Limitations](#limitations) | Aggregation, latency, scope, private endpoints, duplicates, costs. |
| 6. Pitfalls | [Operational Pitfalls](#operational-pitfalls), [IAM/RBAC](#iamrbac), [Data Security, Encryption and Data Access](#data-security-encryption-and-data-access) | RBAC, DCR/DCE, blob write, Shared Key, ingestion, retention. |

## Executive Summary

Azure Virtual Network Flow Logs records information about IP traffic traversing a virtual network. Microsoft describes it as a Network Watcher feature that writes flow information to Azure Storage and can be consumed by visualization tools, SIEM, IDS, or analytics platforms. It operates at OSI layer 4, so it is not a packet capture and does not inspect application payloads. Source: https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-overview

Traffic Analytics adds an operational layer on top of raw logs: it reads flow logs from Storage, aggregates flows, enriches them with security, topology, and geography information, and writes them to Log Analytics. The main tables are `NTANetAnalytics` for enriched flows and `NTAIpDetails` for public IP details. Source: https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics, https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-schema

The demo uses a hub-spoke baseline with centralized routing: Azure Firewall Basic is deployed in the hub and the spoke route tables direct app-data and Internet-bound traffic toward the firewall's private IP. This choice makes the demo closer to a real enterprise design: first validate a correct data path, then inject NSG or UDR faults. Azure Firewall Basic is sufficient for the lab because it supports stateful filtering, outbound SNAT, network rules, and application FQDN filtering. Source: https://learn.microsoft.com/en-us/azure/firewall/features-by-sku#azure-firewall-basic-features

| Requirement | Recommended choice | Rationale | Source |
| --- | --- | --- | --- |
| Raw evidence, audit, export to SIEM/data lake | VNet Flow Logs without Traffic Analytics | Keep raw JSON in Storage and control parsing, normalization, and retention yourself. | https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-overview#common-use-cases |
| Dashboards, KQL, fast troubleshooting, enrichment | VNet Flow Logs with Traffic Analytics | Get `NTANetAnalytics`, `NTAIpDetails`, dashboards, and Log Analytics queries. | https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics#why-traffic-analytics |
| Customer demo or first enterprise operating model | VNet Flow Logs with Traffic Analytics, while also retaining raw logs | Show immediate value and preserve raw evidence for forensics. | https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-usage-scenarios |
| Maximum native Azure cost control | VNet Flow Logs without Traffic Analytics, if an external analytics platform already exists | Avoid Traffic Analytics processing and Log Analytics ingestion, but shift complexity to custom platforms. | https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-overview#pricing |

## Activation Order

| Step | What to do | Why | Expected evidence | Source |
| --- | --- | --- | --- | --- |
| 1 | Verify subscription, tenant, and region. | Storage, VNet Flow Logs, and Traffic Analytics have region/subscription/tenant constraints. | Correct subscription/tenant and supported region. | https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-overview#availability |
| 2 | Register `Microsoft.Insights`. | Microsoft declares this provider is required to log VNet traffic. | Provider in `Registered` state. | https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-manage#register-insights-provider |
| 3 | Verify RBAC for the Terraform identity. | Flow Logs and Traffic Analytics require Network, Storage, OperationalInsights, and Insights actions. | Roles or custom role assigned to the correct scopes. | https://learn.microsoft.com/en-us/azure/network-watcher/required-rbac-permissions |
| 4 | Create or identify the regional Network Watcher. | `azurerm_network_watcher_flow_log` is a child of the Network Watcher. | Network Watcher name and resource group. | https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/data-sources/network_watcher |
| 5 | Create or identify the target VNet/subnet/NIC. | The flow log requires a `target_resource_id`. | Target resource ID present. | https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-manage#create-a-flow-log |
| 6 | Create Storage Account. | Raw flow logs are written to Storage. | Standard/StorageV2 Storage Account in the correct region. | https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-overview#storage-account |
| 7 | Create Log Analytics workspace if Traffic Analytics is needed. | Traffic Analytics writes enriched data to Azure Monitor Logs. | Workspace ready, retention defined, access assigned. | https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics#key-components |
| 8 | Create `azurerm_network_watcher_flow_log`. | Target, Storage, and Network Watcher are available. | Flow log enabled. | https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/resources/network_watcher_flow_log |
| 9 | Add `traffic_analytics` if required. | Requires workspace ID, workspace region, and workspace resource ID. | Data in `NTANetAnalytics` after the processing cycle. | https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-schema#data-aggregation |
| 10 | Validate raw logs and KQL. | Confirms end-to-end. | Blob in Storage and records in Log Analytics, if TA is enabled. | https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-manage#download-a-flow-log |

In the repository, the sequence is implemented mainly in [../terraform/monitoring.tf](../terraform/monitoring.tf), with variables in [../terraform/variables.tf](../terraform/variables.tf) and naming/targets in [../terraform/locals.tf](../terraform/locals.tf).

## Prerequisites

| Area | Requirement | Implication | Decision criteria | Source |
| --- | --- | --- | --- | --- |
| Azure account | Active subscription. | Required to create or configure resources. | Use a workload subscription or an observability subscription if supported by the tenant model. | https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-manage#prerequisites |
| Resource provider | `Microsoft.Insights` registered. | Without registration, configuration may fail. | Register it as a platform prerequisite. | https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-manage#register-insights-provider |
| Network Watcher | Regional Network Watcher existing or created. | The flow log is a child of the regional Network Watcher. | In standard environments use `NetworkWatcher_<region>` in `NetworkWatcherRG`; create only if absent. | https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/data-sources/network_watcher |
| Centralized routing | Azure Firewall in the hub, `AzureFirewallSubnet` and `AzureFirewallManagementSubnet` at least `/26`, route tables on the spokes. | Demonstrates a realistic hub-spoke path with a central next hop. | Demo: Azure Firewall Basic; production: evaluate Standard/Premium based on DNS proxy, throughput, and threat protection needs. | https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/resources/firewall |
| Target | Virtual network, subnet, or network interface. | Higher scope simplifies coverage; lower scope reduces noise/cost. | Prefer VNet for enterprise baseline; use subnet/NIC for targeted on-demand. | https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-manage#create-a-flow-log |
| Storage | Standard Storage Account, same region as the VNet. | Premium is not supported; raw logs are written to blob. | Use Storage dedicated to flow logs. | https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-overview#storage-account |
| Log Analytics | Workspace if Traffic Analytics is enabled. | Required for `NTANetAnalytics` and `NTAIpDetails`. | Centralized operations workspace or dedicated demo workspace. | https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics#key-components |
| Terraform | `azurerm` provider configured. | Manages core Azure resources. | Version pinning and provider config consistent with the landing zone. | https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs |
| Cost governance | Retention and processing interval defined. | Flow logs, Traffic Analytics, Storage, and Log Analytics generate separate costs. | 10 minutes for demo/incident; 60 minutes for steady state. | https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-overview#pricing |

Architectural notes:

- Microsoft recommends disabling NSG Flow Logs on the same workloads before enabling VNet Flow Logs, to avoid duplicate recording and additional costs. Source: https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-overview#virtual-network-flow-logs-compared-to-network-security-group-flow-logs
- If flow logs are configured at multiple levels, Microsoft documents this preference order: NIC > subnet > virtual network. Source: https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-manage#create-a-flow-log

## Terraform Procedure: VNet Flow Logs Without Traffic Analytics

This mode enables raw collection in Azure Storage. It is suitable for audit, compliance, export to SIEM/data lake, forensics, and scenarios where the customer wants to build their own parsing/enrichment layer.

### Minimum Pattern

```hcl
resource "azurerm_storage_account" "flow_logs" {
  name                     = "stflowlogs001"
  resource_group_name      = azurerm_resource_group.observability.name
  location                 = azurerm_resource_group.observability.location
  account_tier             = "Standard"
  account_replication_type = "LRS"
  account_kind             = "StorageV2"
}

data "azurerm_network_watcher" "regional" {
  name                = "NetworkWatcher_westeurope"
  resource_group_name = "NetworkWatcherRG"
}

resource "azurerm_network_watcher_flow_log" "vnet" {
  network_watcher_name = data.azurerm_network_watcher.regional.name
  resource_group_name  = data.azurerm_network_watcher.regional.resource_group_name
  name                 = "fl-prod-app-vnet"

  target_resource_id = azurerm_virtual_network.app.id
  storage_account_id = azurerm_storage_account.flow_logs.id
  enabled            = true
  version            = 2

  retention_policy {
    enabled = true
    days    = 7
  }
}
```

Sources: https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/resources/storage_account, https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/data-sources/network_watcher, https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/resources/network_watcher_flow_log

### Resource `azurerm_storage_account`

In the lab it is defined in [../terraform/monitoring.tf](../terraform/monitoring.tf). It is the repository for raw flow logs.

| Parameter | Lab value | Meaning | Values / constraints | Implications | Decision criteria | Source |
| --- | --- | --- | --- | --- | --- | --- |
| `name` | `substr("${local.normalized_prefix}${random_string.suffix.result}flow", 0, 24)` | Global name of the Storage Account. | Lowercase alphanumeric, globally unique. | Name collision blocks the deploy. | Short prefix + random suffix. | https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/resources/storage_account |
| `resource_group_name` | `azurerm_resource_group.demo.name` | Resource group for Storage. | Existing or created RG name. | Determines lifecycle and ownership. | Demo: workload RG; enterprise: observability RG if centrally governed. | https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/resources/storage_account |
| `location` | `azurerm_resource_group.demo.location` | Storage region. | Supported Azure region. | Microsoft requires Storage in the same region as the VNet. | Align to the target VNet. | https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-overview#storage-account |
| `account_tier` | `Standard` | Performance tier. | `Standard`, `Premium`. | Premium is not supported for VNet Flow Logs. | Use `Standard`. | https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-overview#storage-account |
| `account_replication_type` | `LRS` | Storage replication. | `LRS`, `ZRS`, `GRS`, `GZRS`, other supported values. | Higher replication increases resilience and cost. | Demo: `LRS`; production: consider `ZRS`/geo-replication. | https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-manage#create-a-flow-log |
| `account_kind` | `StorageV2` | Account type. | `StorageV2` recommended. | Supports the modern general-purpose model. | Use `StorageV2`. | https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/resources/storage_account |
| `https_traffic_only_enabled` | `true` | Requires HTTPS. | Boolean. | Improves security baseline. | Leave as `true`. | https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/resources/storage_account |
| `min_tls_version` | `TLS1_2` | Minimum TLS version. | `TLS1_0`, `TLS1_1`, `TLS1_2`. | Legacy TLS increases risk. | Use `TLS1_2`. | https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/resources/storage_account |
| `allow_nested_items_to_be_public` | `false` | Blocks public access to blobs/containers. | Boolean. | Reduces risk of raw log exposure. | Set to `false`. | https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/resources/storage_account |
| `shared_access_key_enabled` | `false` | Disables Shared Key. | Boolean. | Requires Entra ID access for supported operations. | If policy prohibits Shared Key, set to `false` and configure the provider accordingly. | https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/resources/storage_account |
| `blob_properties.delete_retention_policy.days` | `var.flow_log_retention_days` | Blob soft delete. | 1-365 per provider. | Aids recovery from deletions, but does not replace flow log retention. | Demo: 7; production: audit/cost policy. | https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/resources/storage_account |
| `tags` | `local.tags` | Governance metadata. | Key/value map. | Owner, environment, cost, lifecycle. | Mandatory in enterprise. | https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/resources/storage_account |

Warning: HashiCorp notes that `azurerm_network_watcher_flow_log` creates a lifecycle management rule on the Storage Account and may overwrite existing rules. For this reason it is preferable to use Storage dedicated to flow logs. Source: https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/resources/network_watcher_flow_log

### Network Watcher

In the lab, the Network Watcher is read if `create_network_watcher = false`, or created if `create_network_watcher = true`. The logic is in [../terraform/locals.tf](../terraform/locals.tf).

| Terraform object | When to use | Key parameters | Implications | Decision criteria | Source |
| --- | --- | --- | --- | --- | --- |
| `data.azurerm_network_watcher` | Regional Network Watcher already present. | `name`, `resource_group_name`. | Avoids duplicates and respects the standard Azure model. | Recommended default in subscriptions where `NetworkWatcher_<region>` exists. | https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/data-sources/network_watcher |
| `azurerm_network_watcher` | Network Watcher absent or managed by the landing zone module. | `name`, `resource_group_name`, `location`, `tags`. | Creates a new regional resource. | Use only if the Network Watcher does not exist or must be Terraform-owned. | https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/resources/network_watcher |

### Resource `azurerm_network_watcher_flow_log`

In the lab it is created with `for_each` over hub, app spoke, and data spoke in [../terraform/monitoring.tf](../terraform/monitoring.tf).

| Parameter | Lab value | Meaning | Values / constraints | Implications | Decision criteria | Source |
| --- | --- | --- | --- | --- | --- | --- |
| `for_each` | Hub, spoke-app, spoke-data. | Creates a flow log per target. | Map of target resource IDs. | Selective enablement. | Use maps to scale across multiple VNets/subnets/NICs. | https://developer.hashicorp.com/terraform/language/meta-arguments/for_each |
| `network_watcher_name` | `local.network_watcher_name` | Network Watcher name. | Existing or created name. | Changing forces a new resource. | Derive from data source/resource. | https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/resources/network_watcher_flow_log |
| `resource_group_name` | `local.network_watcher_rg` | Resource group of the Network Watcher. | RG where the Network Watcher exists. | Common mistake: using the workload RG instead of `NetworkWatcherRG`. | Use the Network Watcher's output/data source. | https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/resources/network_watcher_flow_log |
| `name` | `fl-${local.workload_prefix}-${each.key}` | Flow log name. | String; changing is ForceNew. | Must be readable and correlatable to the target. | Include environment, app, and target. | https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/resources/network_watcher_flow_log |
| `location` | RG location. | Flow log location. | Default: Network Watcher location. | Changing is ForceNew. | Align to the Network Watcher/VNet region. | https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/resources/network_watcher_flow_log |
| `target_resource_id` | VNet ID. | Resource to log. | VNet, subnet, or NIC per portal/API. | Higher scope increases coverage and volume; lower scope reduces noise. | VNet for baseline; subnet/NIC for on-demand. | https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-manage#create-a-flow-log |
| `storage_account_id` | `azurerm_storage_account.flow_logs.id` | Raw log destination. | Storage Account ID. | Must comply with region/subscription/tenant constraints. | Dedicated, governed Storage. | https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-overview#storage-account |
| `enabled` | `true` | Enables or disables the flow log. | Boolean. | `false` keeps the resource but stops collection. | Useful for a temporary pause without losing configuration. | https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-manage#disable-a-flow-log |
| `version` | `2` | Flow log version. | Provider supports `1` and `2`. | Newer version exposes more fields. | Use `2`, unless there are legacy constraints. | https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/resources/network_watcher_flow_log |
| `retention_policy.enabled` | `true` | Enables flow log retention. | Boolean. | Avoids unintended infinite retention. | `true` in demo and production. | https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/resources/network_watcher_flow_log |
| `retention_policy.days` | `var.flow_log_retention_days` | Raw log retention days. | Number of days; portal allows `0` for retain indefinitely. | Increases Storage cost and forensic window. | Demo: 7; production: audit/cost policy. | https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-manage#create-a-flow-log |
| `tags` | `local.tags` | Governance. | Map. | Owner/cost/lifecycle. | Align to enterprise standards. | https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/resources/network_watcher_flow_log |

## Terraform Procedure: VNet Flow Logs With Traffic Analytics

This mode keeps raw logs in Storage and adds aggregated, enriched data in Log Analytics.

### Minimum Pattern

```hcl
resource "azurerm_log_analytics_workspace" "traffic" {
  name                = "law-prod-network"
  location            = azurerm_resource_group.observability.location
  resource_group_name = azurerm_resource_group.observability.name
  sku                 = "PerGB2018"
  retention_in_days   = 30
}

resource "azurerm_network_watcher_flow_log" "vnet" {
  network_watcher_name = data.azurerm_network_watcher.regional.name
  resource_group_name  = data.azurerm_network_watcher.regional.resource_group_name
  name                 = "fl-prod-app-vnet"

  target_resource_id = azurerm_virtual_network.app.id
  storage_account_id = azurerm_storage_account.flow_logs.id
  enabled            = true
  version            = 2

  retention_policy {
    enabled = true
    days    = 7
  }

  traffic_analytics {
    enabled               = true
    workspace_id          = azurerm_log_analytics_workspace.traffic.workspace_id
    workspace_region      = azurerm_log_analytics_workspace.traffic.location
    workspace_resource_id = azurerm_log_analytics_workspace.traffic.id
    interval_in_minutes   = 10
  }
}
```

Sources: https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/resources/log_analytics_workspace, https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/resources/network_watcher_flow_log, https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-manage#create-a-flow-log

### Resource `azurerm_log_analytics_workspace`

In the lab it is defined in [../terraform/monitoring.tf](../terraform/monitoring.tf).

| Parameter | Lab value | Meaning | Values / constraints | Implications | Decision criteria | Source |
| --- | --- | --- | --- | --- | --- | --- |
| `name` | `law-${local.workload_prefix}-${random_string.suffix.result}` | Workspace name. | 4-63 characters, letters/digits/`-`; cannot start or end with `-`. | Changing is ForceNew. | Name with environment/app/region. | https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/resources/log_analytics_workspace |
| `location` | RG location. | Workspace region. | Supported Azure region. | If the workspace is not available in the same region, Microsoft allows a workspace in another supported region without extra cross-region transfer for Traffic Analytics. | Prefer the same region when available. | https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics#availability |
| `resource_group_name` | Demo RG. | Workspace resource group. | RG name. | Traffic Analytics creates DCR/DCE in the same RG as the workspace. | Use an observability RG with a clear owner. | https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-manage#enable-or-disable-traffic-analytics |
| `sku` | `PerGB2018` | Pricing tier. | Provider lists `PerGB2018`, `CapacityReservation`, and other legacy SKUs. | Capacity reservation implies a commitment. | `PerGB2018` for demos and variable environments. | https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/resources/log_analytics_workspace |
| `retention_in_days` | `var.log_analytics_retention_days` | Log Analytics data retention. | 30-730 days in the provider. | Increases retention cost and investigation window. | Demo: 30; production: SOC/compliance policy. | https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/resources/log_analytics_workspace |
| `tags` | `local.tags` | Governance. | Map. | Owner/cost/lifecycle. | Align to enterprise tags. | https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/resources/log_analytics_workspace |

### `traffic_analytics` Block

The `traffic_analytics` block is optional. If absent, data remains raw in Storage and does not appear in `NTANetAnalytics`/`NTAIpDetails` via Traffic Analytics.

| Parameter | Lab value | Meaning | Values / constraints | Implications | Decision criteria | Source |
| --- | --- | --- | --- | --- | --- | --- |
| `enabled` | `true` | Enables Traffic Analytics for the flow log. | Boolean. | If `false`/absent, no TA dashboard and no TA tables. | Enable for troubleshooting, dashboards, KQL, and SOC/NOC. | https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/resources/network_watcher_flow_log |
| `workspace_id` | `azurerm_log_analytics_workspace.demo.workspace_id` | Workspace GUID/customer ID. | Workspace GUID. | Required to link processing. | Use the provider attribute; do not hardcode. | https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/resources/network_watcher_flow_log |
| `workspace_region` | `azurerm_log_analytics_workspace.demo.location` | Workspace region. | Workspace region. | Must match the workspace. | Derive from the workspace. | https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/resources/network_watcher_flow_log |
| `workspace_resource_id` | `azurerm_log_analytics_workspace.demo.id` | Azure resource ID of the workspace. | Resource ID. | Required for authorization/destination. | Derive from the workspace. | https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/resources/network_watcher_flow_log |
| `interval_in_minutes` | `var.traffic_analytics_interval_minutes` | Processing frequency. | Provider default 60; portal allows 10 or 60 minutes. | 10 reduces latency but increases frequency/operational cost; 60 is the standard steady-state default. | 10 for demo/incident; 60 for standard production. | https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-manage#create-a-flow-log |

Traffic Analytics creates and manages Data Collection Rules and Data Collection Endpoints in the same resource group as the Log Analytics workspace, with the prefix `NWTA`. Microsoft warns not to modify them manually. Source: https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-manage#enable-or-disable-traffic-analytics

Traffic Analytics aggregates raw flow logs before writing them to Log Analytics. For analysis of all individual flows, also use the raw blobs. Source: https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-schema#data-aggregation

### Optional Lab Operational Resources

| Terraform resource | File | Purpose | Decision criteria | Source |
| --- | --- | --- | --- | --- |
| `azurerm_application_insights_workbook.traffic_analytics` | [../terraform/monitoring.tf](../terraform/monitoring.tf) | Shared workbook with demo queries. | Useful for customer meetings and NOC/SOC; in production, standardize templates and ownership. | https://learn.microsoft.com/en-us/azure/azure-monitor/visualize/workbooks-overview |
| `azurerm_monitor_scheduled_query_rules_alert_v2.denied_flow_spike` | [../terraform/monitoring.tf](../terraform/monitoring.tf) | KQL alert on deny flow spike. | Enable with validated thresholds and action groups. | https://learn.microsoft.com/en-us/azure/azure-monitor/alerts/alerts-create-log-alert-rule |

## Networking Requirements and Generated Traffic

VNet Flow Logs are collected by the Azure platform. There is no need to open inbound ports to VMs, install agents, or insert appliances in the data path to collect flow logs. The recorded flows are the real or synthetic application traffic traversing the VNet. Source: https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-overview#how-logging-works

In the lab, the application data path uses a deliberate routing choice: the app spoke and data spoke have route tables associated to the workload subnets. The routes `10.30.0.0/16`, `10.20.0.0/16`, and `0.0.0.0/0` point to the private IP of Azure Firewall in the hub. The more-specific routes created by the scripts are temporary faults and do not replace the Terraform baseline. Hub-spoke source: https://learn.microsoft.com/en-us/azure/architecture/networking/architecture/hub-spoke, UDR source: https://learn.microsoft.com/en-us/azure/virtual-network/virtual-networks-udr-overview#user-defined-routes

| Flow | Generated by | Expected visibility | Why it's useful | Source |
| --- | --- | --- | --- | --- |
| Client `10.20.1.10` to web `10.20.2.10/11` HTTP | [Student/Resources/scenarios/scripts/generate-baseline-traffic.sh](Student/Resources/scenarios/scripts/generate-baseline-traffic.sh) | Allowed flow and forward/return bytes/packets. | Healthy traffic baseline. | https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-queries#list-subnets-interacting-with-each-other |
| Client to ILB `10.20.2.100` HTTP | [Student/Resources/scenarios/scripts/generate-baseline-traffic.sh](Student/Resources/scenarios/scripts/generate-baseline-traffic.sh) | Flow toward load balancer/backend when enriched. | Verifies distribution and top conversations. | https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-queries#view-load-balancer-traffic-distribution |
| Client to API `10.30.1.10:8080` | [Student/Resources/scenarios/scripts/generate-baseline-traffic.sh](Student/Resources/scenarios/scripts/generate-baseline-traffic.sh) | InterVNet or subnet-to-subnet. | Verifies app-data communication. | https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-schema#notes |
| Client to DB `10.30.2.10:5432` | [Student/Resources/scenarios/scripts/generate-baseline-traffic.sh](Student/Resources/scenarios/scripts/generate-baseline-traffic.sh) | Allowed if NSG permits; denied in the fault scenario. | NSG troubleshooting and application path. | https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-usage-scenarios#visualize-the-trends-in-network-security-group-nsgnsg-rules-hits |
| Client to `www.microsoft.com:443` | [Student/Resources/scenarios/scripts/generate-baseline-traffic.sh](Student/Resources/scenarios/scripts/generate-baseline-traffic.sh) | `AzurePublic` or enriched public flow. | Identifies public egress. | https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-schema#notes |
| Baseline route to data spoke via Azure Firewall | Terraform in [../terraform/network.tf](../terraform/network.tf) | Next Hop `VirtualAppliance`, firewall private IP, app-data and data-app flows. | Validates healthy centralized routing. | https://learn.microsoft.com/en-us/azure/network-watcher/next-hop-overview |
| More-specific UDR fault `10.20.1.0/24 -> None` | [Student/Resources/scenarios/scripts/trigger-udr-asymmetry.sh](Student/Resources/scenarios/scripts/trigger-udr-asymmetry.sh) | Direction, unbalanced bytes, missing return, `IsFlowCapturedAtUDRHop` where populated. | Routing/asymmetry diagnosis without dismantling the baseline. | https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-schema#traffic-analytics-schema |
| Traffic to Private Endpoint | [../terraform/private-endpoint.tf](../terraform/private-endpoint.tf) | Captured from the source VM side; not from the private endpoint itself. | Demonstrates Private Link visibility from the consumer side. | https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-overview#private-endpoint-traffic |

## IAM/RBAC

Azure RBAC allows assigning only the necessary actions. For Network Watcher, Microsoft indicates Owner, Contributor, Network Contributor, or an equivalent custom role for the required functionality. However, Microsoft clarifies that Network Contributor does not include all the Storage, Compute, OperationalInsights, and Insights actions required by Flow Logs and Traffic Analytics. Source: https://learn.microsoft.com/en-us/azure/network-watcher/required-rbac-permissions

| Identity | Responsibility | Minimum permissions to validate | Recommended scope | Operational notes | Source |
| --- | --- | --- | --- | --- | --- |
| Terraform deployer identity | Create network, Azure Firewall, route table, Storage, Workspace, Flow Logs, Workbook, alerts, and optionally the Network Watcher. | Flow Logs actions: read/write/delete, `configureFlowLog/action`, `queryFlowLogStatus/action`; plus Storage, Network, Log Analytics/Insights if TA is enabled. | Workload RG, `NetworkWatcherRG`, workspace/Storage RG. | In enterprise use a service principal or federated workload identity with a custom role. | https://learn.microsoft.com/en-us/azure/network-watcher/required-rbac-permissions#flow-logs |
| Traffic Analytics operator | View dashboards and run queries. | Read access to the workspace and related resources. | Log Analytics workspace and observed RGs. | Separate read-only operations from deploy. | https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-queries#prerequisites |
| Storage/raw log consumer | Read raw blobs. | Storage data-plane access consistent with policy. | Storage Account or container. | If Shared Key is disabled, use Entra ID/RBAC data plane where applicable. | https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-manage#download-a-flow-log |
| CI/CD identity | Controlled plan/apply. | Same permissions as the deployer, plus role assignment permissions if managing RBAC. | Minimum scopes per environment. | Avoid permanent Owner; use approvals/PIM where possible. | https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/resources/role_assignment |
| Security/SOC reader | Investigate traffic and threats. | Reader on relevant resources and Log Analytics Reader on the workspace. | Workspace and observed resource groups. | Does not require write permissions on flow logs. | https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics#why-traffic-analytics |

For Traffic Analytics, Microsoft lists reads on NICs, NSGs, route tables, VNets, load balancers, public IPs, VMs, VMSS, workspace read/shared keys, and read/write/delete actions on DCR/DCE in the workspace's subscription. Additionally, permissions inherited from management groups are not supported for enabling Traffic Analytics. Source: https://learn.microsoft.com/en-us/azure/network-watcher/required-rbac-permissions#traffic-analytics

## Data Security, Encryption and Data Access

Flow logs are technical network data but may contain sensitive information about application behavior: source/destination IPs, ports, protocols, volumes, direction, and flow state. For this reason, this documentation treats them as operational evidence subject to access controls, retention policies, and data protection.

| Area | Recommended decision | Implication | Source |
| --- | --- | --- | --- |
| Raw log access | Use data-plane RBAC with Microsoft Entra ID where possible; avoid dependency on Shared Key. | In the lab `shared_access_key_enabled = false` requires `storage_use_azuread = true` in the `azurerm` provider for supported Storage operations. | https://learn.microsoft.com/en-us/azure/storage/blobs/authorize-access-azure-active-directory |
| Storage encryption | Leave Azure Storage at-rest encryption enabled. | Microsoft automatically encrypts data written to Storage; CMK and dedicated scopes are enterprise options if required. | https://learn.microsoft.com/en-us/azure/storage/common/storage-service-encryption |
| Log Analytics access | Separate who can read queries, who can administer the workspace, and who can modify alerts/workbooks. | Reduces the risk of excessive access to enriched network data. | https://learn.microsoft.com/en-us/azure/azure-monitor/logs/manage-access |
| Customer-managed keys | Consider CMK for workspaces or dedicated clusters only where the compliance requirement mandates it. | Increases governance and operational complexity; not required for the base demo. | https://learn.microsoft.com/en-us/azure/azure-monitor/logs/customer-managed-keys |
| Retention | Keep raw Storage retention and Log Analytics retention separate. | Raw Storage serves forensics; Log Analytics serves investigation and reporting. Policies may diverge. | https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-manage#create-a-flow-log |
| Blob manipulation | Do not edit, overwrite, or delete blocks while Azure is writing the hourly blobs. | Microsoft warns that modifying the block structure during ingestion can cause subsequent writes to that hourly blob to fail. | https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-manage#create-a-flow-log |
| `NWTA` resources | Do not manually modify DCR/DCE created by Traffic Analytics. | Traffic Analytics manages them; manual changes can break the pipeline. | https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-manage#enable-or-disable-traffic-analytics |

## Using VNet Flow Logs Without Traffic Analytics

| Feature | How to use | Value | Limitation | Source |
| --- | --- | --- | --- | --- |
| Raw JSON in Storage | Container `insights-logs-flowlogflowevent`, file `PT1H.json`. | Forensic evidence and audit. | Requires custom parsing. | https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-manage#download-a-flow-log |
| L4 flow tuples | Read timestamp, IPs, ports, protocol, direction, state, encryption, bytes, packets. | Understand who communicates with whom and at what volume. | Does not show application payload. | https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-overview#log-format |
| SIEM/IDS export | Export blobs to external tools. | Integration with existing security platform. | Enrichment is the customer's responsibility. | https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-overview#common-use-cases |
| Compliance | Retain raw evidence to verify isolation and enterprise rules. | Technical traceability. | Requires retention and access control. | https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-overview#common-use-cases |

### Scenario 1: Unexpected Internet Port

| Field | Content |
| --- | --- |
| Symptom | A workload communicates with unexpected public IPs. |
| Action | Download the `PT1H.json` blob for the relevant hour and filter tuples with a destination or source public IP. |
| Raw evidence | Source IP, destination IP, destination port, protocol, flow direction, flow state, bytes, packets. |
| Decision | Confirm whether the port is expected, then correct the NSG/route/firewall or application allowlist. |
| Source | https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-overview#log-format |

### Scenario 2: Application Cannot Reach the Database

| Field | Content |
| --- | --- |
| Symptom | App/client cannot connect to DB on TCP 5432. |
| Action | Generate or observe traffic, then look for tuples `10.20.x.x -> 10.30.2.10:5432`. |
| Raw evidence | Flow state `D` for deny or absence of return/consistent bytes. |
| Decision | Correlate with NSG effective rules or IP Flow Verify to confirm the rule. |
| Source | https://learn.microsoft.com/en-us/azure/network-watcher/ip-flow-verify-overview |

### Scenario 3: Private Endpoint Validation

| Field | Content |
| --- | --- |
| Symptom | The team wants to know if traffic to a PaaS service goes through the private endpoint. |
| Action | Capture flows from the source VM side; do not expect capture at the private endpoint itself. |
| Raw evidence | Destination IP equal to the private endpoint's private IP and source IP of the VM. |
| Decision | Correlate with private DNS and effective routes. |
| Source | https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-overview#private-endpoint-traffic |

## Using VNet Flow Logs With Traffic Analytics

| Feature | How to use | Value | Source |
| --- | --- | --- | --- |
| Traffic Analytics dashboard | Azure portal > Network Watcher > Traffic Analytics. | Hotspots, top talkers, top protocols, topology, public IP, NSG rule hits. | https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-usage-scenarios |
| KQL on `NTANetAnalytics` | Log Analytics workspace. | Queries for subnet, region, subscription, VM, load balancer, ExpressRoute, flow status. | https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-queries |
| KQL on `NTAIpDetails` | Log Analytics workspace. | WHOIS/location/threat for public and malicious flow IPs. | https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-schema#public-ip-details-schema |
| Custom alerts | Azure Monitor scheduled query rules. | Alert on deny spikes, anomalous egress, or malicious traffic. | https://learn.microsoft.com/en-us/azure/azure-monitor/alerts/alerts-create-log-alert-rule |
| Workbook | Azure Monitor Workbooks. | Custom dashboard shared with customer/NOC/SOC. | https://learn.microsoft.com/en-us/azure/azure-monitor/visualize/workbooks-overview |

The lab's KQL catalog is in [kql-catalog.md](kql-catalog.md).

### Scenario 1: Top Talkers and Capacity Anomaly

| Field | Content |
| --- | --- |
| Symptom | Sudden traffic increase or suspicious saturation between subnets. |
| Portal | Traffic Analytics dashboard > hotspots, top talkers, and frequent conversations. |
| KQL | Query 2 and Query 4 in [kql-catalog.md](kql-catalog.md). |
| Evidence | `TotalBytes`, `SrcIp`, `DestIp`, `DestPort`, `FlowType`, source/destination subnets. |
| Decision | Confirm whether traffic is expected, plan capacity, or correct unexpected communications. |
| Source | https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-usage-scenarios#find-traffic-hotspots |

### Scenario 2: Deny Spike or Incorrect NSG Rule

| Field | Content |
| --- | --- |
| Symptom | Application cannot reach DB or denied flows are increasing. |
| Portal | Traffic Analytics > NSG/NSG rules hits. |
| KQL | Query 3 in [kql-catalog.md](kql-catalog.md) or `Student/Resources/scenarios/scripts/run-kql.sh denied`. |
| Evidence | `FlowStatus == "Denied"` (full word, not `D`), `AclRule`, `AclGroup`, `SrcIp`, `DestIp`, `DestPort`. |
| Decision | Correct NSG priority/rule and validate with IP Flow Verify. |
| Source | https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-usage-scenarios#visualize-the-trends-in-network-security-group-nsgnsg-rules-hits |

### Scenario 3: Unexpected Public or Malicious Communication

| Field | Content |
| --- | --- |
| Symptom | VMs or subnets communicate with unauthorized public IPs. |
| Portal | Traffic Analytics > Public IP Information and geographic maps. |
| KQL | Query 5 and Query 6 in [kql-catalog.md](kql-catalog.md). |
| Evidence | `FlowType` `ExternalPublic`, `AzurePublic`, or `MaliciousFlow`; `NTAIpDetails` with `ThreatType`, `DNSDomain`, `Location`. |
| Decision | Block egress, open a security incident, update firewall/NSG/routes. |
| Source | https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-usage-scenarios#view-information-about-public-ips-interacting-with-your-deployment |

Smoke test KQL:

```kql
NTANetAnalytics
| where SubType == "FlowLog"
| take 10
```

Source: https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-queries

## Limitations

| Limitation | Impact | Mitigation | Source |
| --- | --- | --- | --- |
| Not a packet capture | Payload, application handshakes, or individual packets are not visible. | Use Packet Capture or application-layer tools when payload/packet-level analysis is required. | https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-overview#how-logging-works |
| Traffic Analytics aggregates data | Not all raw flows produce a 1:1 row in Log Analytics. | Use raw blobs for precise forensics and `NTANetAnalytics` for trends and fast troubleshooting. | https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-schema#data-aggregation |
| Visibility latency | Enriched data arrives after the 10/60-minute processing cycle plus ingestion time. | In demos generate traffic first and have smoke test/no-data queries ready. | https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-schema#data-aggregation |
| Possible duplicates | If logging is enabled on multiple sides of the same conversation, duplicate records may appear. | Use `FlowDirection` or `MACAddress` in queries. | https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-queries#prevent-duplicate-records |
| NIC/subnet/VNet scope precedence | Multiple configurations are not equivalent; NIC takes precedence over subnet, and subnet over VNet. | Define a scope standard to avoid surprises. | https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-manage#create-a-flow-log |
| Private Endpoint | Traffic is not recorded at the private endpoint itself. | Capture from the source VM side and correlate with private DNS/resource ID. | https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-overview#private-endpoint-traffic |
| Separate costs | Flow logs, Storage, Traffic Analytics, and Log Analytics have separate cost components. | Define retention, interval, and target scope before enabling. | https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-overview#pricing |

## Operational Pitfalls

| Pitfall | Symptom | Recommended action |
| --- | --- | --- |
| `Microsoft.Insights` not registered | Flow log creation fails or does not start. | Register the provider before deploying. |
| Network Watcher absent or incorrect name/RG | Terraform data source fails. | Verify `NetworkWatcher_<region>` and `NetworkWatcherRG`, or create the resource via Terraform. |
| Insufficient RBAC | 403 errors on Storage, workspace, flow logs, or Traffic Analytics. | Validate the IAM/RBAC matrix before the demo. |
| Data not immediately visible | Empty queries after generating traffic. | Wait for the TA interval, check raw blobs, and use the no-data query in [kql-catalog.md](kql-catalog.md). |
| Route fault not restored | Terraform plan shows drift on the route table. | Run `restore-*` and then `terraform plan -detailed-exitcode`. |
| NSG fault not restored | Persistent denies after the demo. | Run `restore-nsg-block.sh`, then IP Flow Verify. |
| Manual modification of `NWTA` DCR/DCE | Traffic Analytics stops processing. | Restore the Traffic Analytics configuration from the flow log; avoid manual management. |
| Storage shared with other lifecycle rules | Unexpected retention/lifecycle behavior. | Use Storage dedicated to flow logs. |

## Combined Value: Raw Logs + Traffic Analytics

| Dimension | Raw VNet Flow Logs | Traffic Analytics | Combined value | Source |
| --- | --- | --- | --- | --- |
| Fidelity | Raw JSON in blob. | Aggregated and enriched records. | Raw for forensics, TA for fast triage. | https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-schema#data-aggregation |
| Latency | Blobs collected at one-minute intervals. | 10 or 60-minute processing with ingestion delay. | Raw for point-in-time verification, TA for trends/dashboards. | https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-schema#data-aggregation |
| Usability | Requires custom parser/tools. | KQL, dashboards, workbooks. | Reduces troubleshooting time. | https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-queries |
| Security | No automatic enrichment. | IP details, geography, threat context. | Raw data + ready security signal. | https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-schema#public-ip-details-schema |
| Costs | Flow logs + Storage. | Flow logs + Storage + TA processing + Log Analytics. | Enable TA where it delivers operational value. | https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-overview#pricing |

## On-Demand Activation with Terraform

Objective: enable VNet Flow Logs and Traffic Analytics only on the environments, applications, and time windows where they are needed, reducing costs and operational noise.

| Layer | Strategy | Why | Source |
| --- | --- | --- | --- |
| Git | Folders per environment and `.tfvars` files per application. | Separates intents, approvals, and state. | https://developer.hashicorp.com/terraform/language/values/variables |
| Terraform module | Module `modules/vnet-flow-observability` with input `flow_log_targets`. | Reuse and selective enablement. | https://developer.hashicorp.com/terraform/language/modules |
| State | Separate backend/state per environment. | Reduces blast radius. | https://developer.hashicorp.com/terraform/language/state |
| Pipeline | `terraform plan` on PR, manual approval, `terraform apply` on merge or incident runbook. | Governance and audit trail. | https://developer.hashicorp.com/terraform/cli/commands/plan |
| Variables | `enable_vnet_flow_logs`, `enable_traffic_analytics`, `retention_days`, `interval_in_minutes`, `ttl`. | Explicit toggles and cost control. | https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/resources/network_watcher_flow_log |
| Tags | `environment`, `application`, `owner`, `costCenter`, `ttl`, `enabledReason`. | Chargeback and cleanup. | https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/resources/network_watcher_flow_log |

Recommended inputs:

```hcl
variable "enable_vnet_flow_logs" {
  type    = bool
  default = false
}

variable "enable_traffic_analytics" {
  type    = bool
  default = false
}

variable "flow_log_targets" {
  type = map(object({
    resource_id = string
    scope       = string
  }))
  default = {}
}

variable "traffic_analytics_interval_minutes" {
  type    = number
  default = 60
  validation {
    condition     = contains([10, 60], var.traffic_analytics_interval_minutes)
    error_message = "Use 10 or 60 minutes."
  }
}
```

`for_each` Pattern:

```hcl
locals {
  active_flow_log_targets = var.enable_vnet_flow_logs ? var.flow_log_targets : {}
}

resource "azurerm_network_watcher_flow_log" "target" {
  for_each = local.active_flow_log_targets

  network_watcher_name = data.azurerm_network_watcher.regional.name
  resource_group_name  = data.azurerm_network_watcher.regional.resource_group_name
  name                 = "fl-${var.environment}-${var.application}-${each.key}"

  target_resource_id = each.value.resource_id
  storage_account_id = azurerm_storage_account.flow_logs.id
  enabled            = true
  version            = 2

  retention_policy {
    enabled = true
    days    = var.flow_log_retention_days
  }

  dynamic "traffic_analytics" {
    for_each = var.enable_traffic_analytics ? [1] : []
    content {
      enabled               = true
      workspace_id          = azurerm_log_analytics_workspace.traffic.workspace_id
      workspace_region      = azurerm_log_analytics_workspace.traffic.location
      workspace_resource_id = azurerm_log_analytics_workspace.traffic.id
      interval_in_minutes   = var.traffic_analytics_interval_minutes
    }
  }
}
```

Sources: https://developer.hashicorp.com/terraform/language/meta-arguments/for_each, https://developer.hashicorp.com/terraform/language/expressions/dynamic-blocks, https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/resources/network_watcher_flow_log

| Approach | Effect | Pros | Cons | When to choose it | Source |
| --- | --- | --- | --- | --- | --- |
| `enabled = false` | Keeps the resource but stops collection. | Fast reactivation. | The resource remains present; watch for drift/policy. | Temporary pause or recurring troubleshooting. | https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-manage#disable-a-flow-log |
| `for_each = {}` | Terraform destroys the flow log resources. | Clean state and no active collection. | Recreation required; be aware of raw data already present. | Temporary activation with strict cost control. | https://developer.hashicorp.com/terraform/language/meta-arguments/for_each |
| Separate module | Observability deployable independently from the workload. | Better governance and blast radius. | Requires dedicated pipeline/state. | Recommended enterprise pattern. | https://developer.hashicorp.com/terraform/language/modules |

Recommendation: for enterprise environments, use a separate observability module, `for_each` on explicit targets, and an approval pipeline. Use `enabled = false` only when you need to keep the configuration ready for fast reactivation.

## Customer Meeting Checklist

| Check | Question | Evidence to have | Risk if missing | Source |
| --- | --- | --- | --- | --- |
| Subscription/tenant | Which subscription and tenant are we using? | Subscription ID, tenant, owner. | Deploying to the wrong scope. | https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-manage#prerequisites |
| Region | Does the region support VNet Flow Logs and Traffic Analytics? | Target region verified. | Feature not available. | https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-overview#availability |
| Provider | Is `Microsoft.Insights` registered? | `Registered` state. | Flow log creation failure. | https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-manage#register-insights-provider |
| Network Watcher | Does `NetworkWatcher_<region>` exist? | Network Watcher name/RG. | Terraform data source fails. | https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/data-sources/network_watcher |
| Target scope | VNet, subnet, or NIC? | List of resource IDs. | Too much noise or insufficient coverage. | https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-manage#create-a-flow-log |
| NSG Flow Logs | Are they active on the same workloads? | Inventory of existing flow logs. | Duplication/costs. | https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-overview#virtual-network-flow-logs-compared-to-network-security-group-flow-logs |
| Storage | Standard/StorageV2 Storage Account in the correct region? | Storage Account ID and policy. | Flow logs not written or policy conflict. | https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-overview#storage-account |
| Shared Key policy | Is Shared Key allowed or prohibited? | Azure Policy/security baseline. | Terraform Storage operation failure. | https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/resources/storage_account |
| Log Analytics | Which workspace are we using? | Workspace ID, region, retention, access. | Traffic Analytics not configurable or queryable. | https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics#key-components |
| DCR/DCE | Does the customer know TA creates `NWTA` resources? | Shared operational note. | Manual modification breaks Traffic Analytics. | https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-manage#enable-or-disable-traffic-analytics |
| RBAC | Who deploys and who reads? | Identity/role/scope matrix. | 403 errors or excessive access. | https://learn.microsoft.com/en-us/azure/network-watcher/required-rbac-permissions |
| Costs | Are retention and interval decided? | `flow_log_retention_days`, `log_analytics_retention_days`, interval 10/60. | Unexpected costs. | https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-overview#pricing |
| Ingestion time | Does the customer accept 10/60-minute latency? | Explicit expectation. | Demo perceived as non-functional. | https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-schema#data-aggregation |
| KQL access | Who can open Log Analytics? | Workspace access. | Unable to show evidence. | https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-queries#prerequisites |
| Test scenarios | Which issues are we simulating? | Traffic plan and time windows. | Weak evidence. | https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-usage-scenarios |
| Rollback | How do we disable or destroy? | Terraform plan, restore scripts, owner. | Residual costs and temporary configurations. | https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-manage#disable-a-flow-log |

## Lab Validation Commands

```bash
cd terraform
terraform validate
terraform plan
```

```bash
Student/Resources/scenarios/scripts/generate-baseline-traffic.sh
Student/Resources/scenarios/scripts/run-kql.sh top-talkers
Student/Resources/scenarios/scripts/run-kql.sh denied
```

```bash
Student/Resources/scenarios/scripts/trigger-nsg-block.sh
Student/Resources/scenarios/scripts/run-kql.sh denied
Student/Resources/scenarios/scripts/restore-nsg-block.sh
```

Repository references: [Student/Resources/scenarios/scripts/generate-baseline-traffic.sh](Student/Resources/scenarios/scripts/generate-baseline-traffic.sh), [Student/Resources/scenarios/scripts/run-kql.sh](Student/Resources/scenarios/scripts/run-kql.sh), [Student/Resources/scenarios/scripts/trigger-nsg-block.sh](Student/Resources/scenarios/scripts/trigger-nsg-block.sh), [Student/Resources/scenarios/scripts/restore-nsg-block.sh](Student/Resources/scenarios/scripts/restore-nsg-block.sh)

## Official Sources

| Topic | Source |
| --- | --- |
| VNet Flow Logs overview | https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-overview |
| VNet Flow Logs management | https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-manage |
| Traffic Analytics overview | https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics |
| Traffic Analytics schema | https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-schema |
| Traffic Analytics queries | https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-queries |
| Traffic Analytics usage scenarios | https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-usage-scenarios |
| Network Watcher RBAC | https://learn.microsoft.com/en-us/azure/network-watcher/required-rbac-permissions |
| Hub-spoke networking | https://learn.microsoft.com/en-us/azure/architecture/networking/architecture/hub-spoke |
| User-defined routes | https://learn.microsoft.com/en-us/azure/virtual-network/virtual-networks-udr-overview |
| Azure Firewall features by SKU | https://learn.microsoft.com/en-us/azure/firewall/features-by-sku |
| Terraform flow log resource | https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/resources/network_watcher_flow_log |
| Terraform Storage Account | https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/resources/storage_account |
| Terraform Log Analytics workspace | https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/resources/log_analytics_workspace |
| Terraform Network Watcher resource | https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/resources/network_watcher |
| Terraform Network Watcher data source | https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/data-sources/network_watcher |
| Terraform Azure Firewall | https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/resources/firewall |
| Terraform Firewall Policy | https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/resources/firewall_policy |
| Terraform Firewall Policy Rule Collection Group | https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/resources/firewall_policy_rule_collection_group |
| Terraform route | https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/resources/route |
| Terraform role assignment | https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/resources/role_assignment |

## Glossary

| Term | Definition |
| --- | --- |
| VNet Flow Logs | Azure Network Watcher feature that records IP traffic traversing a virtual network. |
| Traffic Analytics | Service that analyzes flow logs, aggregates them, enriches them, and publishes them to Log Analytics. |
| Network Watcher | Azure regional service for network monitoring and diagnostics. |
| Log Analytics workspace | Azure Monitor Logs workspace where log tables are stored and queried. |
| KQL | Kusto Query Language, the language for querying Azure Monitor Logs. |
| IAM | Identity and Access Management, the model for managing identities and access. |
| RBAC | Role-Based Access Control, Azure role-based authorization. |
| DCR | Data Collection Rule, an Azure Monitor rule for data collection. |
| DCE | Data Collection Endpoint, an Azure Monitor endpoint for data collection. |
| NSG | Network Security Group, a set of L3/L4 rules associated with a subnet or NIC. |
| UDR | User Defined Route, a custom route in an Azure route table. |
| Azure Firewall | Azure managed firewall used as a central next hop, with stateful filtering and outbound SNAT. |
| SNAT | Source Network Address Translation, translation of the source address used for Internet egress. |
| NVA | Network Virtual Appliance, a virtual appliance used for routing, firewall, or inspection. |
| SIEM | Security Information and Event Management, a security event correlation platform. |
| IDS | Intrusion Detection System, a system for detecting intrusions. |
| 5-tuple | Combination of source IP, destination IP, source port, destination port, and protocol. |
| Flow state | State of the flow, for example begin, continue, end, or deny. |
| Flow direction | Inbound/outbound direction relative to the capture point. |
| FlowStatus | Traffic Analytics field indicating allowed (`A`) or denied (`D`). |
| FlowType | Traffic Analytics classification, for example `IntraVNet`, `InterVNet`, `AzurePublic`, `ExternalPublic`, `MaliciousFlow`. |
| `NTANetAnalytics` | Log Analytics table with aggregated and enriched flow logs from Traffic Analytics. |
| `NTAIpDetails` | Log Analytics table with details on public IPs, geography, and threat information. |
