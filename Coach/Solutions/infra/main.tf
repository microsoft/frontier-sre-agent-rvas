data "azurerm_client_config" "current" {}

module "workload" {
  source = "./modules/workload"

  providers = {
    azurerm = azurerm
    azapi   = azapi
    random  = random
  }

  location            = var.location
  resource_group_name = var.resource_group_name

  vm_admin_username         = var.vm_admin_username
  vm_admin_password         = var.vm_admin_password
  deploy_madrid_vm          = var.deploy_madrid_vm
  deploy_paris_vm           = var.deploy_paris_vm
  create_parking_public_ips = var.create_parking_public_ips
  berlin_mcp_auth_token     = var.berlin_mcp_auth_token
}

# SQL Server DBA track: SQL MCP Container App and sample Azure SQL database.
module "sre_dba_infra" {
  source = "./modules/workload/sre-dba-infra"
  count  = var.deploy_sre_dba_infra ? 1 : 0

  providers = {
    azurerm = azurerm
    random  = random
  }

  location                   = var.location
  sql_location               = var.sre_dba_sql_location
  resource_group_name        = module.workload.resource_group_name
  resource_group_id          = module.workload.resource_group_id
  log_analytics_workspace_id = module.workload.log_analytics_workspace_id
  sql_mcp_image              = var.sre_dba_sql_mcp_image
  sql_client_ip_address      = var.sre_dba_sql_client_ip_address

  tags = {
    workload        = "sre-dba"
    program         = "azure-sre-agent"
    managed-by      = "terraform"
    SecurityControl = "Ignore"
  }
}

module "sre_agent" {
  source = "./modules/sre_agent"

  providers = {
    azurerm = azurerm
    azapi   = azapi
  }

  location            = var.location
  resource_group_name = module.workload.resource_group_name
  resource_group_id   = module.workload.resource_group_id

  # Feed workload resource IDs into the agent's knowledge graph.
  managed_resource_ids = concat(
    module.workload.managed_resource_ids,
    flatten(module.sre_dba_infra[*].managed_resource_ids)
  )

  # Feed the demo workspace ID into the Log Analytics connector.
  log_analytics_workspace_id = module.workload.log_analytics_workspace_id

  # Stable label => scope_id map drives the managed_scope for_each role assignments.
  # Every workload/sre-dba resource-group output now resolves to the same shared
  # resource group, so a single label covers all of them without duplicating
  # role assignments for the same principal/role/scope.
  managed_scopes = {
    "/subscriptions/${data.azurerm_client_config.current.subscription_id}" = "/subscriptions/${data.azurerm_client_config.current.subscription_id}"
    "workload-resource-group"                                              = module.workload.resource_group_id
    "demo-log-analytics"                                                   = module.workload.log_analytics_workspace_id
  }
}
