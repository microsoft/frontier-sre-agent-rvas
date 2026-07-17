provider "azurerm" {
  resource_provider_registrations = "core"
  storage_use_azuread             = true

  features {
    resource_group {
      # Force-delete resource groups even when they still contain Azure-auto-created
      # nested resources (Network Watcher Traffic Analytics DCE/DCR, default subnet
      # NSGs, App Insights smart-detector rules, ACA-managed NSGs). Those are created
      # out-of-band and would otherwise block RG deletion during the hub-spoke reorg.
      prevent_deletion_if_contains_resources = false
    }
  }
}

provider "azapi" {
  enable_preflight = false
}