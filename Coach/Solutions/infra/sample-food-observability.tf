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

# HTTP 5xx alert + Action Group imported from the original Grubify lab
# (dm-chelupati/sre-agent-lab: infra/modules/alert-rules.bicep). The lab uses a
# single platform metric alert on the Container App "Requests" metric filtered to
# statusCodeCategory 5xx, plus a minimal Action Group, and states "a single alert
# keeps things clean". We adopt that faithful mechanism (PT1M/PT5M, near real time)
# in place of the previous log-query alert. The ONLY deliberate deviation is the
# severity: kept at 1 (not the lab's 3) so the alert stays in the Sev1 incident
# filter band owned by the Sample Food / Grubify ACA app domain. Domain-routing
# rule (2026-06-14): the sample-food-http-errors plan matches titleContains "food"
# (the alert name "alert-food-http-5xx") and routes to the
# aca-app-incident-handler subagent (renamed 2026-06-14 from incident-handler).
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