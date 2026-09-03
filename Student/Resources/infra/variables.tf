variable "location" {
  description = "Azure region for all resources."
  type        = string
  default     = "swedencentral"
}

variable "rg_hub" {
  description = "Resource group name for the hub connectivity resources."
  type        = string
  default     = "rg-sre-hub-connectivity"
}

variable "rg_spoke_web_api" {
  description = "Resource group name for the web/API IaaS spoke."
  type        = string
  default     = "rg-sre-spoke-web-api-iaas"
}

variable "rg_spoke_data" {
  description = "Resource group name for the data IaaS spoke."
  type        = string
  default     = "rg-sre-spoke-data-iaas"
}

variable "rg_sample_food" {
  description = "Resource group name for the Sample Food Container Apps spoke."
  type        = string
  default     = "rg-sre-spoke-foodapp-paas"
}

variable "create_network_watcher" {
  description = "Set to true to create NetworkWatcherRG and the Network Watcher. Set to false (default) to read an existing one via data source."
  type        = bool
  default     = false
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

variable "rg_parking_lisbon" {
  description = "Resource group name for the Lisbon Parking API."
  type        = string
  default     = "rg-sre-parking-lisbon"
}

variable "rg_parking_berlin" {
  description = "Resource group name for the Berlin Parking API."
  type        = string
  default     = "rg-sre-parking-berlin"
}

variable "rg_parking_madrid" {
  description = "Resource group name for the Madrid Parking VM."
  type        = string
  default     = "rg-sre-parking-madrid"
}

variable "rg_parking_paris" {
  description = "Resource group name for the Paris Parking VM."
  type        = string
  default     = "rg-sre-parking-paris"
}

variable "rg_parking_chaos" {
  description = "Resource group name for Chaos Control and VM Health Control."
  type        = string
  default     = "rg-sre-parking-chaos"
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
