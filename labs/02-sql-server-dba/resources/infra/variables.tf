variable "location" {
  description = "Azure region for all resources."
  type        = string
  default     = "swedencentral"
}

variable "resource_group_name" {
  description = "Name of the resource group that holds the SQL Server DBA lab resources."
  type        = string
  default     = "rg-sre-dba-rvas"
}

variable "sql_location" {
  description = "Region override for the Azure SQL server and database. Uses location when null."
  type        = string
  default     = null
}

variable "sql_client_ip_address" {
  description = "Public IPv4 address allowed through the Azure SQL firewall for running the setup scripts. No rule is created when null."
  type        = string
  default     = null
}

variable "sql_mcp_image" {
  description = "Container image for the read-only SQL Server MCP server."
  type        = string
  default     = "ghcr.io/microsoft/frontier-sre-agent-rvas/sql-server-mcp:latest"
}
