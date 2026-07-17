locals {
  resource_tags = {
    workload    = "azure-sre-agent"
    managed-by  = "terraform"
    data-plane  = "configuration-api"
    environment = "dev"
    owner       = "sre-platform"
    repository  = "azure-sre-agent"
  }

  managed_scope_roles = [
    "Reader",
    "Log Analytics Reader",
    "Monitoring Reader"
  ]

  # Build a flat map of { "<label>|<role>" => { scope, role } } from var.managed_scopes.
  # The label is the map key from var.managed_scopes; keeping it stable across deployments
  # avoids Terraform trying to recreate role assignments on every plan.
  managed_scope_role_assignments = merge([
    for label, scope_id in var.managed_scopes : {
      for role in local.managed_scope_roles :
      "${label}|${role}" => {
        scope = scope_id
        role  = role
      }
    }
  ]...)
}
