# Consumption environment without VNet integration: the environment uses
# Azure-managed networking and reaches Azure SQL over its public endpoint.
resource "azurerm_container_app_environment" "main" {
  name                       = local.names.container_apps_environment
  location                   = azurerm_resource_group.main.location
  resource_group_name        = azurerm_resource_group.main.name
  logs_destination           = "log-analytics"
  log_analytics_workspace_id = var.log_analytics_workspace_id
  public_network_access      = "Enabled"
  tags                       = local.resource_tags

  workload_profile {
    name                  = "Consumption"
    workload_profile_type = "Consumption"
  }
}

# The ingress is public and unauthenticated by Terraform. Configure Microsoft
# Entra authentication manually before connecting Azure SRE Agent; see the
# SQL Server MCP deployment guide in Student/Resources/sql-server-mcp.
resource "azurerm_container_app" "sql_mcp" {
  name                         = local.names.container_app
  container_app_environment_id = azurerm_container_app_environment.main.id
  resource_group_name          = azurerm_resource_group.main.name
  revision_mode                = "Single"
  workload_profile_name        = "Consumption"
  tags                         = local.resource_tags

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.sql_mcp.id]
  }

  secret {
    name  = "sql-connection-string"
    value = local.sql_mcp_connection_string
  }

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
    # A single replica keeps MCP sessions and instance-local plan resources
    # on one instance.
    min_replicas = 1
    max_replicas = 1

    container {
      name   = "sql-server-mcp"
      image  = var.sql_mcp_image
      cpu    = 0.5
      memory = "1Gi"

      env {
        name        = "MCPMSSQL_CONNECTION_STRING"
        secret_name = "sql-connection-string"
      }

      env {
        name  = "MCPMSSQL_DESCRIPTION"
        value = "SQL Server DBA workshop database"
      }

      env {
        name  = "MCPMSSQL_REQUIRE_AZURE_MANAGED_IDENTITY"
        value = "true"
      }

      env {
        name  = "MCPMSSQL_TRANSPORT"
        value = "http"
      }

      env {
        name  = "MCPMSSQL_QUERY_MAX_ROWS"
        value = "250"
      }

      env {
        name  = "MCPMSSQL_QUERY_COMMAND_TIMEOUT_SECONDS"
        value = "30"
      }

      env {
        name  = "MCPMSSQL_QUERY_MAX_OUTPUT_BYTES"
        value = "262144"
      }

      env {
        name  = "MCPMSSQL_ANALYZE_COMMAND_TIMEOUT_SECONDS"
        value = "30"
      }

      liveness_probe {
        transport = "HTTP"
        path      = "/healthz"
        port      = 8080

        initial_delay           = 10
        interval_seconds        = 10
        timeout                 = 5
        failure_count_threshold = 3
      }
    }
  }
}
