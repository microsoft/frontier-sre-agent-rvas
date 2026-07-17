data "azurerm_client_config" "current" {}

resource "azurerm_resource_group" "agent" {
  name     = var.rg_agent
  location = var.location
  tags     = local.resource_tags
}

resource "azurerm_user_assigned_identity" "agent" {
  name                = "uai-contoso-sre-agent-dev"
  location            = azurerm_resource_group.agent.location
  resource_group_name = azurerm_resource_group.agent.name
  tags                = local.resource_tags
}

resource "azurerm_log_analytics_workspace" "agent" {
  name                         = "law-contoso-sre-agent-dev"
  location                     = azurerm_resource_group.agent.location
  resource_group_name          = azurerm_resource_group.agent.name
  sku                          = "PerGB2018"
  retention_in_days            = 30
  local_authentication_enabled = false
  tags                         = local.resource_tags
}

resource "azurerm_application_insights" "agent" {
  name                         = "appi-contoso-sre-agent-dev"
  location                     = azurerm_resource_group.agent.location
  resource_group_name          = azurerm_resource_group.agent.name
  application_type             = "web"
  workspace_id                 = azurerm_log_analytics_workspace.agent.id
  local_authentication_enabled = false
  tags                         = local.resource_tags
}

resource "azapi_resource" "agent" {
  type                      = "Microsoft.App/agents@2026-01-01"
  name                      = "contoso-sre-agent-dev"
  parent_id                 = azurerm_resource_group.agent.id
  location                  = azurerm_resource_group.agent.location
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
        accessLevel = "High"
        identity    = azurerm_user_assigned_identity.agent.id
        mode        = "Autonomous"
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
        managedResources = var.managed_resource_ids
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

  response_export_values = [
    "properties.agentEndpoint",
    "properties.outboundIpAddresses",
    "properties.powerState",
    "properties.provisioningState"
  ]
}

resource "azapi_resource" "log_analytics_connector" {
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
}

resource "azapi_resource" "application_insights_connector" {
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
  scope                            = "/subscriptions/${data.azurerm_client_config.current.subscription_id}"
  role_definition_name             = "Monitoring Contributor"
  principal_id                     = azurerm_user_assigned_identity.agent.principal_id
  principal_type                   = "ServicePrincipal"
  skip_service_principal_aad_check = true
}

resource "azurerm_role_assignment" "subscription_contributor" {
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
