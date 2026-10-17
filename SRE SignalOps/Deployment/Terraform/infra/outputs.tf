output "subscription_id" {
  value = module.workload.subscription_id
}

output "sre_agent_id" {
  value = azapi_resource.agent.id
}

output "sre_agent_name" {
  value = azapi_resource.agent.name
}

output "agent_resource_group" {
  value = azurerm_resource_group.agent.name
}

output "sre_agent_endpoint" {
  value = azapi_resource.agent.output.properties.agentEndpoint
}

output "mission_context" {
  description = "Non-secret values consumed by the mission context loader."
  value = {
    AZURE_SUBSCRIPTION_ID      = module.workload.subscription_id
    AZURE_RESOURCE_GROUP       = module.workload.sample_food_resource_group_name
    AGENT_RESOURCE_GROUP       = azurerm_resource_group.agent.name
    SRE_AGENT_ID               = azapi_resource.agent.id
    SRE_AGENT_NAME             = azapi_resource.agent.name
    SRE_AGENT_ENDPOINT         = azapi_resource.agent.output.properties.agentEndpoint
    LOG_ANALYTICS_WORKSPACE_ID = module.workload.log_analytics_workspace_id
    LOG_ANALYTICS_CUSTOMER_ID  = module.workload.log_analytics_workspace_customer_id
    APPLICATIONINSIGHTS_NAME   = module.workload.sample_food_resource_names.app_insights
    API_APP_NAME               = module.workload.sample_food_api_container_app_name
    FRONTEND_APP_NAME          = module.workload.sample_food_frontend_container_app_name
    FRONTEND_URL               = module.workload.sample_food_frontend_url
    API_URL                    = module.workload.sample_food_api_url
  }
}

output "vm_applications" {
  value = {
    madrid = var.deploy_madrid_vm ? {
      name           = module.workload.parking_madrid_vm_name
      resource_group = var.rg_parking_madrid
    } : null
    paris = var.deploy_paris_vm ? {
      name           = module.workload.parking_paris_vm_name
      resource_group = var.rg_parking_paris
    } : null
  }
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

output "demo_lab_vm_private_ips" {
  value = module.workload.demo_lab_vm_private_ips
}

output "demo_lab_vm_names" {
  value = module.workload.demo_lab_vm_names
}

output "demo_lab_scenario_resource_names" {
  description = "Resource names used by the scenario scripts (NSGs, route tables, VMs, Firewall, Bastion)."
  value       = module.workload.demo_lab_scenario_resource_names
}

output "demo_lab_bastion_host_name" {
  value = module.workload.demo_lab_bastion_host_name
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

output "sample_food_resource_group_name" {
  value = module.workload.sample_food_resource_group_name
}

output "sample_food_api_container_app_name" {
  value = module.workload.sample_food_api_container_app_name
}

output "sample_food_frontend_container_app_name" {
  value = module.workload.sample_food_frontend_container_app_name
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

output "parking_resource_groups" {
  value = module.workload.parking_resource_groups
}
