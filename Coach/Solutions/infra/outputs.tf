# ─── SRE Agent ─────────────────────────────────────────────────────────────────

output "subscription_id" {
  description = "Azure subscription ID used by this deployment."
  value       = module.workload.subscription_id
}

output "agent_resource_group" {
  description = "Resource group name that contains the Azure SRE Agent."
  value       = module.sre_agent.agent_resource_group
}

output "agent_name" {
  description = "Azure SRE Agent resource name."
  value       = module.sre_agent.agent_name
}

output "agent_endpoint" {
  description = "Azure SRE Agent data-plane endpoint returned by ARM."
  value       = module.sre_agent.agent_endpoint
}

output "agent_portal_url" {
  description = "Azure SRE Agent portal URL."
  value       = module.sre_agent.agent_portal_url
}

output "agent_resource_id" {
  description = "Azure SRE Agent ARM resource ID."
  value       = module.sre_agent.agent_resource_id
}

output "application_insights_id" {
  description = "Application Insights resource ID used by the agent."
  value       = module.sre_agent.application_insights_id
}

output "application_insights_app_id" {
  description = "Application Insights app ID passed to the agent log configuration."
  value       = module.sre_agent.application_insights_app_id
}

output "log_analytics_workspace_id" {
  description = "Log Analytics workspace resource ID used by Application Insights."
  value       = module.sre_agent.log_analytics_workspace_id
}

output "managed_identity_client_id" {
  description = "User-assigned managed identity client ID."
  value       = module.sre_agent.managed_identity_client_id
}

output "managed_identity_principal_id" {
  description = "User-assigned managed identity principal ID used for RBAC role assignments."
  value       = module.sre_agent.managed_identity_principal_id
}

output "outbound_ip_addresses" {
  description = "Outbound IP addresses returned by the Azure SRE Agent resource."
  value       = module.sre_agent.outbound_ip_addresses
}

output "provisioning_state" {
  description = "Azure SRE Agent provisioning state."
  value       = module.sre_agent.provisioning_state
}

# ─── Workload ──────────────────────────────────────────────────────────────────

output "hub_resource_group_name" {
  value = module.workload.hub_resource_group_name
}

output "web_api_resource_group_name" {
  value = module.workload.web_api_resource_group_name
}

output "data_resource_group_name" {
  value = module.workload.data_resource_group_name
}

output "demo_lab_location" {
  value = module.workload.demo_lab_location
}

output "demo_lab_log_analytics_workspace_id" {
  value = module.workload.demo_lab_log_analytics_workspace_id
}

output "demo_lab_log_analytics_workspace_customer_id" {
  value = module.workload.demo_lab_log_analytics_workspace_customer_id
}

output "demo_lab_storage_account_name" {
  value = module.workload.demo_lab_storage_account_name
}

output "demo_lab_network_watcher_name" {
  value = module.workload.demo_lab_network_watcher_name
}

output "demo_lab_network_watcher_resource_group_name" {
  value = module.workload.demo_lab_network_watcher_resource_group_name
}

output "demo_lab_vm_private_ips" {
  value = module.workload.demo_lab_vm_private_ips
}

output "demo_lab_vm_names" {
  value = module.workload.demo_lab_vm_names
}

output "demo_lab_azure_firewall_private_ip" {
  value = module.workload.demo_lab_azure_firewall_private_ip
}

output "demo_lab_azure_firewall_public_ip" {
  value = module.workload.demo_lab_azure_firewall_public_ip
}

output "demo_lab_bastion_host_name" {
  value = module.workload.demo_lab_bastion_host_name
}

output "demo_lab_bastion_dns_name" {
  value = module.workload.demo_lab_bastion_dns_name
}

output "demo_lab_bastion_public_ip" {
  value = module.workload.demo_lab_bastion_public_ip
}

output "demo_lab_scenario_resource_names" {
  value = module.workload.demo_lab_scenario_resource_names
}

output "sample_food_app_enabled" {
  value = module.workload.sample_food_app_enabled
}

output "sample_food_resource_names" {
  value = module.workload.sample_food_resource_names
}

output "sample_food_resource_group_name" {
  value = module.workload.sample_food_resource_group_name
}

output "sample_food_location" {
  value = module.workload.sample_food_location
}

output "sample_food_network" {
  value = module.workload.sample_food_network
}

output "sample_food_api_container_app_name" {
  value = module.workload.sample_food_api_container_app_name
}

output "sample_food_frontend_container_app_name" {
  value = module.workload.sample_food_frontend_container_app_name
}

output "sample_food_api_url" {
  value = module.workload.sample_food_api_url
}

output "sample_food_frontend_url" {
  value = module.workload.sample_food_frontend_url
}

output "sample_food_application_insights_resource_id" {
  value = module.workload.sample_food_application_insights_resource_id
}

output "sample_food_application_insights_app_id" {
  value = module.workload.sample_food_application_insights_app_id
}

# ─── Parking App ───────────────────────────────────────────────────────────────

output "parking_lisbon_url" {
  value = module.workload.parking_lisbon_url
}

output "parking_berlin_url" {
  value = module.workload.parking_berlin_url
}

output "parking_berlin_mcp_url" {
  value = module.workload.parking_berlin_mcp_url
}

output "parking_chaos_control_url" {
  value = module.workload.parking_chaos_control_url
}

output "parking_vm_health_control_url" {
  value = module.workload.parking_vm_health_control_url
}

output "parking_frontend_name" {
  value = module.workload.parking_frontend_name
}

output "parking_frontend_url" {
  value = module.workload.parking_frontend_url
}

output "parking_frontend_resource_group_name" {
  value = module.workload.parking_frontend_resource_group_name
}

output "parking_frontend_service_plan_name" {
  value = module.workload.parking_frontend_service_plan_name
}

output "parking_madrid_vm_name" {
  value = module.workload.parking_madrid_vm_name
}

output "parking_madrid_vm_private_ip" {
  value = module.workload.parking_madrid_vm_private_ip
}

output "parking_madrid_api_url" {
  value = module.workload.parking_madrid_api_url
}

output "parking_paris_vm_name" {
  value = module.workload.parking_paris_vm_name
}

output "parking_paris_vm_private_ip" {
  value = module.workload.parking_paris_vm_private_ip
}

output "parking_paris_api_url" {
  value = module.workload.parking_paris_api_url
}

output "parking_resource_groups" {
  value = module.workload.parking_resource_groups
}
