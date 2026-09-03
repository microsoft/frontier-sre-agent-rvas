resource "azurerm_storage_account" "flow_logs" {
  name                            = substr("${local.demo_suffix}flow", 0, 24)
  resource_group_name             = azurerm_resource_group.hub.name
  location                        = azurerm_resource_group.hub.location
  account_tier                    = "Standard"
  account_replication_type        = "LRS"
  account_kind                    = "StorageV2"
  https_traffic_only_enabled      = true
  min_tls_version                 = "TLS1_2"
  allow_nested_items_to_be_public = false
  public_network_access_enabled   = false
  shared_access_key_enabled = false
  tags                      = local.resource_tags

  # Keep the firewall default-deny and retain the trusted-service exception used by
  # Microsoft.Network to write and analyze flow logs when public access is disabled.
  network_rules {
    default_action = "Deny"
    bypass         = ["AzureServices"]

    private_link_access {
      endpoint_resource_id = "/subscriptions/${data.azurerm_client_config.current.subscription_id}/providers/Microsoft.Security/datascanners/storageDataScanner"
      endpoint_tenant_id   = data.azurerm_client_config.current.tenant_id
    }
  }

  blob_properties {
    delete_retention_policy {
      days = 7
    }
  }
}

resource "azurerm_log_analytics_workspace" "demo" {
  name                = "law-${local.demo_suffix}"
  location            = azurerm_resource_group.hub.location
  resource_group_name = azurerm_resource_group.hub.name
  sku                 = "PerGB2018"
  retention_in_days   = 30
  tags                = local.resource_tags
}

resource "azurerm_network_watcher_flow_log" "vnet" {
  for_each = {
    hub        = azurerm_virtual_network.hub.id
    spoke-app  = azurerm_virtual_network.spoke_app.id
    spoke-data = azurerm_virtual_network.spoke_data.id
  }

  network_watcher_name = local.demo_network_watcher_name
  resource_group_name  = local.demo_network_watcher_rg
  name                 = "fl-${each.key}"
  location             = azurerm_resource_group.hub.location

  target_resource_id = each.value
  storage_account_id = azurerm_storage_account.flow_logs.id
  enabled            = true
  version            = 2
  tags               = local.resource_tags

  retention_policy {
    enabled = true
    days    = 7
  }

  traffic_analytics {
    enabled               = true
    workspace_id          = azurerm_log_analytics_workspace.demo.workspace_id
    workspace_region      = azurerm_log_analytics_workspace.demo.location
    workspace_resource_id = azurerm_log_analytics_workspace.demo.id
    interval_in_minutes   = 10
  }
}

