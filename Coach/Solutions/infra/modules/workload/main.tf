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
  tags     = local.demo_tags
}

resource "azurerm_resource_group" "spoke_web_api" {
  name     = var.rg_spoke_web_api
  location = var.location
  tags     = local.demo_tags
}

resource "azurerm_resource_group" "spoke_data" {
  name     = var.rg_spoke_data
  location = var.location
  tags     = local.demo_tags
}

# Network Watcher — set var.create_network_watcher=true to create; false (default) reads the existing one.
data "azurerm_network_watcher" "demo_existing" {
  count               = var.create_network_watcher ? 0 : 1
  name                = "NetworkWatcher_${var.location}"
  resource_group_name = "NetworkWatcherRG"
}

resource "azurerm_resource_group" "network_watcher" {
  count    = var.create_network_watcher ? 1 : 0
  name     = "NetworkWatcherRG"
  location = var.location
  tags     = local.demo_tags
}

resource "azurerm_network_watcher" "demo" {
  count               = var.create_network_watcher ? 1 : 0
  name                = "NetworkWatcher_${var.location}"
  location            = var.location
  resource_group_name = azurerm_resource_group.network_watcher[0].name
  tags                = local.demo_tags
}
