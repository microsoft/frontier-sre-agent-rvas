# Deploy the SignalOps workload and agent. Complete-Lab.ps1 configures
# data-plane routing, knowledge, and the VM applications after apply.

data "azurerm_container_registry" "existing" {
  name                = var.container_registry_name
  resource_group_name = var.container_registry_resource_group
}

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

  container_registry_id           = data.azurerm_container_registry.existing.id
  container_registry_login_server = data.azurerm_container_registry.existing.login_server
  container_images                = var.container_images
  registry_pull_role              = var.registry_pull_role

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
