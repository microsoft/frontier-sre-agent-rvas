# ─── Subscription / Identity ───────────────────────────────────────────────────

output "subscription_id" {
  description = "Azure subscription ID used by this deployment."
  value       = data.azurerm_client_config.current.subscription_id
}

# ─── SRE Agent inputs ──────────────────────────────────────────────────────────
# These outputs feed directly into the sre_agent module inputs.

output "log_analytics_workspace_id" {
  description = "Demo Log Analytics workspace resource ID (used by the SRE Agent log connector and as an agent-managed scope)."
  value       = azurerm_log_analytics_workspace.demo.id
}

output "log_analytics_workspace_customer_id" {
  description = "Demo Log Analytics workspace customer ID."
  value       = azurerm_log_analytics_workspace.demo.workspace_id
}

output "rg_hub_id" {
  description = "Hub connectivity resource group ID (used by sre_agent for RBAC scoping)."
  value       = azurerm_resource_group.hub.id
}

output "rg_spoke_web_api_id" {
  description = "Web/API spoke resource group ID."
  value       = azurerm_resource_group.spoke_web_api.id
}

output "rg_spoke_data_id" {
  description = "Data spoke resource group ID."
  value       = azurerm_resource_group.spoke_data.id
}

output "rg_sample_food_id" {
  description = "Sample Food resource group ID."
  value       = azurerm_resource_group.sample_food.id
}

output "managed_resource_ids" {
  description = "List of resource IDs for the SRE Agent knowledge graph (subscription + workload resource groups + demo Log Analytics workspace)."
  value = distinct([
    "/subscriptions/${data.azurerm_client_config.current.subscription_id}",
    azurerm_resource_group.hub.id,
    azurerm_resource_group.spoke_web_api.id,
    azurerm_resource_group.spoke_data.id,
    azurerm_resource_group.sample_food.id,
    azurerm_log_analytics_workspace.demo.id,
  ])
}

# ─── Hub / Demo Lab ────────────────────────────────────────────────────────────

output "hub_resource_group_name" {
  description = "Connectivity resource group for the hub (Azure Firewall, Bastion, shared observability)."
  value       = azurerm_resource_group.hub.name
}

output "web_api_resource_group_name" {
  description = "Resource group for the Web-API IaaS spoke (client + web VMs, internal load balancer)."
  value       = azurerm_resource_group.spoke_web_api.name
}

output "data_resource_group_name" {
  description = "Resource group for the Data IaaS spoke (API + PostgreSQL VMs)."
  value       = azurerm_resource_group.spoke_data.name
}

output "demo_lab_location" {
  description = "Azure region used by the hub and IaaS spokes."
  value       = azurerm_resource_group.hub.location
}

output "demo_lab_log_analytics_workspace_id" {
  description = "Log Analytics workspace resource ID for Traffic Analytics and Sample Food telemetry."
  value       = azurerm_log_analytics_workspace.demo.id
}

output "demo_lab_log_analytics_workspace_customer_id" {
  description = "Log Analytics workspace customer ID used by Azure CLI query commands."
  value       = azurerm_log_analytics_workspace.demo.workspace_id
}

output "demo_lab_storage_account_name" {
  description = "Dedicated storage account that receives raw VNet Flow Log blobs."
  value       = azurerm_storage_account.flow_logs.name
}

output "demo_lab_network_watcher_name" {
  description = "Regional Network Watcher used by flow log resources."
  value       = local.demo_network_watcher_name
}

output "demo_lab_network_watcher_resource_group_name" {
  description = "Resource group that contains the Network Watcher and flow log child resources."
  value       = local.demo_network_watcher_rg
}

output "demo_lab_vm_private_ips" {
  description = "Private IPs used by demo traffic scripts and KQL examples."
  value = {
    client   = azurerm_network_interface.client.private_ip_address
    web_1    = azurerm_network_interface.web[0].private_ip_address
    web_2    = azurerm_network_interface.web[1].private_ip_address
    api      = azurerm_network_interface.api.private_ip_address
    db       = azurerm_network_interface.db.private_ip_address
    nva      = azurerm_network_interface.nva.private_ip_address
    firewall = azurerm_firewall.hub.ip_configuration[0].private_ip_address
    ilb      = "10.20.2.100"
  }
}

