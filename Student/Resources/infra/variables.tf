variable "location" {
  description = "Azure region for all resources."
  type        = string
  default     = "swedencentral"
}

variable "resource_group_name" {
  description = "Name of the single shared resource group used by every workload resource."
  type        = string
  default     = "rg-sre-agent-rvas"
}

variable "vm_admin_username" {
  description = "Admin username for the parking app VMs (Madrid and Paris)."
  type        = string
  default     = "azureadmin"
}

variable "vm_admin_password" {
  description = "Admin password for the parking app VMs (Madrid and Paris)."
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
  description = "Create Standard public IPs for the Madrid and Paris VMs. Useful for direct SSH/RDP access in dev/test."
  type        = bool
  default     = false
}

variable "berlin_mcp_auth_token" {
  description = "MCP auth token for the Berlin MCP server. Leave empty to disable authentication (dev/lab use only)."
  type        = string
  sensitive   = true
  default     = ""
}
