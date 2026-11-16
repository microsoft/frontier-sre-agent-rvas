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

variable "parking_frontend_sku" {
  description = "App Service plan SKU for the Parking Manager frontend. B1 often has no capacity in Sweden Central, so the default is B2; switch to B1 or P0v3 if your region requires it."
  type        = string
  default     = "B2"
}

variable "parking_source_base_url" {
  description = "Base URL the Madrid VM downloads the Parking API source from. The default tracks the main branch of the repository; point it at your fork or branch if you changed the code."
  type        = string
  default     = "https://raw.githubusercontent.com/microsoft/frontier-sre-agent-rvas/main/labs/01-azure-operations/resources/parking-manager/backend"
}

variable "berlin_mcp_auth_token" {
  description = "MCP auth token for the Berlin MCP server. Leave empty to disable authentication (dev/lab use only)."
  type        = string
  sensitive   = true
  default     = ""
}
