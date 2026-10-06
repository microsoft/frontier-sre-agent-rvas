variable "location" {
  description = "Azure region for all resources."
  type        = string
  default     = "swedencentral"
}

variable "resource_group_name" {
  description = "Shared resource group name for all workload resources. Previously split across twelve resource groups; see the origin_tags local for each resource's pre-consolidation origin."
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
  description = "Admin password supplied by the root module for all lab VMs."
  type        = string
  sensitive   = true
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
