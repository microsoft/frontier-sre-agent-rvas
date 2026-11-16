locals {
  resource_tags = merge(
    var.tags,
    {
      component = "sql-server-dba-track"
      lab       = "sre-agent-dba"
    }
  )

  sql_location = coalesce(var.sql_location, var.location)

  names = {
    managed_identity           = "id-sre-dba-sql-mcp"
    container_apps_environment = "cae-sre-dba"
    container_app              = "ca-sre-dba-sql-mcp"
    # Azure SQL server names are globally unique DNS labels.
    sql_server = "sql-sre-dba-${random_string.suffix.result}"
  }

  sql_entra_admin_login     = coalesce(var.sql_entra_admin_login, "sre-dba-sql-admin")
  sql_entra_admin_object_id = coalesce(var.sql_entra_admin_object_id, data.azurerm_client_config.current.object_id)

  # Passwordless profile validated by the MCP managed-identity connection policy.
  sql_mcp_connection_string = join("", [
    "Server=tcp:${azurerm_mssql_server.main.fully_qualified_domain_name},1433;",
    "Database=${azurerm_mssql_database.main.name};",
    "Authentication=Active Directory Managed Identity;",
    "User Id=${azurerm_user_assigned_identity.sql_mcp.client_id};",
    "Encrypt=True;",
    "TrustServerCertificate=False;",
  ])
}
