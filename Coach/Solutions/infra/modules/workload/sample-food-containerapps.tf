resource "azurerm_container_app_environment" "sample_food" {
  name                       = local.sample_food_names.container_apps_environment
  location                   = azurerm_resource_group.sample_food.location
  resource_group_name        = azurerm_resource_group.sample_food.name
  logs_destination           = "log-analytics"
  log_analytics_workspace_id = azurerm_log_analytics_workspace.demo.id
  infrastructure_subnet_id   = azurerm_subnet.sample_food_container_apps.id
  public_network_access      = "Enabled"
  tags                       = local.sample_food_tags

  workload_profile {
    name                  = "Consumption"
    workload_profile_type = "Consumption"
  }
}

resource "azurerm_container_app" "sample_food_api" {
  name                         = local.sample_food_names.api_container_app
  container_app_environment_id = azurerm_container_app_environment.sample_food.id
  resource_group_name          = azurerm_resource_group.sample_food.name
  revision_mode                = "Single"
  workload_profile_name        = "Consumption"
  tags                         = local.sample_food_tags

  ingress {
    external_enabled           = true
    target_port                = 8080
    transport                  = "auto"
    allow_insecure_connections = false

    traffic_weight {
      latest_revision = true
      percentage      = 100
    }
  }

  template {
    min_replicas = 1
    max_replicas = 5

    container {
      name   = "grubify-api"
      image  = "ghcr.io/microsoft/frontier-sre-agent-rvas/grubify-api:latest"
      cpu    = 0.5
      memory = "1Gi"

      env {
        name  = "ASPNETCORE_URLS"
        value = "http://+:8080"
      }

      env {
        name  = "ASPNETCORE_ENVIRONMENT"
        value = "Production"
      }

      env {
        name  = "APPLICATIONINSIGHTS_CONNECTION_STRING"
        value = azurerm_application_insights.sample_food.connection_string
      }

      env {
        name  = "AllowedOrigins__0"
        value = "https://${local.sample_food_names.frontend_container_app}.${azurerm_container_app_environment.sample_food.default_domain}"
      }
    }
  }
}

resource "azurerm_container_app" "sample_food_frontend" {
  name                         = local.sample_food_names.frontend_container_app
  container_app_environment_id = azurerm_container_app_environment.sample_food.id
  resource_group_name          = azurerm_resource_group.sample_food.name
  revision_mode                = "Single"
  workload_profile_name        = "Consumption"
  tags                         = local.sample_food_tags

  ingress {
    external_enabled           = true
    target_port                = 80
    transport                  = "auto"
    allow_insecure_connections = false

    traffic_weight {
      latest_revision = true
      percentage      = 100
    }
  }

  template {
    min_replicas = 1
    max_replicas = 3

    container {
      name   = "grubify-frontend"
      image  = "ghcr.io/microsoft/frontier-sre-agent-rvas/grubify-frontend:latest"
      cpu    = 0.25
      memory = "0.5Gi"

      env {
        name  = "REACT_APP_API_BASE_URL"
        value = "https://${azurerm_container_app.sample_food_api.ingress[0].fqdn}/api"
      }
    }
  }
}
