locals {
  resource_tags = {
    workload    = "azure-sre-agent"
    managed-by  = "terraform"
    data-plane  = "configuration-api"
    environment = "dev"
    owner       = "sre-platform"
    repository  = "azure-sre-agent"
  }

  managed_resource_ids = distinct([
    "/subscriptions/${data.azurerm_client_config.current.subscription_id}",
    azurerm_resource_group.hub.id,
    azurerm_resource_group.spoke_web_api.id,
    azurerm_resource_group.spoke_data.id,
    azurerm_resource_group.sample_food.id,
    azurerm_log_analytics_workspace.demo.id
  ])

  managed_scope_roles = [
    "Reader",
    "Log Analytics Reader",
    "Monitoring Reader"
  ]

  managed_scope_role_assignments = merge(
    {
      for role in local.managed_scope_roles :
      "/subscriptions/${data.azurerm_client_config.current.subscription_id}|${role}" => {
        scope = "/subscriptions/${data.azurerm_client_config.current.subscription_id}"
        role  = role
      }
    },
    {
      for role in local.managed_scope_roles :
      "hub-resource-group|${role}" => {
        scope = azurerm_resource_group.hub.id
        role  = role
      }
    },
    {
      for role in local.managed_scope_roles :
      "web-api-resource-group|${role}" => {
        scope = azurerm_resource_group.spoke_web_api.id
        role  = role
      }
    },
    {
      for role in local.managed_scope_roles :
      "data-resource-group|${role}" => {
        scope = azurerm_resource_group.spoke_data.id
        role  = role
      }
    },
    {
      for role in local.managed_scope_roles :
      "sample-food-resource-group|${role}" => {
        scope = azurerm_resource_group.sample_food.id
        role  = role
      }
    },
    {
      for role in local.managed_scope_roles :
      "demo-log-analytics|${role}" => {
        scope = azurerm_log_analytics_workspace.demo.id
        role  = role
      }
    }
  )
  demo_tags = merge(
    {
      workload    = "vnet-flow-logs-traffic-analytics-demo"
      environment = "demo"
      managed-by  = "terraform"
    },
    {
      owner = "demo-team"
    }
  )

  demo_address_spaces = {
    hub        = ["10.10.0.0/16"]
    spoke_app  = ["10.20.0.0/16"]
    spoke_data = ["10.30.0.0/16"]
  }

  demo_subnets = {
    hub_mgmt          = "10.10.1.0/24"
    hub_nva           = "10.10.2.0/24"
    hub_firewall      = "10.10.3.0/26"
    hub_firewall_mgmt = "10.10.4.0/26"
    hub_bastion       = "10.10.5.0/26"
    app_client        = "10.20.1.0/24"
    app_web           = "10.20.2.0/24"
    data_api          = "10.30.1.0/24"
    data_db           = "10.30.2.0/24"
    data_privatelink  = "10.30.3.0/24"
  }

  demo_network_watcher_name = var.create_network_watcher ? azurerm_network_watcher.demo[0].name : data.azurerm_network_watcher.demo_existing[0].name
  demo_network_watcher_rg   = var.create_network_watcher ? azurerm_network_watcher.demo[0].resource_group_name : data.azurerm_network_watcher.demo_existing[0].resource_group_name

  demo_web_cloud_init    = base64encode(templatefile("${path.module}/templates/demo-lab-web-cloud-init.yaml", {}))
  demo_nva_cloud_init    = base64encode(templatefile("${path.module}/templates/demo-lab-nva-cloud-init.yaml", {}))
  demo_client_cloud_init = base64encode(templatefile("${path.module}/templates/demo-lab-client-cloud-init.yaml", {}))

  sample_food_tags = merge(
    local.demo_tags,
    {
      component = "sample-food-ordering-app"
      lab       = "sre-agent-lab"
    }
  )

  sample_food_address_spaces = ["10.40.0.0/16"]
  sample_food_location       = lower(replace(var.location, " ", ""))

  # Suffix shared by all globally-unique resource names (ACR, storage, Log Analytics).
  # Sourced from random_string.suffix so every fresh deployment gets its own unique set.
  demo_suffix = random_string.suffix.result

  sample_food_names = {
    resource_group             = var.rg_sample_food
    vnet                       = "vnet-food"
    container_apps_subnet      = "snet-food-aca-infra"
    probe_subnet               = "snet-food-probe"
    route_table                = "rt-food-probe-to-firewall"
    acr                        = substr("acr${local.demo_suffix}food", 0, 50)
    pull_identity              = "id-food-pull"
    container_apps_environment = "cae-food"
    api_container_app          = "ca-food-api"
    frontend_container_app     = "ca-food-frontend"
    app_insights               = "appi-food"
    diagnostic_setting         = "diag-food-aca"
    flow_log                   = "fl-food"
    http_5xx_alert             = "alert-food-http-5xx"
  }

  sample_food_images = {
    api      = "grubify-api"
    frontend = "grubify-frontend"
    tag      = "latest"
  }

  sample_food_api_placeholder_image      = "${local.sample_food_names.acr}.azurecr.io/grubify-api:v1.0.0"
  sample_food_frontend_placeholder_image = "${local.sample_food_names.acr}.azurecr.io/grubify-frontend:v1.0.0"
}
