variable "location" {
  description = "Azure region for the SRE Agent and its supporting resources."
  type        = string
  default     = "swedencentral"
}

variable "rg_agent" {
  description = "Resource group name for the Azure SRE Agent."
  type        = string
  default     = "rg-sre-agent"
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
  description = "Resource ID of the demo Log Analytics workspace. Used by the Log Analytics connector."
  type        = string
}
