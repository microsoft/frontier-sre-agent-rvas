variable "location" {
  description = "Azure region for all resources."
  type        = string
  default     = "swedencentral"
}

variable "resource_group_name" {
  description = "Name of the single shared resource group used by every workload, SRE Agent, and SQL DBA track resource."
  type        = string
  default     = "rg-sre-agent-rvas"
}

# ─── Parking App ───────────────────────────────────────────────────────────────

variable "vm_admin_username" {
  description = "Admin username for the parking app VMs (Madrid and Paris)."
  type        = string
  default     = "azureadmin"
}

variable "vm_admin_password" {
  description = "Admin password supplied at runtime for all lab VMs."
  type        = string
  sensitive   = true
  default     = "Change-Me-Before-Deploy-123!"
}

variable "deploy_madrid_vm" {
  description = "Set to true to deploy the Madrid Windows Server VM and its extensions."
  type        = bool
  default     = true
}

variable "deploy_paris_vm" {
  description = "Set to true to deploy the Paris Ubuntu Server VM and its extensions."
  type        = bool
  default     = true
}

variable "create_parking_public_ips" {
  description = "Create Standard public IPs for the Madrid and Paris VMs. Useful for direct SSH/RDP access in dev/test; set to false in production."
  type        = bool
  default     = false
}

variable "berlin_mcp_auth_token" {
  description = "MCP auth token for the Berlin MCP server. Leave empty to disable authentication (dev/lab use only)."
  type        = string
  sensitive   = true
  default     = ""
}

# ─── SQL Server DBA track ──────────────────────────────────────────────────────

variable "deploy_sre_dba_infra" {
  description = "Set to true to deploy the SQL MCP Container App and the sample Azure SQL server and database."
  type        = bool
  default     = false
}

variable "sre_dba_sql_location" {
  description = "Region override for the Azure SQL server and database. Uses location when null."
  type        = string
  default     = null
}

variable "sre_dba_sql_client_ip_address" {
  description = "Public IPv4 address allowed through the Azure SQL firewall for running the setup scripts. No rule is created when null."
  type        = string
  default     = null
}

variable "sre_dba_sql_mcp_image" {
  description = "Container image for the read-only SQL Server MCP server."
  type        = string
  default     = "ghcr.io/microsoft/frontier-sre-agent-rvas/sql-server-mcp:latest"
}
