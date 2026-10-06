data "azurerm_client_config" "current" {}

# Random suffix shared by all globally-scoped resource names (storage account,
# Log Analytics workspace). Generated once and stored in state — stable across re-applies.
resource "random_string" "suffix" {
  length  = 6
  upper   = false
  special = false
}

resource "random_uuid" "demo_workbook" {}

# Single shared resource group for every workload resource. Each resource's
# pre-consolidation origin (hub, spoke_web_api, spoke_data, sample_food, and the
# parking resource groups) is preserved via the per-origin workload tag in
# local.origin_tags rather than via separate resource groups.
resource "azurerm_resource_group" "main" {
  name     = var.resource_group_name
  location = var.location
  tags     = merge(local.program_identity, { workload = "platform" })
}

# Network Watcher must already be enabled for the deployment region.
data "azurerm_network_watcher" "demo_existing" {
  name                = "NetworkWatcher_${var.location}"
  resource_group_name = "NetworkWatcherRG"
}
