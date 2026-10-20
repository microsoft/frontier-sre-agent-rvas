terraform {
  required_version = ">= 1.5.0"

  required_providers {
    azapi = {
      source  = "Azure/azapi"
      version = "~> 2.10"
    }
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.76"
    }
  }
}

provider "azurerm" {
  resource_provider_registrations = "core"
  features {}
}

provider "azapi" {
  enable_preflight = true
}
