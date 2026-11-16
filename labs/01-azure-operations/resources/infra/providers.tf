provider "azurerm" {
  resource_provider_registrations = "core"
  storage_use_azuread             = true

  features {
    resource_group {
      prevent_deletion_if_contains_resources = false
    }
  }
}

provider "azapi" {
  enable_preflight = false
}
