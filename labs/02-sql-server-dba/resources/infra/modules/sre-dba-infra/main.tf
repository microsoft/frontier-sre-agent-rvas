data "azurerm_client_config" "current" {}

resource "random_string" "suffix" {
  length  = 6
  upper   = false
  special = false
}

# Workload identity used by the MCP container to authenticate to Azure SQL.
# Database access is granted separately by sql/07_add_ca_mcp_managed_identity.sql.
resource "azurerm_user_assigned_identity" "sql_mcp" {
  name                = local.names.managed_identity
  location            = var.location
  resource_group_name = var.resource_group_name
  tags                = local.resource_tags
}
