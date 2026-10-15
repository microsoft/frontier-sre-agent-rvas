mock_provider "azurerm" {
  mock_resource "azurerm_resource_group" {
    defaults = {
      id = "/subscriptions/00000000-0000-0000-0000-000000000002/resourceGroups/rg-fabric-test"
    }
  }
  mock_resource "azurerm_log_analytics_workspace" {
    defaults = {
      id = "/subscriptions/00000000-0000-0000-0000-000000000002/resourceGroups/rg-fabric-test/providers/Microsoft.OperationalInsights/workspaces/mock-logs"
    }
  }
  mock_resource "azurerm_user_assigned_identity" {
    defaults = {
      id           = "/subscriptions/00000000-0000-0000-0000-000000000002/resourceGroups/rg-fabric-test/providers/Microsoft.ManagedIdentity/userAssignedIdentities/mock-identity"
      principal_id = "00000000-0000-0000-0000-000000000006"
      client_id    = "00000000-0000-0000-0000-000000000007"
    }
  }
  mock_data "azurerm_client_config" {
    defaults = {
      object_id       = "00000000-0000-0000-0000-000000000001"
      subscription_id = "00000000-0000-0000-0000-000000000002"
      tenant_id       = "00000000-0000-0000-0000-000000000003"
    }
  }
}

mock_provider "azapi" {
  mock_resource "azapi_resource" {
    defaults = {
      id = "/subscriptions/00000000-0000-0000-0000-000000000002/resourceGroups/rg-fabric-test/providers/Microsoft.App/agents/mock-agent"
    }
  }
}

variables {
  resource_group_name    = "rg-fabric-test"
  capacity_name          = "fabrictestcapacity"
  capacity_location      = "westeurope"
  capacity_admin_members = ["coach@example.com"]
  teams = {
    team01 = {
      agent_name = "fabric-team01"
      administrator_principal_ids = [
        "00000000-0000-0000-0000-000000000001",
        "00000000-0000-0000-0000-000000000004"
      ]
    }
    team02 = {
      agent_name                  = "fabric-team02"
      administrator_principal_ids = ["00000000-0000-0000-0000-000000000005"]
    }
  }
}

run "shared_capacity_and_team_access" {
  command = apply

  override_resource {
    target = module.sre_agent["team01"].azapi_resource.agent
    values = {
      id = "/subscriptions/00000000-0000-0000-0000-000000000002/resourceGroups/rg-fabric-test/providers/Microsoft.App/agents/fabric-team01"
    }
  }
  override_resource {
    target = module.sre_agent["team02"].azapi_resource.agent
    values = {
      id = "/subscriptions/00000000-0000-0000-0000-000000000002/resourceGroups/rg-fabric-test/providers/Microsoft.App/agents/fabric-team02"
    }
  }

  assert {
    condition     = azapi_resource.capacity.type == "Microsoft.Fabric/capacities@2023-11-01" && azapi_resource.capacity.body.sku.name == "F4"
    error_message = "The workshop must provision a shared Fabric F capacity."
  }
  assert {
    condition     = tolist(azapi_resource.capacity.body.properties.administration.members) == tolist(["coach@example.com"])
    error_message = "The capacity must name the coach as administrator."
  }
  assert {
    condition     = length(module.sre_agent) == 2 && length(azurerm_role_assignment.participant_sre_agent_admin) == 2
    error_message = "Provision one agent per team and participant grants without duplicating the deployer's grant."
  }
  assert {
    condition     = alltrue([for grant in azurerm_role_assignment.participant_sre_agent_admin : grant.role_definition_name == "SRE Agent Administrator"])
    error_message = "Every configuring participant/group must receive SRE Agent Administrator."
  }
  assert {
    condition     = alltrue([for key, grant in azurerm_role_assignment.participant_sre_agent_admin : grant.scope == module.sre_agent[local.team_administrators[key].team_key].agent_resource_id])
    error_message = "Participant access must be scoped to the assigned team's agent, not the subscription."
  }
}

run "reject_invalid_capacity_name" {
  command = plan
  variables {
    capacity_name = "invalid-capacity-name"
  }
  expect_failures = [var.capacity_name]
}

run "reject_empty_participant_access" {
  command = plan
  variables {
    teams = {
      team01 = {
        agent_name                  = "fabric-team01"
        administrator_principal_ids = []
      }
    }
  }
  expect_failures = [var.teams]
}

run "legacy_agent_defaults_preserved" {
  command = plan
  module {
    source = "../modules/sre_agent"
  }
  variables {
    resource_group_name        = "rg-agent-test"
    resource_group_id          = "/subscriptions/00000000-0000-0000-0000-000000000002/resourceGroups/rg-agent-test"
    managed_resource_ids       = []
    managed_scopes             = {}
    log_analytics_workspace_id = "/subscriptions/00000000-0000-0000-0000-000000000002/resourceGroups/rg-agent-test/providers/Microsoft.OperationalInsights/workspaces/demo"
  }
  assert {
    condition     = azapi_resource.agent.name == "contoso-sre-agent-dev" && azapi_resource.agent.body.properties.actionConfiguration.mode == "Autonomous"
    error_message = "Existing Azure Operations deployments must retain their agent name and autonomous mode."
  }
  assert {
    condition     = length(azurerm_role_assignment.subscription_contributor) == 1 && length(azurerm_role_assignment.subscription_monitoring_contributor) == 1
    error_message = "Existing Azure Operations permissions must remain unchanged."
  }
  assert {
    condition     = length(azapi_resource.log_analytics_connector) == 1 && length(azapi_resource.application_insights_connector) == 1
    error_message = "Existing Azure Operations deployments must retain their monitoring connectors."
  }
}

run "fabric_agent_read_only" {
  command = plan
  module {
    source = "../modules/sre_agent"
  }
  variables {
    agent_name                   = "fabric-team01"
    read_only                    = true
    enable_monitoring_connectors = false
    resource_group_name          = "rg-agent-test"
    resource_group_id            = "/subscriptions/00000000-0000-0000-0000-000000000002/resourceGroups/rg-agent-test"
    managed_resource_ids         = []
    managed_scopes = {
      capacity = "/subscriptions/00000000-0000-0000-0000-000000000002/resourceGroups/rg-agent-test/providers/Microsoft.Fabric/capacities/fabrictestcapacity"
    }
  }
  assert {
    condition     = azapi_resource.agent.name == "fabric-team01" && azapi_resource.agent.body.properties.actionConfiguration.mode == "ReadOnly" && azapi_resource.agent.body.properties.actionConfiguration.accessLevel == "Low"
    error_message = "Fabric agents must use the team name and low-access ReadOnly mode."
  }
  assert {
    condition     = length(azurerm_role_assignment.subscription_contributor) == 0 && length(azurerm_role_assignment.subscription_monitoring_contributor) == 0
    error_message = "Fabric agent identities must not receive subscription-level write grants."
  }
  assert {
    condition     = length(azurerm_role_assignment.managed_scope) == 3 && alltrue([for grant in azurerm_role_assignment.managed_scope : contains(["Reader", "Log Analytics Reader", "Monitoring Reader"], grant.role_definition_name)])
    error_message = "Fabric managed-scope grants must be limited to read roles."
  }
  assert {
    condition     = length(azapi_resource.log_analytics_connector) == 0 && length(azapi_resource.application_insights_connector) == 0
    error_message = "Fabric deployments must not create unconfigured Azure Operations connectors."
  }
}
