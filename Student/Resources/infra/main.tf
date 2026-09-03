# Deploy the workload — the hub-spoke network, demo VMs, Sample Food (Grubify)
# app, and the Parking app. This is the infrastructure the Azure SRE Agent will
# observe and manage.
#
# The Azure SRE Agent itself is deliberately not declared here. Creating it is the
# participant's job in Challenge 00, and it starts empty: skills, knowledge,
# subagents and connectors are added from Challenge 01 onwards. Record the agent's
# resource group and name in Student/.env so the make targets can reach it.

module "workload" {
  source = "../../../Coach/Solutions/infra/modules/workload"

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
