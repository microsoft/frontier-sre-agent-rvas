data "azurerm_client_config" "current" {}

module "workload" {
  source = "./modules/workload"

  providers = {
    azurerm = azurerm
    azapi   = azapi
    random  = random
  }

  location               = var.location
  rg_hub                 = var.rg_hub
  rg_spoke_web_api       = var.rg_spoke_web_api
  rg_spoke_data          = var.rg_spoke_data
  rg_sample_food         = var.rg_sample_food
  create_network_watcher = var.create_network_watcher

  vm_admin_username         = var.vm_admin_username
  vm_admin_password         = var.vm_admin_password
  deploy_madrid_vm          = var.deploy_madrid_vm
  deploy_paris_vm           = var.deploy_paris_vm
  create_parking_public_ips = var.create_parking_public_ips
  berlin_mcp_auth_token     = var.berlin_mcp_auth_token

  rg_parking_lisbon = var.rg_parking_lisbon
  rg_parking_berlin = var.rg_parking_berlin
  rg_parking_madrid = var.rg_parking_madrid
  rg_parking_paris  = var.rg_parking_paris
  rg_parking_chaos  = var.rg_parking_chaos
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
  managed_resource_ids = module.workload.managed_resource_ids

  # Feed the demo workspace ID into the Log Analytics connector.
  log_analytics_workspace_id = module.workload.log_analytics_workspace_id

  # Stable label => scope_id map drives the managed_scope for_each role assignments.
  # Labels must match the keys used before the module refactor to preserve state.
  managed_scopes = {
    "/subscriptions/${data.azurerm_client_config.current.subscription_id}" = "/subscriptions/${data.azurerm_client_config.current.subscription_id}"
    "hub-resource-group"                                                   = module.workload.rg_hub_id
    "web-api-resource-group"                                               = module.workload.rg_spoke_web_api_id
    "data-resource-group"                                                  = module.workload.rg_spoke_data_id
    "sample-food-resource-group"                                           = module.workload.rg_sample_food_id
    "demo-log-analytics"                                                   = module.workload.log_analytics_workspace_id
  }
}
