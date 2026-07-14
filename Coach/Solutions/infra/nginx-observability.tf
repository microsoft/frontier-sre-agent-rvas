# NGINX service-down observability for the web tier, powering the "NGINX Service
# Down" Azure SRE Agent demo scenario.
#
# Flow: Azure Monitor Agent (AMA) on the web VMs -> Syslog Data Collection Rule
# -> demo Log Analytics workspace -> scheduled query alert that fires when the
# nginx systemd unit is stopped/deactivated/failed. The alert is Sev2, so it lands
# in the web-tier-nginx incident filter band (titleContains nginx) and is handled
# by the iaas-vm-incident-handler subagent for autonomous in-guest restart.
#
# Sources:
# - AMA install via VM extension: https://learn.microsoft.com/en-us/azure/azure-monitor/agents/azure-monitor-agent-manage
# - Data Collection Rule overview: https://learn.microsoft.com/en-us/azure/azure-monitor/essentials/data-collection-rule-overview
# - Log search alert rules: https://learn.microsoft.com/en-us/azure/azure-monitor/alerts/alerts-create-log-alert-rule

resource "azurerm_monitor_data_collection_rule" "web_syslog" {
  name                = "dcr-web-syslog"
  resource_group_name = azurerm_resource_group.spoke_web_api.name
  location            = azurerm_resource_group.spoke_web_api.location
  tags                = local.demo_tags

  destinations {
    log_analytics {
      workspace_resource_id = azurerm_log_analytics_workspace.demo.id
      name                  = "law-demo"
    }
  }

  data_sources {
    syslog {
      name           = "syslog-all"
      facility_names = ["*"]
      log_levels     = ["*"]
      streams        = ["Microsoft-Syslog"]
    }
  }

  data_flow {
    streams      = ["Microsoft-Syslog"]
    destinations = ["law-demo"]
  }
}

resource "azurerm_virtual_machine_extension" "web_ama" {
  count = 2

  name                       = "AzureMonitorLinuxAgent"
  virtual_machine_id         = azurerm_linux_virtual_machine.web[count.index].id
  publisher                  = "Microsoft.Azure.Monitor"
  type                       = "AzureMonitorLinuxAgent"
  type_handler_version       = "1.0"
  auto_upgrade_minor_version = true
  automatic_upgrade_enabled  = true
  tags                       = local.demo_tags
}

resource "azurerm_monitor_data_collection_rule_association" "web_syslog" {
  count = 2

  name                    = "dcra-web-${count.index + 1}-syslog"
  target_resource_id      = azurerm_linux_virtual_machine.web[count.index].id
  data_collection_rule_id = azurerm_monitor_data_collection_rule.web_syslog.id

  depends_on = [azurerm_virtual_machine_extension.web_ama]
}

resource "azurerm_monitor_scheduled_query_rules_alert_v2" "nginx_down" {
  name                    = "alert-nginx-down"
  resource_group_name     = azurerm_resource_group.spoke_web_api.name
  location                = azurerm_resource_group.spoke_web_api.location
  display_name            = "NGINX service down on web tier"
  description             = "Fires when the nginx systemd unit is stopped, deactivated, or fails on a web-tier VM, based on Syslog collected by Azure Monitor Agent. Routes (Sev2, web-tier-nginx filter) to the SRE Agent iaas-vm-incident-handler subagent for autonomous in-guest restart."
  enabled                 = true
  severity                = 2
  scopes                  = [azurerm_log_analytics_workspace.demo.id]
  evaluation_frequency    = "PT1M"
  window_duration         = "PT10M"
  skip_query_validation   = true
  tags                    = local.demo_tags
  auto_mitigation_enabled = true
  criteria {
    query                   = <<-KQL
      Syslog
      | where TimeGenerated > ago(10m)
      | where ProcessName == "systemd"
      | where SyslogMessage has "nginx"
      | where SyslogMessage has_any ("Stopped", "Deactivated", "Failed", "failed")
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
