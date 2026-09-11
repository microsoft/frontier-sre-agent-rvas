# ─── Parking Manager Frontend ─────────────────────────────────────────────────
# The Web App keeps a public HTTPS endpoint. Regional VNet integration is used
# only for outbound calls to the private Madrid and Paris APIs. The integration
# subnet has no UDR, and route-all is disabled, so public dependencies do not
# traverse the hub firewall.

resource "azurerm_resource_group" "parking_frontend" {
  name     = var.rg_parking_frontend
  location = var.location
  tags     = local.resource_tags
}

resource "azurerm_service_plan" "parking_frontend" {
  name                = "asp-parking-frontend"
  location            = azurerm_resource_group.parking_frontend.location
  resource_group_name = azurerm_resource_group.parking_frontend.name
  os_type             = "Linux"
  sku_name            = "B1"
  tags                = local.resource_tags
}

resource "azurerm_linux_web_app" "parking_frontend" {
  name                                           = "app-parking-frontend-${local.demo_suffix}"
  location                                       = azurerm_resource_group.parking_frontend.location
  resource_group_name                            = azurerm_resource_group.parking_frontend.name
  service_plan_id                                = azurerm_service_plan.parking_frontend.id
  virtual_network_subnet_id                      = azurerm_subnet.parking_frontend.id
  public_network_access_enabled                  = true
  https_only                                     = true
  ftp_publish_basic_authentication_enabled       = false
  webdeploy_publish_basic_authentication_enabled = false
  tags                                           = local.resource_tags

  app_settings = {
    NODE_ENV                        = "production"
    PORT                            = "8080"
    WEBSITES_PORT                   = "8080"
    REACT_APP_LISBON_API_URL        = "https://${azurerm_container_app.parking_lisbon.ingress[0].fqdn}"
    REACT_APP_MADRID_API_URL        = var.deploy_madrid_vm ? "http://${azurerm_network_interface.madrid[0].private_ip_address}:3002" : ""
    REACT_APP_PARIS_API_URL         = var.deploy_paris_vm ? "http://${azurerm_network_interface.paris[0].private_ip_address}:3003" : ""
    REACT_APP_BERLIN_API_URL        = "https://${azurerm_container_app.parking_berlin.ingress[0].fqdn}"
    REACT_APP_CHAOS_CONTROL_URL     = "https://${azurerm_container_app.chaos_control.ingress[0].fqdn}"
    REACT_APP_VM_HEALTH_CONTROL_URL = "https://${azurerm_container_app.vm_health_control.ingress[0].fqdn}"
  }

  site_config {
    always_on                         = true
    ftps_state                        = "Disabled"
    health_check_eviction_time_in_min = 10
    health_check_path                 = "/health"
    minimum_tls_version               = "1.2"
    vnet_route_all_enabled            = false

    application_stack {
      docker_image_name = local.parking_images.frontend
    }
  }
}
