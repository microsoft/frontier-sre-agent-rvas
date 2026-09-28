# Microsoft Entra-only authentication: no SQL administrator password exists.
resource "azurerm_mssql_server" "main" {
  name                          = local.names.sql_server
  location                      = local.sql_location
  resource_group_name           = azurerm_resource_group.main.name
  version                       = "12.0"
  minimum_tls_version           = "1.2"
  public_network_access_enabled = true
  tags                          = local.resource_tags

  azuread_administrator {
    login_username              = local.sql_entra_admin_login
    object_id                   = local.sql_entra_admin_object_id
    tenant_id                   = data.azurerm_client_config.current.tenant_id
    azuread_authentication_only = true
  }

  # Server identity used to resolve Microsoft Entra principals during
  # CREATE USER ... FROM EXTERNAL PROVIDER.
  identity {
    type = "SystemAssigned"
  }
}

resource "azurerm_mssql_database" "main" {
  name           = var.sql_database_name
  server_id      = azurerm_mssql_server.main.id
  sku_name       = var.sql_database_sku_name
  max_size_gb    = 10
  collation      = "SQL_Latin1_General_CP1_CI_AS"
  zone_redundant = false
  tags           = local.resource_tags
}

# Container Apps without VNet integration has no fixed outbound address, so
# Azure services are allowed through the server firewall.
resource "azurerm_mssql_firewall_rule" "azure_services" {
  name             = "AllowAzureServices"
  server_id        = azurerm_mssql_server.main.id
  start_ip_address = "0.0.0.0"
  end_ip_address   = "0.0.0.0"
}

resource "azurerm_mssql_firewall_rule" "client" {
  count = var.sql_client_ip_address == null ? 0 : 1

  name             = "AllowSetupClient"
  server_id        = azurerm_mssql_server.main.id
  start_ip_address = var.sql_client_ip_address
  end_ip_address   = var.sql_client_ip_address
}