output "demo_lab_vm_names" {
  description = "Linux VM names used by validation and operations scripts."
  value = {
    client = azurerm_linux_virtual_machine.client.name
    web_1  = azurerm_linux_virtual_machine.web[0].name
    web_2  = azurerm_linux_virtual_machine.web[1].name
    api    = azurerm_linux_virtual_machine.api.name
    db     = azurerm_linux_virtual_machine.db.name
    nva    = azurerm_linux_virtual_machine.nva.name
  }
}

output "demo_lab_azure_firewall_private_ip" {
  description = "Private IP of the hub Azure Firewall used as the default centralized next hop."
  value       = azurerm_firewall.hub.ip_configuration[0].private_ip_address
}

output "demo_lab_azure_firewall_public_ip" {
  description = "Public IP used by Azure Firewall for SNAT of Internet-bound demo traffic."
  value       = azurerm_public_ip.firewall.ip_address
}

output "demo_lab_bastion_host_name" {
  description = "Azure Bastion host name used for private VM access."
  value       = azurerm_bastion_host.hub.name
}

output "demo_lab_bastion_dns_name" {
  description = "Azure Bastion DNS name."
  value       = azurerm_bastion_host.hub.dns_name
}

output "demo_lab_bastion_public_ip" {
  description = "Public IP assigned to Azure Bastion. VMs still have no public IPs."
  value       = azurerm_public_ip.bastion.ip_address
}

output "demo_lab_scenario_resource_names" {
  description = "Resource names used by the scenario scripts."
  value = {
    client_vm        = azurerm_linux_virtual_machine.client.name
    app_nsg          = azurerm_network_security_group.app.name
    data_nsg         = azurerm_network_security_group.data.name
    app_vnet         = azurerm_virtual_network.spoke_app.name
    data_vnet        = azurerm_virtual_network.spoke_data.name
    app_route_table  = azurerm_route_table.app_to_nva.name
    data_route_table = azurerm_route_table.data_to_nva.name
    firewall_name    = azurerm_firewall.hub.name
    bastion_name     = azurerm_bastion_host.hub.name
  }
}

# ─── Sample Food ───────────────────────────────────────────────────────────────

output "sample_food_app_enabled" {
  description = "Whether the Sample Food Ordering App lab is enabled."
  value       = true
}

output "sample_food_resource_names" {
  description = "Resource names used by Sample Food Ordering App scripts and documentation."
  value = {
    resource_group             = azurerm_resource_group.sample_food.name
    vnet                       = azurerm_virtual_network.sample_food.name
    container_apps_environment = azurerm_container_app_environment.sample_food.name
    api_container_app          = azurerm_container_app.sample_food_api.name
    frontend_container_app     = azurerm_container_app.sample_food_frontend.name
    app_insights               = azurerm_application_insights.sample_food.name
  }
}

output "sample_food_resource_group_name" {
  description = "Resource group containing the Sample Food Ordering App regional resources."
  value       = azurerm_resource_group.sample_food.name
}

output "sample_food_location" {
  description = "Azure region used by Sample Food Ordering App regional resources."
  value       = azurerm_resource_group.sample_food.location
}

output "sample_food_network" {
  description = "Network resource IDs and CIDRs for the Sample Food Ordering App lab."
  value = {
    vnet_id                    = azurerm_virtual_network.sample_food.id
    address_space              = azurerm_virtual_network.sample_food.address_space
    container_apps_subnet_id   = azurerm_subnet.sample_food_container_apps.id
    container_apps_subnet_cidr = "10.40.0.0/21"
    probe_subnet_id            = azurerm_subnet.sample_food_probe.id
    probe_subnet_cidr          = "10.40.8.0/24"
  }
}

