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

output "demo_lab_vm_private_ips" {
  value = module.workload.demo_lab_vm_private_ips
}

output "demo_lab_vm_names" {
  value = module.workload.demo_lab_vm_names
}

output "sample_food_api_url" {
  value = module.workload.sample_food_api_url
}

output "sample_food_frontend_url" {
  value = module.workload.sample_food_frontend_url
}

output "parking_lisbon_url" {
  value = module.workload.parking_lisbon_url
}

output "parking_berlin_url" {
  value = module.workload.parking_berlin_url
}

output "parking_chaos_control_url" {
  value = module.workload.parking_chaos_control_url
}

output "parking_vm_health_control_url" {
  value = module.workload.parking_vm_health_control_url
}

output "parking_resource_groups" {
  value = module.workload.parking_resource_groups
}
