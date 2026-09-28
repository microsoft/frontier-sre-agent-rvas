output "resource_group_name" {
  description = "Resource group name for the SQL Server DBA track resources"
  value       = azurerm_resource_group.main.name
}

output "resource_group_id" {
  description = "Resource group ID for the SQL Server DBA track resources"
  value       = azurerm_resource_group.main.id
}

output "managed_resource_ids" {
  description = "Resource IDs added to the Azure SRE Agent knowledge graph"
  value = [
    azurerm_container_app_environment.main.id,
    azurerm_container_app.sql_mcp.id,
    azurerm_mssql_server.main.id,
    azurerm_mssql_database.main.id,
  ]
}

output "container_apps_environment_name" {
  description = "Container Apps environment hosting the SQL MCP server"
  value       = azurerm_container_app_environment.main.name
}

output "sql_mcp_container_app_name" {
  description = "Container App name for the SQL MCP server"
  value       = azurerm_container_app.sql_mcp.name
}

output "sql_mcp_url" {
  description = "Streamable HTTP endpoint for the SQL MCP server"
  value       = "https://${azurerm_container_app.sql_mcp.ingress[0].fqdn}/mcp"
}

output "sql_mcp_health_url" {
  description = "Liveness endpoint for the SQL MCP server"
  value       = "https://${azurerm_container_app.sql_mcp.ingress[0].fqdn}/healthz"
}

output "sql_mcp_identity_name" {
  description = "Managed identity display name to map in sql/07_add_ca_mcp_managed_identity.sql"
  value       = azurerm_user_assigned_identity.sql_mcp.name
}

output "sql_mcp_identity_client_id" {
  description = "Client ID of the SQL MCP managed identity"
  value       = azurerm_user_assigned_identity.sql_mcp.client_id
}

output "sql_mcp_identity_principal_id" {
  description = "Object (principal) ID of the SQL MCP managed identity"
  value       = azurerm_user_assigned_identity.sql_mcp.principal_id
}

output "sql_server_name" {
  description = "Azure SQL logical server name"
  value       = azurerm_mssql_server.main.name
}

output "sql_server_fqdn" {
  description = "Azure SQL logical server fully qualified domain name"
  value       = azurerm_mssql_server.main.fully_qualified_domain_name
}

output "sql_database_name" {
  description = "Sample workshop database name"
  value       = azurerm_mssql_database.main.name
}
