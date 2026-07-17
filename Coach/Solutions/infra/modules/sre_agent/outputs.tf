output "agent_resource_group" {
  description = "Resource group name that contains the Azure SRE Agent."
  value       = azurerm_resource_group.agent.name
}

output "agent_name" {
  description = "Azure SRE Agent resource name."
  value       = azapi_resource.agent.name
}

output "agent_endpoint" {
  description = "Azure SRE Agent data-plane endpoint returned by ARM."
  value       = try(azapi_resource.agent.output.properties.agentEndpoint, null)
}

output "agent_portal_url" {
  description = "Azure SRE Agent portal URL."
  value       = "https://sre.azure.com/#/agent/${split("/", azapi_resource.agent.id)[2]}/${azurerm_resource_group.agent.name}/${azapi_resource.agent.name}"
}

output "agent_resource_id" {
  description = "Azure SRE Agent ARM resource ID."
  value       = azapi_resource.agent.id
}

output "application_insights_id" {
  description = "Application Insights resource ID used by the agent."
  value       = azurerm_application_insights.agent.id
}

output "application_insights_app_id" {
  description = "Application Insights app ID passed to the agent log configuration."
  value       = azurerm_application_insights.agent.app_id
}

output "log_analytics_workspace_id" {
  description = "Log Analytics workspace resource ID used by Application Insights."
  value       = azurerm_log_analytics_workspace.agent.id
}

output "managed_identity_client_id" {
  description = "User-assigned managed identity client ID."
  value       = azurerm_user_assigned_identity.agent.client_id
}

output "managed_identity_principal_id" {
  description = "User-assigned managed identity principal ID used for RBAC role assignments."
  value       = azurerm_user_assigned_identity.agent.principal_id
}

output "outbound_ip_addresses" {
  description = "Outbound IP addresses returned by the Azure SRE Agent resource."
  value       = try(azapi_resource.agent.output.properties.outboundIpAddresses, [])
}

output "provisioning_state" {
  description = "Azure SRE Agent provisioning state."
  value       = try(azapi_resource.agent.output.properties.provisioningState, null)
}
