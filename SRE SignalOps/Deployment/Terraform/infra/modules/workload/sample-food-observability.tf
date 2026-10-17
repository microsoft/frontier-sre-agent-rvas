resource "azurerm_application_insights" "sample_food" {
  name                = local.sample_food_names.app_insights
  location            = azurerm_resource_group.sample_food.location
  resource_group_name = azurerm_resource_group.sample_food.name
  application_type    = "web"
  workspace_id        = azurerm_log_analytics_workspace.demo.id
  tags                = local.sample_food_tags
}

resource "azurerm_monitor_diagnostic_setting" "sample_food_container_apps_environment" {
  name                           = local.sample_food_names.diagnostic_setting
  target_resource_id             = azurerm_container_app_environment.sample_food.id
  log_analytics_workspace_id     = azurerm_log_analytics_workspace.demo.id
  log_analytics_destination_type = "Dedicated"

  enabled_log {
    category = "ContainerAppConsoleLogs"
  }

  enabled_log {
    category = "ContainerAppSystemLogs"
  }

  enabled_log {
    category = "ContainerAppHTTPLogs"
  }

  enabled_metric {
    category = "AllMetrics"
  }

  lifecycle {
    ignore_changes = [log_analytics_destination_type]
  }
}

# The Grubify title matches the approval-gated sample-food-http-errors plan.
# Requests filtered to 5xx supplies the platform metric incident signal.
resource "azurerm_monitor_action_group" "sample_food" {
  name                = "ag-food"
  resource_group_name = azurerm_resource_group.sample_food.name
  short_name          = "SREFoodAG"
  tags                = local.sample_food_tags
}

resource "azurerm_monitor_metric_alert" "sample_food_http_5xx" {
  name                = local.sample_food_names.http_5xx_alert
  resource_group_name = azurerm_resource_group.sample_food.name
  scopes              = [azurerm_container_app.sample_food_api.id]
  description         = "Alert when the Sample Food Ordering App API returns HTTP 5xx errors; triggers SRE Agent investigation."
  severity            = 1
  enabled             = true
  frequency           = "PT1M"
  # Fire ASAP: PT1M is the minimum aggregation window for metric alerts and matches
  # the PT1M evaluation frequency, so the SRE Agent picks up the incident as early as
  # the platform allows. Container Apps platform metrics still carry ~3 min export
  # latency (metrics DB < 1 min, +3 min to the data collection endpoint), which is
  # the practical detection floor regardless of this window.
  window_size = "PT1M"
  tags        = local.sample_food_tags
  # Metric alerts auto-resolve by default (auto_mitigate defaults to true); declare it
  # explicitly so the auto-resolve intent is recorded and not left to an implicit default.
  auto_mitigate = true

  criteria {
    metric_namespace = "microsoft.app/containerapps"
    metric_name      = "Requests"
    aggregation      = "Total"
    operator         = "GreaterThan"
    # Threshold 0 (GreaterThan) = fire on the FIRST 5xx in the 1-minute window, the
    # most aggressive count setting for fastest SRE Agent pickup. Acceptable here
    # because faults are generated deliberately in the demo; for production raise
    # this so a single transient 5xx (cold start, deploy blip) does not open a Sev1.
    threshold = 0

    dimension {
      name     = "statusCodeCategory"
      operator = "Include"
      values   = ["5xx"]
    }
  }

  action {
    action_group_id = azurerm_monitor_action_group.sample_food.id
  }
}