output "capacity" {
  description = "Shared capacity ARM details; obtain the Fabric capacity UUID from the Fabric portal/API during coach setup."
  value = {
    resource_id = azapi_resource.capacity.id
    name        = azapi_resource.capacity.name
    location    = var.capacity_location
    sku         = var.capacity_sku
  }
}

output "team_agents" {
  description = "Coach handoff: team agent URLs and managed identity IDs for Fabric read grants."
  value = {
    for key, agent in module.sre_agent : key => {
      resource_id                   = agent.agent_resource_id
      portal_url                    = agent.agent_portal_url
      managed_identity_client_id    = agent.managed_identity_client_id
      managed_identity_principal_id = agent.managed_identity_principal_id
      provisioning_state            = agent.provisioning_state
    }
  }
}
