locals {
  parking_images = {
    lisbon        = "ghcr.io/microsoft/frontier-sre-agent-rvas/lisbon-parking-api:latest"
    berlin        = "ghcr.io/microsoft/frontier-sre-agent-rvas/berlin-parking-api:latest"
    chaos_control = "ghcr.io/microsoft/frontier-sre-agent-rvas/chaos-control:latest"
    vm_health     = "ghcr.io/microsoft/frontier-sre-agent-rvas/vm-health-control:latest"
  }
}

# ─── Resource Groups ───────────────────────────────────────────────────────────

resource "azurerm_resource_group" "parking_lisbon" {
  name     = var.rg_parking_lisbon
  location = var.location
  tags     = local.resource_tags
}

resource "azurerm_resource_group" "parking_berlin" {
  name     = var.rg_parking_berlin
  location = var.location
  tags     = local.resource_tags
}

resource "azurerm_resource_group" "parking_madrid" {
  name     = var.rg_parking_madrid
  location = var.location
  tags     = local.resource_tags
}

resource "azurerm_resource_group" "parking_paris" {
  name     = var.rg_parking_paris
  location = var.location
  tags     = local.resource_tags
}

resource "azurerm_resource_group" "parking_chaos" {
  name     = var.rg_parking_chaos
  location = var.location
  tags     = local.resource_tags
}

# ─── Chaos Control ─────────────────────────────────────────────────────────────

resource "azurerm_container_app" "chaos_control" {
  name                         = "ca-chaos-control"
  container_app_environment_id = azurerm_container_app_environment.sample_food.id
  resource_group_name          = azurerm_resource_group.parking_chaos.name
  revision_mode                = "Single"
  workload_profile_name        = "Consumption"
  tags                         = local.resource_tags


  identity {
    type = "SystemAssigned"
  }

  ingress {
    external_enabled           = true
    target_port                = 3090
    transport                  = "auto"
    allow_insecure_connections = false

    traffic_weight {
      latest_revision = true
      percentage      = 100
    }
  }

  template {
    min_replicas = 1
    max_replicas = 2

    container {
      name   = "chaos-control"
      image  = local.parking_images.chaos_control
      cpu    = 0.25
      memory = "0.5Gi"

      env {
        name  = "PORT"
        value = "3090"
      }

      env {
        name  = "NODE_ENV"
        value = "production"
      }

      liveness_probe {
        transport = "HTTP"
        path      = "/health"
        port      = 3090

        initial_delay           = 10
        interval_seconds        = 30
        failure_count_threshold = 3
      }

      readiness_probe {
        transport = "HTTP"
        path      = "/health"
        port      = 3090

        initial_delay           = 5
        interval_seconds        = 10
        failure_count_threshold = 3
      }
    }
  }
}

# ─── VM Health Control ─────────────────────────────────────────────────────────

resource "azurerm_container_app" "vm_health_control" {
  name                         = "ca-vm-health-control"
  container_app_environment_id = azurerm_container_app_environment.sample_food.id
  resource_group_name          = azurerm_resource_group.parking_chaos.name
  revision_mode                = "Single"
  workload_profile_name        = "Consumption"
  tags                         = local.resource_tags

  identity {
    type = "SystemAssigned"
  }

  ingress {
    external_enabled           = true
    target_port                = 3095
    transport                  = "auto"
    allow_insecure_connections = false

    traffic_weight {
      latest_revision = true
      percentage      = 100
    }
  }

  template {
    min_replicas = 1
    max_replicas = 2

    container {
      name   = "vm-health-control"
      image  = local.parking_images.vm_health
      cpu    = 0.25
      memory = "0.5Gi"

      env {
        name  = "PORT"
        value = "3095"
      }

      env {
        name  = "NODE_ENV"
        value = "production"
      }

      env {
        name  = "DCE_ENDPOINT"
        value = azurerm_monitor_data_collection_endpoint.vm_health.logs_ingestion_endpoint
      }

      env {
        name  = "DCR_RULE_ID"
        value = azurerm_monitor_data_collection_rule.vm_health_status.immutable_id
      }

      env {
        name  = "DCR_STREAM_NAME"
        value = "Custom-VMHealthStatus_CL"
      }

      liveness_probe {
        transport = "HTTP"
        path      = "/health"
        port      = 3095

        initial_delay           = 10
        interval_seconds        = 30
        failure_count_threshold = 3
      }

      readiness_probe {
        transport = "HTTP"
        path      = "/health"
        port      = 3095

        initial_delay           = 5
        interval_seconds        = 10
        failure_count_threshold = 3
      }
    }
  }
}

