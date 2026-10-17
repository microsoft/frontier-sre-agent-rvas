variable "location" {
  description = "Azure region for all resources."
  type        = string
  default     = "uksouth"
}

variable "container_registry_name" {
  description = "Existing ACR in the selected subscription. It is read, not created or destroyed."
  type        = string
}

variable "container_registry_resource_group" {
  type = string
}

variable "registry_pull_role" {
  description = "Use Repository Reader for an ABAC-enabled registry, otherwise AcrPull."
  type        = string
  default     = "AcrPull"

  validation {
    condition     = contains(["AcrPull", "Container Registry Repository Reader"], var.registry_pull_role)
    error_message = "Choose AcrPull or Container Registry Repository Reader."
  }
}

variable "container_images" {
  description = "Digest-pinned images built into your existing ACR by Build-Images.ps1."
  type = object({
    grubify_api      = string
    grubify_frontend = string
    lisbon           = string
    berlin           = string
    berlin_mcp       = string
    chaos_control    = string
    vm_health        = string
  })

  validation {
    condition     = alltrue([for image in values(var.container_images) : can(regex("^[a-z0-9]+\\.azurecr\\.io/.+@sha256:[a-f0-9]{64}$", image))])
    error_message = "Supply seven digest-pinned Azure Container Registry image references, not mutable tags or external registry images."
  }
}

variable "agent_name" {
  type    = string
  default = "signalops-tf-sre-agent"
}

variable "rg_agent" {
  type    = string
  default = "rg-signalops-tf-agent"
}

variable "agent_location" {
  description = "An Azure SRE Agent-supported region; independent of the workload region."
  type        = string
  default     = "swedencentral"
}

variable "rg_hub" {
  description = "Resource group name for the hub connectivity resources."
  type        = string
  default     = "rg-signalops-tf-hub"
}

variable "rg_spoke_web_api" {
  description = "Resource group name for the web/API IaaS spoke."
  type        = string
  default     = "rg-signalops-tf-web-api"
}

variable "rg_spoke_data" {
  description = "Resource group name for the data IaaS spoke."
  type        = string
  default     = "rg-signalops-tf-data"
}

variable "rg_sample_food" {
  description = "Resource group name for the Sample Food Container Apps spoke."
  type        = string
  default     = "rg-signalops-tf-food"
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
  description = "Admin password for the lab VMs. Supply securely at deployment time."
  type        = string
  sensitive   = true

  validation {
    condition     = length(var.vm_admin_password) >= 12
    error_message = "Use a VM admin password of at least 12 characters that meets Azure complexity requirements."
  }
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
  default     = "rg-signalops-tf-parking-lisbon"
}

variable "rg_parking_berlin" {
  description = "Resource group name for the Berlin Parking API."
  type        = string
  default     = "rg-signalops-tf-parking-berlin"
}

variable "rg_parking_madrid" {
  description = "Resource group name for the Madrid Parking VM."
  type        = string
  default     = "rg-signalops-tf-parking-madrid"
}

variable "rg_parking_paris" {
  description = "Resource group name for the Paris Parking VM."
  type        = string
  default     = "rg-signalops-tf-parking-paris"
}

variable "rg_parking_chaos" {
  description = "Resource group name for Chaos Control and VM Health Control."
  type        = string
  default     = "rg-signalops-tf-parking-chaos"
}

variable "create_parking_public_ips" {
  description = "Create Standard public IPs for the Madrid and Paris VMs. Useful for direct SSH/RDP access in dev/test."
  type        = bool
  default     = false
}

variable "berlin_mcp_auth_token" {
  description = "MCP auth token for the Berlin MCP server. Supply securely at deployment time."
  type        = string
  sensitive   = true

  validation {
    condition     = length(var.berlin_mcp_auth_token) >= 32
    error_message = "Supply a Berlin MCP authentication token of at least 32 characters."
  }
}