resource "azurerm_application_insights_workbook" "traffic_analytics" {
  name                = random_uuid.demo_workbook.result
  resource_group_name = azurerm_resource_group.hub.name
  location            = azurerm_resource_group.hub.location
  display_name        = "VNet Flow Logs and Traffic Analytics Demo"
  description         = "Curated workbook for the VNet Flow Logs and Traffic Analytics customer demo."
  tags                = local.resource_tags

  data_json = jsonencode({
    version = "Notebook/1.0"
    items = [
      {
        type = 1
        name = "overview"
        content = {
          json = "# VNet Flow Logs + Traffic Analytics Demo\nUse this workbook to show top talkers, denied flows, internet exposure, and troubleshooting signals from NTANetAnalytics."
        }
      },
      {
        type = 3
        name = "flow-types"
        content = {
          version                 = "KqlItem/1.0"
          query                   = <<-KQL
            NTANetAnalytics
            | where SubType == "FlowLog" and TimeGenerated > ago(24h)
            | summarize Flows=sum(AllowedInFlows + DeniedInFlows + AllowedOutFlows + DeniedOutFlows), Bytes=sum(BytesSrcToDest + BytesDestToSrc) by FlowType, FlowStatus
            | order by Bytes desc
          KQL
          size                    = 1
          title                   = "Flow types and status"
          queryType               = 0
          resourceType            = "microsoft.operationalinsights/workspaces"
          crossComponentResources = [azurerm_log_analytics_workspace.demo.id]
          visualization           = "table"
        }
      },
      {
        type = 3
        name = "denied-flows"
        content = {
          version                 = "KqlItem/1.0"
          query                   = <<-KQL
            NTANetAnalytics
            | where SubType == "FlowLog" and TimeGenerated > ago(24h)
            | where FlowStatus contains "Denied" or DeniedInFlows > 0 or DeniedOutFlows > 0
            | summarize DeniedFlows=sum(DeniedInFlows + DeniedOutFlows) by AclRule, SrcIp, DestIp, DestPort, L4Protocol
            | order by DeniedFlows desc
          KQL
          size                    = 1
          title                   = "Denied flows by rule and endpoint"
          queryType               = 0
          resourceType            = "microsoft.operationalinsights/workspaces"
          crossComponentResources = [azurerm_log_analytics_workspace.demo.id]
          visualization           = "table"
        }
      },
      {
        type = 3
        name = "top-talkers"
        content = {
          version                 = "KqlItem/1.0"
          query                   = <<-KQL
            NTANetAnalytics
            | where SubType == "FlowLog" and TimeGenerated > ago(24h)
            | summarize TotalBytes=sum(BytesSrcToDest + BytesDestToSrc) by SrcIp, DestIp, DestPort, L4Protocol
            | top 20 by TotalBytes desc
          KQL
          size                    = 1
          title                   = "Top conversations"
          queryType               = 0
          resourceType            = "microsoft.operationalinsights/workspaces"
          crossComponentResources = [azurerm_log_analytics_workspace.demo.id]
          visualization           = "table"
        }
      }
    ]
    isLocked            = false
    fallbackResourceIds = [azurerm_log_analytics_workspace.demo.id]
  })
}

resource "azurerm_monitor_scheduled_query_rules_alert_v2" "denied_flow_spike" {
  name                = "alert-denied-flow-spike"
  resource_group_name = azurerm_resource_group.hub.name
  location            = azurerm_resource_group.hub.location
  display_name        = "Denied VNet flow spike"
  description         = "Demo alert that fires when denied flows are observed in Traffic Analytics data."
  enabled             = true
  severity            = 2
  scopes              = [azurerm_log_analytics_workspace.demo.id]
  # Fire ASAP: evaluate every minute so a denied-flow spike is detected within ~1 min
  # of the data landing, instead of up to 5 min. window_duration MUST stay >= the
  # Traffic Analytics processing interval (interval_in_minutes = 10 on the flow log):
  # NTANetAnalytics is written in ~10-min batches, so a shorter window would usually
  # see no rows and the alert would never fire. The 10-min Traffic Analytics batch is
  # the real detection floor here, not the alert cadence.
  evaluation_frequency  = "PT1M"
  window_duration       = "PT10M"
  skip_query_validation = true
  tags                  = local.resource_tags
  # Auto-resolve the incident once denied flows stop appearing in the evaluation
  # window, so the demo shows the full detect -> remediate -> resolve lifecycle.
  # (v2 alerts default this to false, so it must be set explicitly to enable it.)
  auto_mitigation_enabled = true

  criteria {
    # NTANetAnalytics decorates the flow status as the full word "Denied"/"Allowed"
    # (live-certified), NOT the single letter "D"/"A" that the Traffic Analytics schema
    # doc still lists. Match the word OR the numeric denied counters so a single denied
    # flow is enough to fire (inclusive OR; FlowStatus == "D" would never match and the
    # alert would never fire).
    query                   = <<-KQL
      NTANetAnalytics
      | where SubType == "FlowLog" and TimeGenerated > ago(10m)
      | where FlowStatus contains "Denied" or DeniedInFlows > 0 or DeniedOutFlows > 0
    KQL
    time_aggregation_method = "Count"
    threshold               = 0
    operator                = "GreaterThan"

    failing_periods {
      minimum_failing_periods_to_trigger_alert = 1
      number_of_evaluation_periods             = 1
    }
  }
}
