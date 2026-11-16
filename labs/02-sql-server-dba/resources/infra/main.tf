locals {
  tags = {
    workload        = "sre-dba"
    program         = "azure-sre-agent"
    managed-by      = "terraform"
    SecurityControl = "Ignore"
  }
}

resource "azurerm_resource_group" "main" {
  name     = var.resource_group_name
  location = var.location
  tags     = local.tags
}

# Container Apps logs go here so the SRE Agent can query them.
resource "azurerm_log_analytics_workspace" "main" {
  name                = "log-sre-dba"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  sku                 = "PerGB2018"
  retention_in_days   = 30
  tags                = local.tags
}

module "sre_dba_infra" {
  source = "./modules/sre-dba-infra"

  providers = {
    azurerm = azurerm
    random  = random
  }

  location                   = var.location
  sql_location               = var.sql_location
  resource_group_name        = azurerm_resource_group.main.name
  resource_group_id          = azurerm_resource_group.main.id
  log_analytics_workspace_id = azurerm_log_analytics_workspace.main.id
  sql_mcp_image              = var.sql_mcp_image
  sql_client_ip_address      = var.sql_client_ip_address
  tags                       = local.tags
}
