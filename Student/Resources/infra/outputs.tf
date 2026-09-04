output "subscription_id" {
  value = module.workload.subscription_id
}

output "log_analytics_workspace_id" {
  description = "Demo Log Analytics workspace ID — needed when wiring up the SRE Agent connector."
  value       = module.workload.log_analytics_workspace_id
}

output "managed_resource_ids" {
  description = "Resource IDs to pass into the SRE Agent knowledge graph."
  value       = module.workload.managed_resource_ids
}

output "hub_resource_group_name" {
  value = module.workload.hub_resource_group_name
}

output "web_api_resource_group_name" {
  description = "Resource group for the Web-API IaaS spoke — used by scenario scripts for VM run-commands."
  value       = module.workload.web_api_resource_group_name
}

output "data_resource_group_name" {
  description = "Resource group for the data spoke — used by scenario scripts."
  value       = module.workload.data_resource_group_name
}

output "demo_lab_location" {
  value = module.workload.demo_lab_location
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

output "demo_lab_scenario_resource_names" {
  description = "Resource names used by the scenario scripts (NSGs, route tables, VMs, Firewall, Bastion)."
  value       = module.workload.demo_lab_scenario_resource_names
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

output "demo_lab_network_watcher_name" {
  value = module.workload.demo_lab_network_watcher_name
}

output "demo_lab_network_watcher_resource_group_name" {
  value = module.workload.demo_lab_network_watcher_resource_group_name
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

output "sample_food_api_url" {
  value = module.workload.sample_food_api_url
}

output "sample_food_frontend_url" {
  value = module.workload.sample_food_frontend_url
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

output "sample_food_application_insights_resource_id" {
  value = module.workload.sample_food_application_insights_resource_id
}

output "sample_food_application_insights_app_id" {
  value = module.workload.sample_food_application_insights_app_id
}

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