output "sample_food_api_container_app_name" {
  description = "Sample Food Ordering API Container App name."
  value       = azurerm_container_app.sample_food_api.name
}

output "sample_food_frontend_container_app_name" {
  description = "Sample Food Ordering frontend Container App name."
  value       = azurerm_container_app.sample_food_frontend.name
}

output "sample_food_api_url" {
  description = "Sample Food Ordering API HTTPS URL."
  value       = "https://${azurerm_container_app.sample_food_api.ingress[0].fqdn}"
}

output "sample_food_frontend_url" {
  description = "Sample Food Ordering frontend HTTPS URL."
  value       = "https://${azurerm_container_app.sample_food_frontend.ingress[0].fqdn}"
}

output "sample_food_application_insights_resource_id" {
  description = "Application Insights resource ID for Sample Food Ordering App telemetry."
  value       = azurerm_application_insights.sample_food.id
}

output "sample_food_application_insights_app_id" {
  description = "Application Insights app ID for Sample Food Ordering App telemetry."
  value       = azurerm_application_insights.sample_food.app_id
}

# ─── Parking App ───────────────────────────────────────────────────────────────

output "parking_lisbon_url" {
  description = "HTTPS URL for the Lisbon Parking API Container App."
  value       = "https://${azurerm_container_app.parking_lisbon.ingress[0].fqdn}"
}

output "parking_berlin_url" {
  description = "HTTPS URL for the Berlin Parking API Container App."
  value       = "https://${azurerm_container_app.parking_berlin.ingress[0].fqdn}"
}

output "parking_berlin_mcp_url" {
  description = "Berlin MCP server URL — use as the MCP connector endpoint in the SRE Agent"
  value       = "https://${azurerm_container_app.berlin_mcp_server.ingress[0].fqdn}/mcp"
}

output "parking_chaos_control_url" {
  description = "HTTPS URL for the Chaos Control Container App."
  value       = "https://${azurerm_container_app.chaos_control.ingress[0].fqdn}"
}

output "parking_vm_health_control_url" {
  description = "HTTPS URL for the VM Health Control Container App."
  value       = "https://${azurerm_container_app.vm_health_control.ingress[0].fqdn}"
}

output "parking_madrid_vm_name" {
  description = "Name of the Madrid Windows Server VM (parking API on port 3002)."
  value       = var.deploy_madrid_vm ? azurerm_windows_virtual_machine.madrid[0].name : ""
}

output "parking_madrid_vm_private_ip" {
  description = "Private IP address of the Madrid VM."
  value       = var.deploy_madrid_vm ? azurerm_network_interface.madrid[0].private_ip_address : ""
}

output "parking_madrid_api_url" {
  description = "Madrid Parking API URL (private IP, accessible within the VNet on port 3002)."
  value       = var.deploy_madrid_vm ? "http://${azurerm_network_interface.madrid[0].private_ip_address}:3002" : ""
}

output "parking_paris_vm_name" {
  description = "Name of the Paris Ubuntu Server VM (parking API on port 3003)."
  value       = var.deploy_paris_vm ? azurerm_linux_virtual_machine.paris[0].name : ""
}

output "parking_paris_vm_private_ip" {
  description = "Private IP address of the Paris VM."
  value       = var.deploy_paris_vm ? azurerm_network_interface.paris[0].private_ip_address : ""
}

output "parking_paris_api_url" {
  description = "Paris Parking API URL (private IP, accessible within the VNet on port 3003)."
  value       = var.deploy_paris_vm ? "http://${azurerm_network_interface.paris[0].private_ip_address}:3003" : ""
}

output "parking_resource_groups" {
  description = "Resource group names for each parking app component."
  value = {
    lisbon = azurerm_resource_group.parking_lisbon.name
    berlin = azurerm_resource_group.parking_berlin.name
    madrid = azurerm_resource_group.parking_madrid.name
    paris  = azurerm_resource_group.parking_paris.name
    chaos  = azurerm_resource_group.parking_chaos.name
  }
}
