variable "location" {
  description = "Azure region for all resources."
  type        = string
  default     = "uksouth"
}

variable "rg_agent" {
  description = "Resource group name for the Azure SRE Agent."
  type        = string
  default     = "rg-sre-agent"
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

