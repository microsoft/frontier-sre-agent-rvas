data "azurerm_client_config" "current" {}

module "workload" {
  source = "./modules/workload"

  providers = {
    azurerm = azurerm
    azapi   = azapi
    random  = random
  }

  location         = var.location
  rg_hub           = var.rg_hub
  rg_spoke_web_api = var.rg_spoke_web_api
  rg_spoke_data    = var.rg_spoke_data
  rg_sample_food   = var.rg_sample_food

  vm_admin_username         = var.vm_admin_username
  vm_admin_password         = var.vm_admin_password
  deploy_madrid_vm          = var.deploy_madrid_vm
  deploy_paris_vm           = var.deploy_paris_vm
  create_parking_public_ips = var.create_parking_public_ips
  berlin_mcp_auth_token     = var.berlin_mcp_auth_token

  rg_parking_lisbon   = var.rg_parking_lisbon
  rg_parking_berlin   = var.rg_parking_berlin
  rg_parking_madrid   = var.rg_parking_madrid
  rg_parking_paris    = var.rg_parking_paris
  rg_parking_chaos    = var.rg_parking_chaos
  rg_parking_frontend = var.rg_parking_frontend
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
  resource_group_name        = var.rg_sre_dba
  log_analytics_workspace_id = module.workload.log_analytics_workspace_id
  sql_mcp_image              = var.sre_dba_sql_mcp_image
  sql_client_ip_address      = var.sre_dba_sql_client_ip_address

  tags = {
    workload        = "azure-sre-agent"
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

  location = var.location
  rg_agent = var.rg_agent

  # Feed workload resource IDs into the agent's knowledge graph.
  managed_resource_ids = concat(
    module.workload.managed_resource_ids,
    flatten(module.sre_dba_infra[*].managed_resource_ids)
  )

  # Feed the demo workspace ID into the Log Analytics connector.
  log_analytics_workspace_id = module.workload.log_analytics_workspace_id

  # Stable label => scope_id map drives the managed_scope for_each role assignments.
  # Labels must match the keys used before the module refactor to preserve state.
  managed_scopes = merge({
    "/subscriptions/${data.azurerm_client_config.current.subscription_id}" = "/subscriptions/${data.azurerm_client_config.current.subscription_id}"
    "hub-resource-group"                                                   = module.workload.rg_hub_id
    "web-api-resource-group"                                               = module.workload.rg_spoke_web_api_id
    "data-resource-group"                                                  = module.workload.rg_spoke_data_id
    "sample-food-resource-group"                                           = module.workload.rg_sample_food_id
    "parking-lisbon-resource-group"                                        = module.workload.rg_parking_lisbon_id
    "parking-berlin-resource-group"                                        = module.workload.rg_parking_berlin_id
    "parking-madrid-resource-group"                                        = module.workload.rg_parking_madrid_id
    "parking-paris-resource-group"                                         = module.workload.rg_parking_paris_id
    "parking-chaos-resource-group"                                         = module.workload.rg_parking_chaos_id
    "parking-frontend-resource-group"                                      = module.workload.rg_parking_frontend_id
    "demo-log-analytics"                                                   = module.workload.log_analytics_workspace_id
    },
    { for id in module.sre_dba_infra[*].resource_group_id : "sre-dba-resource-group" => id }
  )
}
