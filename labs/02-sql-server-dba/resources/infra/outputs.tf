output "resource_group_name" {
  value = azurerm_resource_group.main.name
}

output "log_analytics_workspace_id" {
  value = azurerm_log_analytics_workspace.main.id
}

output "sql_mcp_url" {
  value = module.sre_dba_infra.sql_mcp_url
}

output "sql_mcp_health_url" {
  value = module.sre_dba_infra.sql_mcp_health_url
}

output "sql_mcp_container_app_name" {
  value = module.sre_dba_infra.sql_mcp_container_app_name
}

output "sql_mcp_identity_name" {
  value = module.sre_dba_infra.sql_mcp_identity_name
}

output "sql_mcp_identity_client_id" {
  value = module.sre_dba_infra.sql_mcp_identity_client_id
}

output "sql_mcp_identity_principal_id" {
  value = module.sre_dba_infra.sql_mcp_identity_principal_id
}

output "sql_server_name" {
  value = module.sre_dba_infra.sql_server_name
}

output "sql_server_fqdn" {
  value = module.sre_dba_infra.sql_server_fqdn
}

output "sql_database_name" {
  value = module.sre_dba_infra.sql_database_name
}
