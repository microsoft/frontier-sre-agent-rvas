variable "resource_group_name" {
  description = "Dedicated resource group for the Fabric workshop capacity and team agents."
  type        = string
}

variable "agent_location" {
  description = "Azure region supporting Azure SRE Agent and the configured model."
  type        = string
  default     = "swedencentral"
}

variable "capacity_location" {
  description = "Fabric-supported region compatible with the workshop tenant and workspaces."
  type        = string
}

variable "capacity_name" {
  description = "Globally unique Fabric capacity name, 3-63 lowercase letters or digits, starting with a letter."
  type        = string

  validation {
    condition     = can(regex("^[a-z][a-z0-9]{2,62}$", var.capacity_name))
    error_message = "Use 3-63 lowercase letters or digits, starting with a letter."
  }
}

variable "capacity_sku" {
  description = "Paid Fabric SKU. F4 is a starting point for monitoring, not a guarantee of audience workload capacity."
  type        = string
  default     = "F4"

  validation {
    condition     = contains(["F2", "F4", "F8", "F16", "F32", "F64", "F128", "F256", "F512", "F1024", "F2048"], var.capacity_sku)
    error_message = "Specify a supported Fabric F SKU."
  }
}

variable "capacity_admin_members" {
  description = "Coach administrator user identities (UPNs) for the shared Fabric capacity; not participant agent identities."
  type        = set(string)

  validation {
    condition     = length(var.capacity_admin_members) > 0 && alltrue([for member in var.capacity_admin_members : can(regex("^[^@\\s]+@[^@\\s]+$", member))])
    error_message = "Provide at least one coach administrator UPN."
  }
}

variable "teams" {
  description = "One agent per team; administrator_principal_ids are Entra object IDs of participant users or security groups."
  type = map(object({
    agent_name                  = string
    administrator_principal_ids = set(string)
  }))

  validation {
    condition = length(var.teams) > 0 && alltrue([
      for team in values(var.teams) :
      can(regex("^[a-z][a-z0-9-]{2,39}$", team.agent_name)) &&
      length(team.administrator_principal_ids) > 0 &&
      alltrue([for id in team.administrator_principal_ids : can(regex("^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$", id))])
    ])
    error_message = "Provide at least one team, a 3-40 character lowercase agent name, and participant/group object IDs."
  }

  validation {
    condition     = length(distinct([for team in values(var.teams) : team.agent_name])) == length(var.teams)
    error_message = "Each team must have a unique agent name."
  }
}
