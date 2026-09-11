data "azurerm_client_config" "current" {}

# Random suffix shared by all globally-scoped resource names (storage account,
# Log Analytics workspace). Generated once and stored in state — stable across re-applies.
resource "random_string" "suffix" {
  length  = 6
  upper   = false
  special = false
}

resource "random_uuid" "demo_workbook" {}

# Hub-spoke resource groups. The hub holds connectivity resources (Firewall, Bastion,
# shared observability) while each spoke gets its own RG for isolation.
resource "azurerm_resource_group" "hub" {
  name     = var.rg_hub
  location = var.location
  tags     = local.resource_tags
}

resource "azurerm_resource_group" "spoke_web_api" {
  name     = var.rg_spoke_web_api
  location = var.location
  tags     = local.resource_tags
}

resource "azurerm_resource_group" "spoke_data" {
  name     = var.rg_spoke_data
  location = var.location
  tags     = local.resource_tags
}

# Network Watcher must already be enabled for the deployment region.
data "azurerm_network_watcher" "demo_existing" {
  name                = "NetworkWatcher_${var.location}"
  resource_group_name = "NetworkWatcherRG"
}