# ─── Lisbon API ────────────────────────────────────────────────────────────────

resource "azurerm_container_app" "parking_lisbon" {
  name                         = "ca-parking-lisbon"
  container_app_environment_id = azurerm_container_app_environment.sample_food.id
  resource_group_name          = azurerm_resource_group.parking_lisbon.name
  revision_mode                = "Single"
  workload_profile_name        = "Consumption"
  tags                         = local.resource_tags

  identity {
    type = "SystemAssigned"
  }

  ingress {
    external_enabled           = true
    target_port                = 3001
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
      name   = "lisbon-parking-api"
      image  = local.parking_images.lisbon
      cpu    = 0.25
      memory = "0.5Gi"

      env {
        name  = "PARKING_CITY"
        value = "Lisbon"
      }

      env {
        name  = "PARKING_NAME"
        value = "Lisbon Central Parking"
      }

      env {
        name  = "PARKING_LOCATION"
        value = "Lisbon, Portugal"
      }

      env {
        name  = "WORKSPACE_ID"
        value = azurerm_log_analytics_workspace.demo.workspace_id
      }

      env {
        name  = "LOG_TYPE"
        value = "LisbonParkingLogs"
      }

      env {
        name  = "CHAOS_CONTROL_URL"
        value = "https://${azurerm_container_app.chaos_control.ingress[0].fqdn}"
      }

      liveness_probe {
        transport = "HTTP"
        path      = "/health"
        port      = 3001

        initial_delay           = 10
        interval_seconds        = 30
        failure_count_threshold = 3
      }

      readiness_probe {
        transport = "HTTP"
        path      = "/health"
        port      = 3001

        initial_delay           = 5
        interval_seconds        = 10
        failure_count_threshold = 3
      }
    }
  }
}

# ─── Berlin API (intentionally no Log Analytics — demo observability gap) ──────

resource "azurerm_container_app" "parking_berlin" {
  name                         = "ca-parking-berlin"
  container_app_environment_id = azurerm_container_app_environment.sample_food.id
  resource_group_name          = azurerm_resource_group.parking_berlin.name
  revision_mode                = "Single"
  workload_profile_name        = "Consumption"
  tags                         = local.resource_tags

  identity {
    type = "SystemAssigned"
  }

  ingress {
    external_enabled           = true
    target_port                = 3004
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
      name   = "berlin-parking-api"
      image  = local.parking_images.berlin
      cpu    = 0.25
      memory = "0.5Gi"

      env {
        name  = "PARKING_CITY"
        value = "Berlin"
      }

      env {
        name  = "PARKING_NAME"
        value = "Berlin Central Parking"
      }

      env {
        name  = "PARKING_LOCATION"
        value = "Alexanderplatz, Berlin, Germany"
      }

      env {
        name  = "PORT"
        value = "3004"
      }

      env {
        name  = "NODE_ENV"
        value = "production"
      }

      liveness_probe {
        transport = "HTTP"
        path      = "/health"
        port      = 3004

        initial_delay           = 10
        interval_seconds        = 30
        failure_count_threshold = 3
      }

      readiness_probe {
        transport = "HTTP"
        path      = "/health"
        port      = 3004

        initial_delay           = 5
        interval_seconds        = 10
        failure_count_threshold = 3
      }
    }
  }
}
