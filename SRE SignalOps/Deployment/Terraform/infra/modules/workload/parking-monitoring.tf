# ─── Data Collection Endpoint (shared by VM log collection DCRs) ──────────────

resource "azurerm_monitor_data_collection_endpoint" "parking_vms" {
  name                = "dce-parking-vm-logs"
  resource_group_name = azurerm_resource_group.hub.name
  location            = azurerm_resource_group.hub.location
  kind                = "Linux"
  tags                = local.resource_tags

  lifecycle {
    create_before_destroy = true
  }
}

# ─── DCR: Madrid — Windows Event Log collection ────────────────────────────────

resource "azurerm_monitor_data_collection_rule" "madrid_windows_events" {
  count = var.deploy_madrid_vm ? 1 : 0

  name                        = "dcr-madrid-windows-events"
  resource_group_name         = azurerm_resource_group.hub.name
  location                    = azurerm_resource_group.hub.location
  data_collection_endpoint_id = azurerm_monitor_data_collection_endpoint.parking_vms.id
  tags                        = local.resource_tags

  data_sources {
    windows_event_log {
      name    = "madrid-windows-events"
      streams = ["Microsoft-Event"]
      x_path_queries = [
        "Application!*[System[*]]",
        "System!*[System[(Level=1 or Level=2 or Level=3)]]",
        "Security!*[System[(Level=1 or Level=2 or Level=3)]]",
      ]
    }
  }

  destinations {
    log_analytics {
      name                  = "la-madrid-windows-events"
      workspace_resource_id = azurerm_log_analytics_workspace.demo.id
    }
  }

  data_flow {
    streams      = ["Microsoft-Event"]
    destinations = ["la-madrid-windows-events"]
  }
}

resource "azurerm_monitor_data_collection_rule_association" "madrid" {
  count = var.deploy_madrid_vm ? 1 : 0

  name                    = "assoc-madrid-windows-events"
  target_resource_id      = azurerm_windows_virtual_machine.madrid[0].id
  data_collection_rule_id = azurerm_monitor_data_collection_rule.madrid_windows_events[0].id
  description             = "Collect Madrid Windows Event Viewer logs to Log Analytics"
}

# ─── DCR: Paris — Linux syslog collection ─────────────────────────────────────

resource "azurerm_monitor_data_collection_rule" "paris_syslog" {
  count = var.deploy_paris_vm ? 1 : 0

  name                        = "dcr-paris-syslog"
  resource_group_name         = azurerm_resource_group.hub.name
  location                    = azurerm_resource_group.hub.location
  data_collection_endpoint_id = azurerm_monitor_data_collection_endpoint.parking_vms.id
  tags                        = local.resource_tags

  data_sources {
    syslog {
      name    = "paris-linux-syslog"
      streams = ["Microsoft-Syslog"]
      facility_names = [
        "auth", "authpriv", "cron", "daemon", "kern",
        "local0", "local1", "local2", "local3", "local4",
        "local5", "local6", "local7", "syslog", "user",
      ]
      log_levels = [
        "Emergency", "Alert", "Critical", "Error",
        "Warning", "Notice", "Info", "Debug",
      ]
    }
  }

  destinations {
    log_analytics {
      name                  = "la-paris-syslog"
      workspace_resource_id = azurerm_log_analytics_workspace.demo.id
    }
  }

  data_flow {
    streams      = ["Microsoft-Syslog"]
    destinations = ["la-paris-syslog"]
  }
}

resource "azurerm_monitor_data_collection_rule_association" "paris" {
  count = var.deploy_paris_vm ? 1 : 0

  name                    = "assoc-paris-syslog"
  target_resource_id      = azurerm_linux_virtual_machine.paris[0].id
  data_collection_rule_id = azurerm_monitor_data_collection_rule.paris_syslog[0].id
  description             = "Collect Paris Linux syslog logs to Log Analytics"
}

# ─── DCE + DCR: VM Health Status custom table (for VM Health Control service) ──

resource "azurerm_monitor_data_collection_endpoint" "vm_health" {
  name                = "dce-vm-health-status"
  resource_group_name = azurerm_resource_group.parking_chaos.name
  location            = azurerm_resource_group.parking_chaos.location
  tags                = local.resource_tags

  lifecycle {
    create_before_destroy = true
  }
}

# The custom table must exist in the workspace before the DCR can reference it
# as an output stream. Azure does not auto-create it from the DCR stream declaration.
resource "azapi_resource" "vm_health_table" {
  type      = "Microsoft.OperationalInsights/workspaces/tables@2022-10-01"
  name      = "VMHealthStatus_CL"
  parent_id = azurerm_log_analytics_workspace.demo.id

  body = {
    properties = {
      schema = {
        name = "VMHealthStatus_CL"
        columns = [
          { name = "TimeGenerated", type = "datetime" },
          { name = "vmName", type = "string" },
          { name = "city", type = "string" },
          { name = "healthState", type = "string" },
          { name = "previousState", type = "string" },
          { name = "severity", type = "string" },
          { name = "source", type = "string" },
          { name = "message", type = "string" },
          { name = "resourceGroup", type = "string" },
          { name = "subscriptionId", type = "string" },
          { name = "resourceType", type = "string" },
        ]
      }
      retentionInDays = 30
      plan            = "Analytics"
    }
  }
}

resource "azurerm_monitor_data_collection_rule" "vm_health_status" {
  name                        = "dcr-vm-health-status"
  resource_group_name         = azurerm_resource_group.parking_chaos.name
  location                    = azurerm_resource_group.parking_chaos.location
  data_collection_endpoint_id = azurerm_monitor_data_collection_endpoint.vm_health.id
  tags                        = local.resource_tags

  depends_on = [azapi_resource.vm_health_table]

  stream_declaration {
    stream_name = "Custom-VMHealthStatus_CL"

    column {
      name = "TimeGenerated"
      type = "datetime"
    }

    column {
      name = "vmName"
      type = "string"
    }

    column {
      name = "city"
      type = "string"
    }

    column {
      name = "healthState"
      type = "string"
    }

    column {
      name = "previousState"
      type = "string"
    }

    column {
      name = "severity"
      type = "string"
    }

    column {
      name = "source"
      type = "string"
    }

    column {
      name = "message"
      type = "string"
    }

    column {
      name = "resourceGroup"
      type = "string"
    }

    column {
      name = "subscriptionId"
      type = "string"
    }

    column {
      name = "resourceType"
      type = "string"
    }
  }

  destinations {
    log_analytics {
      name                  = "la-vm-health"
      workspace_resource_id = azurerm_log_analytics_workspace.demo.id
    }
  }

  data_flow {
    streams       = ["Custom-VMHealthStatus_CL"]
    destinations  = ["la-vm-health"]
    output_stream = "Custom-VMHealthStatus_CL"
    transform_kql = "source"
  }
}

# Monitoring Metrics Publisher role on the DCR so the vm-health-control
# container app can ingest VMHealthStatus_CL log entries.
resource "azurerm_role_assignment" "vm_health_metrics_publisher" {
  scope                            = azurerm_monitor_data_collection_rule.vm_health_status.id
  role_definition_name             = "Monitoring Metrics Publisher"
  principal_id                     = azurerm_container_app.vm_health_control.identity[0].principal_id
  principal_type                   = "ServicePrincipal"
  skip_service_principal_aad_check = true
}
