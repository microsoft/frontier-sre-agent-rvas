variable "location" {
  description = "Azure region for the SRE Agent and its supporting resources."
  type        = string
  default     = "swedencentral"
}

variable "resource_group_name" {
  description = "Name of the shared resource group that holds this module's resources."
  type        = string
}

variable "resource_group_id" {
  description = "ARM resource ID of the shared resource group, used as the agent resource's parent_id."
  type        = string
}

variable "managed_resource_ids" {
  description = "List of Azure resource IDs that the SRE Agent will monitor (fed into the agent knowledge graph). Typically includes the subscription, workload resource groups, and the demo Log Analytics workspace."
  type        = list(string)
}

variable "managed_scopes" {
  description = "Map of label => scope_id pairs used to generate RBAC role assignments for the agent's user-assigned identity. The label becomes part of the for_each key (format: '<label>|<role>'), so it must be stable across deployments. Use the subscription resource path ('/subscriptions/<id>') as the key for subscription-scoped entries."
  type        = map(string)
}

variable "log_analytics_workspace_id" {
  description = "Resource ID of the demo Log Analytics workspace. Required when enable_monitoring_connectors is true."
  type        = string
  default     = null
}

variable "agent_name" {
  description = "Name of the agent; also used to name its identity and logging resources."
  type        = string
  default     = "contoso-sre-agent-dev"
}

variable "read_only" {
  description = "Use ReadOnly mode and omit subscription Contributor and Monitoring Contributor grants."
  type        = bool
  default     = false
}

variable "enable_monitoring_connectors" {
  description = "Create the Azure Operations Log Analytics and Application Insights connectors."
  type        = bool
  default     = true
}

variable "default_model" {
  description = "Legacy explicit model configuration; null lets SRE Agent use its regional provider default. Verify the approved provider in the portal before sending data."
  type = object({
    name     = string
    provider = string
  })
  default = {
    name     = "claude-opus-4-6"
    provider = "Anthropic"
  }
}
