variable "location" {
  description = "Azure region for the SQL MCP Container Apps resources"
  type        = string
}

variable "sql_location" {
  description = "Azure region for the Azure SQL server and database. Defaults to location when null"
  type        = string
  default     = null
}

variable "resource_group_name" {
  description = "Resource group name for the SQL Server DBA track resources"
  type        = string
  default     = "rg-sre-dba"
}

variable "log_analytics_workspace_id" {
  description = "Log Analytics workspace resource ID that receives Container Apps environment logs"
  type        = string
}

variable "sql_mcp_image" {
  description = "Container image for the read-only SQL Server MCP server"
  type        = string
  default     = "ghcr.io/microsoft/frontier-sre-agent-rvas/sql-server-mcp:latest"
}

variable "sql_database_name" {
  description = "Name of the sample workshop database"
  type        = string
  default     = "stockOrders"
}

variable "sql_database_sku_name" {
  description = "SKU for the sample workshop database"
  type        = string
  default     = "S1"
}

variable "sql_entra_admin_login" {
  description = "Display name for the Microsoft Entra administrator of the Azure SQL server. Defaults to sre-dba-sql-admin when null"
  type        = string
  default     = null
}

variable "sql_entra_admin_object_id" {
  description = "Object ID of the Microsoft Entra administrator of the Azure SQL server. Defaults to the deploying principal when null"
  type        = string
  default     = null
}

variable "sql_client_ip_address" {
  description = "Public IPv4 address allowed through the Azure SQL firewall for running the setup scripts. No client rule is created when null"
  type        = string
  default     = null
}

variable "tags" {
  description = "Tags applied to every SQL Server DBA track resource"
  type        = map(string)
  default     = {}
}
