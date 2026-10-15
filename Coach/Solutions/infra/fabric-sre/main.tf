data "azurerm_client_config" "current" {}

resource "azurerm_resource_group" "workshop" {
  name     = var.resource_group_name
  location = var.agent_location
  tags = {
    workload   = "fabric-sre"
    managed-by = "terraform"
  }
}

resource "azapi_resource" "capacity" {
  type      = "Microsoft.Fabric/capacities@2023-11-01"
  name      = var.capacity_name
  parent_id = azurerm_resource_group.workshop.id
  location  = var.capacity_location
  tags      = azurerm_resource_group.workshop.tags

  body = {
    properties = {
      administration = {
        members = sort(tolist(var.capacity_admin_members))
      }
    }
    sku = {
      name = var.capacity_sku
      tier = "Fabric"
    }
  }
}

module "sre_agent" {
  source   = "../modules/sre_agent"
  for_each = var.teams

  agent_name                   = each.value.agent_name
  location                     = var.agent_location
  resource_group_name          = azurerm_resource_group.workshop.name
  resource_group_id            = azurerm_resource_group.workshop.id
  read_only                    = true
  enable_monitoring_connectors = false

  managed_resource_ids = [azapi_resource.capacity.id]
  managed_scopes = {
    capacity = azapi_resource.capacity.id
  }
}

locals {
  team_administrators = merge([
    for team_key, team in var.teams : {
      for principal_id in team.administrator_principal_ids :
      "${team_key}|${principal_id}" => {
        team_key     = team_key
        principal_id = principal_id
      } if lower(principal_id) != lower(data.azurerm_client_config.current.object_id)
    }
  ]...)
}

resource "azurerm_role_assignment" "participant_sre_agent_admin" {
  for_each = local.team_administrators

  scope                = module.sre_agent[each.value.team_key].agent_resource_id
  role_definition_name = "SRE Agent Administrator"
  principal_id         = each.value.principal_id
}
