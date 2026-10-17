data "azurerm_client_config" "current" {}

locals {
  agent_tags = {
    workload   = "signalops"
    managed-by = "terraform"
  }
  agent_write_scopes = {
    hub    = module.workload.rg_hub_id
    app    = module.workload.rg_spoke_web_api_id
    data   = module.workload.rg_spoke_data_id
    food   = module.workload.rg_sample_food_id
    lisbon = "/subscriptions/${data.azurerm_client_config.current.subscription_id}/resourceGroups/${var.rg_parking_lisbon}"
    berlin = "/subscriptions/${data.azurerm_client_config.current.subscription_id}/resourceGroups/${var.rg_parking_berlin}"
    madrid = "/subscriptions/${data.azurerm_client_config.current.subscription_id}/resourceGroups/${var.rg_parking_madrid}"
    paris  = "/subscriptions/${data.azurerm_client_config.current.subscription_id}/resourceGroups/${var.rg_parking_paris}"
    chaos  = "/subscriptions/${data.azurerm_client_config.current.subscription_id}/resourceGroups/${var.rg_parking_chaos}"
  }
}

resource "azurerm_resource_group" "agent" {
  name     = var.rg_agent
  location = var.agent_location
  tags     = local.agent_tags
}

resource "azurerm_user_assigned_identity" "agent" {
  name                = "uai-${var.agent_name}"
  resource_group_name = azurerm_resource_group.agent.name
  location            = azurerm_resource_group.agent.location
  tags                = local.agent_tags
}

resource "azurerm_log_analytics_workspace" "agent" {
  name                         = "law-${var.agent_name}"
  resource_group_name          = azurerm_resource_group.agent.name
  location                     = azurerm_resource_group.agent.location
  sku                          = "PerGB2018"
  retention_in_days            = 30
  local_authentication_enabled = false
  tags                         = local.agent_tags
}

resource "azurerm_application_insights" "agent" {
  name                         = "appi-${var.agent_name}"
  resource_group_name          = azurerm_resource_group.agent.name
  location                     = azurerm_resource_group.agent.location
  application_type             = "web"
  workspace_id                 = azurerm_log_analytics_workspace.agent.id
  local_authentication_enabled = false
  tags                         = local.agent_tags
}

resource "azurerm_role_assignment" "agent_workload" {
  for_each                         = local.agent_write_scopes
  scope                            = each.value
  role_definition_name             = "Contributor"
  principal_id                     = azurerm_user_assigned_identity.agent.principal_id
  principal_type                   = "ServicePrincipal"
  skip_service_principal_aad_check = true
  depends_on                       = [module.workload]
}

resource "azurerm_role_assignment" "agent_monitoring" {
  scope                            = "/subscriptions/${data.azurerm_client_config.current.subscription_id}"
  role_definition_name             = "Monitoring Reader"
  principal_id                     = azurerm_user_assigned_identity.agent.principal_id
  principal_type                   = "ServicePrincipal"
  skip_service_principal_aad_check = true
}

resource "azurerm_role_assignment" "agent_logs" {
  scope                            = module.workload.log_analytics_workspace_id
  role_definition_name             = "Log Analytics Reader"
  principal_id                     = azurerm_user_assigned_identity.agent.principal_id
  principal_type                   = "ServicePrincipal"
  skip_service_principal_aad_check = true
}

resource "azurerm_role_assignment" "agent_telemetry_reader" {
  scope                            = azurerm_application_insights.agent.id
  role_definition_name             = "Monitoring Reader"
  principal_id                     = azurerm_user_assigned_identity.agent.principal_id
  principal_type                   = "ServicePrincipal"
  skip_service_principal_aad_check = true
}

resource "azurerm_role_assignment" "agent_telemetry_publisher" {
  scope                            = azurerm_application_insights.agent.id
  role_definition_name             = "Monitoring Metrics Publisher"
  principal_id                     = azurerm_user_assigned_identity.agent.principal_id
  principal_type                   = "ServicePrincipal"
  skip_service_principal_aad_check = true
}

resource "azapi_resource" "agent" {
  type                      = "Microsoft.App/agents@2026-01-01"
  name                      = var.agent_name
  parent_id                 = azurerm_resource_group.agent.id
  location                  = azurerm_resource_group.agent.location
  tags                      = local.agent_tags
  schema_validation_enabled = false

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.agent.id]
  }

  body = {
    properties = {
      actionConfiguration = {
        accessLevel = "High"
        identity    = azurerm_user_assigned_identity.agent.id
        mode        = "Review"
      }
      defaultModel = {
        name     = "claude-opus-4-6"
        provider = "Anthropic"
      }
      incidentManagementConfiguration = {
        type           = "AzMonitor"
        connectionName = "azmonitor"
      }
      knowledgeGraphConfiguration = {
        identity         = azurerm_user_assigned_identity.agent.id
        managedResources = module.workload.managed_resource_ids
      }
      logConfiguration = {
        applicationInsightsConfiguration = {
          appId = azurerm_application_insights.agent.app_id
        }
      }
      monthlyAgentUnitLimit = 500
      upgradeChannel        = "Stable"
    }
  }
  sensitive_body = {
    properties = {
      logConfiguration = {
        applicationInsightsConfiguration = {
          connectionString = azurerm_application_insights.agent.connection_string
        }
      }
    }
  }
  response_export_values = ["properties.agentEndpoint", "properties.provisioningState"]
  depends_on = [
    azurerm_role_assignment.agent_workload,
    azurerm_role_assignment.agent_monitoring,
    azurerm_role_assignment.agent_logs,
    azurerm_role_assignment.agent_telemetry_reader,
    azurerm_role_assignment.agent_telemetry_publisher,
  ]
}

resource "azurerm_role_assignment" "agent_operator" {
  scope                = azapi_resource.agent.id
  role_definition_name = "SRE Agent Administrator"
  principal_id         = data.azurerm_client_config.current.object_id
}

resource "azapi_resource" "agent_log_connector" {
  type      = "Microsoft.App/agents/connectors@2026-01-01"
  name      = "log-analytics"
  parent_id = azapi_resource.agent.id
  body = {
    properties = {
      dataConnectorType = "LogAnalytics"
      dataSource        = module.workload.log_analytics_workspace_id
      identity          = azurerm_user_assigned_identity.agent.id
    }
  }
}

resource "azapi_resource" "agent_insights_connector" {
  type      = "Microsoft.App/agents/connectors@2026-01-01"
  name      = "application-insights"
  parent_id = azapi_resource.agent.id
  body = {
    properties = {
      dataConnectorType = "AppInsights"
      dataSource        = azurerm_application_insights.agent.id
      identity          = azurerm_user_assigned_identity.agent.id
    }
  }
}
