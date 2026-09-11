# Lisbon sends custom logs through the Log Analytics Data Collector API. The
# table is created when the first record arrives, so query validation is skipped
# to allow the alerts and the application to be deployed together.

resource "azurerm_monitor_action_group" "lisbon_chaos" {
  name                = "ag-lisbon-chaos"
  resource_group_name = azurerm_resource_group.parking_lisbon.name
  short_name          = "LisbonChaos"
  tags                = local.resource_tags
}

locals {
  lisbon_fault_alerts = {
    http-error = {
      fault_type = "httpError"
      severity   = 0
    }
    dependency-failure = {
      fault_type = "dependencyFailure"
      severity   = 2
    }
    https-error = {
      fault_type = "httpsError"
      severity   = 2
    }
    exception = {
      fault_type = "exception"
      severity   = 1
    }
    disconnect = {
      fault_type = "disconnect"
      severity   = 2
    }
    timeout = {
      fault_type = "timeout"
      severity   = 2
    }
    bad-payload = {
      fault_type = "badPayload"
      severity   = 2
    }
    high-cpu = {
      fault_type = "highCpu"
      severity   = 2
    }
    high-memory = {
      fault_type = "highMemory"
      severity   = 2
    }
  }

  lisbon_signal_alerts = {
    latency-performance = {
      description = "Lisbon parking API response time exceeded 1500 ms."
      query       = <<-KQL
        union isfuzzy=true LisbonParkingLogs_CL, (datatable(TimeGenerated:datetime)[])
        | extend operation = tostring(coalesce(column_ifexists('operation_s', ''), column_ifexists('operation', '')))
        | extend responseTimeMs = todouble(coalesce(column_ifexists('responseTimeMs_d', real(null)), column_ifexists('responseTimeMs', real(null))))
        | where operation == 'HTTP_RESPONSE' and isnotnull(responseTimeMs)
        | where responseTimeMs > 1500
      KQL
    }
    high-memory-guard-429 = {
      description = "Lisbon parking API returned HTTP 429 from the high-memory safety guard."
      query       = <<-KQL
        union isfuzzy=true LisbonParkingLogs_CL, (datatable(TimeGenerated:datetime)[])
        | extend operation = tostring(coalesce(column_ifexists('operation_s', ''), column_ifexists('operation', '')))
        | extend statusCode = coalesce(toint(column_ifexists('statusCode_d', real(null))), toint(column_ifexists('statusCode', int(null))))
        | where operation == 'HTTP_RESPONSE' and statusCode == 429
      KQL
    }
  }
}

resource "azurerm_monitor_scheduled_query_rules_alert_v2" "lisbon_chaos_generic" {
  name                    = "lisbon-chaos-generic"
  resource_group_name     = azurerm_resource_group.parking_lisbon.name
  location                = azurerm_resource_group.parking_lisbon.location
  display_name            = "Lisbon chaos injection detected"
  description             = "A chaos fault was injected into the Lisbon parking API."
  enabled                 = true
  severity                = 3
  scopes                  = [azurerm_log_analytics_workspace.demo.id]
  evaluation_frequency    = "PT5M"
  window_duration         = "PT5M"
  skip_query_validation   = true
  auto_mitigation_enabled = true
  tags                    = local.resource_tags

  criteria {
    query                   = <<-KQL
      union isfuzzy=true LisbonParkingLogs_CL, (datatable(TimeGenerated:datetime)[])
      | extend operation = tostring(coalesce(column_ifexists('operation_s', ''), column_ifexists('operation', '')))
      | where operation == 'CHAOS_INJECTED'
    KQL
    time_aggregation_method = "Count"
    threshold               = 0
    operator                = "GreaterThan"

    failing_periods {
      minimum_failing_periods_to_trigger_alert = 1
      number_of_evaluation_periods             = 1
    }
  }

  action {
    action_groups = [azurerm_monitor_action_group.lisbon_chaos.id]
  }
}

resource "azurerm_monitor_scheduled_query_rules_alert_v2" "lisbon_chaos_fault" {
  for_each = local.lisbon_fault_alerts

  name                    = "lisbon-chaos-${each.key}"
  resource_group_name     = azurerm_resource_group.parking_lisbon.name
  location                = azurerm_resource_group.parking_lisbon.location
  display_name            = "Lisbon chaos ${each.key} detected"
  description             = "The ${each.value.fault_type} chaos fault was injected into the Lisbon parking API."
  enabled                 = true
  severity                = each.value.severity
  scopes                  = [azurerm_log_analytics_workspace.demo.id]
  evaluation_frequency    = "PT5M"
  window_duration         = "PT5M"
  skip_query_validation   = true
  auto_mitigation_enabled = true
  tags                    = local.resource_tags

  criteria {
    query                   = <<-KQL
      union isfuzzy=true LisbonParkingLogs_CL, (datatable(TimeGenerated:datetime)[])
      | extend operation = tostring(coalesce(column_ifexists('operation_s', ''), column_ifexists('operation', '')))
      | extend faultType = tostring(coalesce(column_ifexists('details_faultType_s', ''), column_ifexists('details_faultType', '')))
      | where operation == 'CHAOS_INJECTED' and faultType == '${each.value.fault_type}'
    KQL
    time_aggregation_method = "Count"
    threshold               = 0
    operator                = "GreaterThan"

    failing_periods {
      minimum_failing_periods_to_trigger_alert = 1
      number_of_evaluation_periods             = 1
    }
  }

  action {
    action_groups = [azurerm_monitor_action_group.lisbon_chaos.id]
  }
}

resource "azurerm_monitor_scheduled_query_rules_alert_v2" "lisbon_signal" {
  for_each = local.lisbon_signal_alerts

  name                    = "lisbon-chaos-${each.key}"
  resource_group_name     = azurerm_resource_group.parking_lisbon.name
  location                = azurerm_resource_group.parking_lisbon.location
  display_name            = "Lisbon chaos ${each.key} detected"
  description             = each.value.description
  enabled                 = true
  severity                = 2
  scopes                  = [azurerm_log_analytics_workspace.demo.id]
  evaluation_frequency    = "PT5M"
  window_duration         = "PT5M"
  skip_query_validation   = true
  auto_mitigation_enabled = true
  tags                    = local.resource_tags

  criteria {
    query                   = each.value.query
    time_aggregation_method = "Count"
    threshold               = 0
    operator                = "GreaterThan"

    failing_periods {
      minimum_failing_periods_to_trigger_alert = 1
      number_of_evaluation_periods             = 1
    }
  }

  action {
    action_groups = [azurerm_monitor_action_group.lisbon_chaos.id]
  }
}
