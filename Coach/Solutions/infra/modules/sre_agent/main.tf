data "azurerm_client_config" "current" {}

resource "azurerm_user_assigned_identity" "agent" {
  name                = "uai-${var.agent_name}"
  location            = var.location
  resource_group_name = var.resource_group_name
  tags                = local.resource_tags
}

resource "azurerm_log_analytics_workspace" "agent" {
  name                         = "law-${var.agent_name}"
  location                     = var.location
  resource_group_name          = var.resource_group_name
  sku                          = "PerGB2018"
  retention_in_days            = 30
  local_authentication_enabled = false
  tags                         = local.resource_tags
}

resource "azurerm_application_insights" "agent" {
  name                         = "appi-${var.agent_name}"
  location                     = var.location
  resource_group_name          = var.resource_group_name
  application_type             = "web"
  workspace_id                 = azurerm_log_analytics_workspace.agent.id
  local_authentication_enabled = false
  tags                         = local.resource_tags
}

resource "azapi_resource" "agent" {
  type                      = "Microsoft.App/agents@2026-01-01"
  name                      = var.agent_name
  parent_id                 = var.resource_group_id
  location                  = var.location
  tags                      = local.resource_tags
  ignore_null_property      = true
  schema_validation_enabled = false

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.agent.id]
  }

  body = {
    properties = {
      actionConfiguration = {
        accessLevel = var.read_only ? "Low" : "High"
        identity    = azurerm_user_assigned_identity.agent.id
        mode        = var.read_only ? "ReadOnly" : "Autonomous"
      }

      defaultModel = var.default_model

      incidentManagementConfiguration = {
        type           = "AzMonitor"
        connectionName = "azmonitor"
      }

      knowledgeGraphConfiguration = {
        identity         = azurerm_user_assigned_identity.agent.id
        managedResources = var.managed_resource_ids
      }

      logConfiguration = {
        applicationInsightsConfiguration = {
          appId = azurerm_application_insights.agent.app_id
        }
      }

      monthlyAgentUnitLimit = 1500
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

  response_export_values = [
    "properties.agentEndpoint",
    "properties.outboundIpAddresses",
    "properties.powerState",
    "properties.provisioningState"
  ]
}

resource "azapi_resource" "log_analytics_connector" {
  count = var.enable_monitoring_connectors ? 1 : 0

  type                      = "Microsoft.App/agents/connectors@2026-01-01"
  name                      = "log-analytics"
  parent_id                 = azapi_resource.agent.id
  ignore_null_property      = true
  schema_validation_enabled = false

  body = {
    properties = {
      dataConnectorType = "LogAnalytics"
      dataSource        = var.log_analytics_workspace_id
      identity          = azurerm_user_assigned_identity.agent.id
    }
  }

  lifecycle {
    precondition {
      condition     = var.log_analytics_workspace_id != null
      error_message = "log_analytics_workspace_id is required when monitoring connectors are enabled."
    }
  }
}

resource "azapi_resource" "application_insights_connector" {
  count = var.enable_monitoring_connectors ? 1 : 0

  type                      = "Microsoft.App/agents/connectors@2026-01-01"
  name                      = "application-insights"
  parent_id                 = azapi_resource.agent.id
  ignore_null_property      = true
  schema_validation_enabled = false

  body = {
    properties = {
      dataConnectorType = "AppInsights"
      dataSource        = azurerm_application_insights.agent.id
      identity          = azurerm_user_assigned_identity.agent.id
    }
  }
}

resource "azurerm_role_assignment" "managed_scope" {
  for_each = local.managed_scope_role_assignments

  scope                            = each.value.scope
  role_definition_name             = each.value.role
  principal_id                     = azurerm_user_assigned_identity.agent.principal_id
  principal_type                   = "ServicePrincipal"
  skip_service_principal_aad_check = true
}

resource "azurerm_role_assignment" "subscription_monitoring_contributor" {
  count = var.read_only ? 0 : 1

  scope                            = "/subscriptions/${data.azurerm_client_config.current.subscription_id}"
  role_definition_name             = "Monitoring Contributor"
  principal_id                     = azurerm_user_assigned_identity.agent.principal_id
  principal_type                   = "ServicePrincipal"
  skip_service_principal_aad_check = true
}

resource "azurerm_role_assignment" "subscription_contributor" {
  count = var.read_only ? 0 : 1

  scope                            = "/subscriptions/${data.azurerm_client_config.current.subscription_id}"
  role_definition_name             = "Contributor"
  principal_id                     = azurerm_user_assigned_identity.agent.principal_id
  principal_type                   = "ServicePrincipal"
  skip_service_principal_aad_check = true
}

resource "azurerm_role_assignment" "current_user_sre_agent_admin" {
  scope                = azapi_resource.agent.id
  role_definition_name = "SRE Agent Administrator"
  principal_id         = data.azurerm_client_config.current.object_id
}

moved {
  from = azurerm_role_assignment.subscription_monitoring_contributor
  to   = azurerm_role_assignment.subscription_monitoring_contributor[0]
}

moved {
  from = azurerm_role_assignment.subscription_contributor
  to   = azurerm_role_assignment.subscription_contributor[0]
}

moved {
  from = azapi_resource.log_analytics_connector
  to   = azapi_resource.log_analytics_connector[0]
}

moved {
  from = azapi_resource.application_insights_connector
  to   = azapi_resource.application_insights_connector[0]
}
