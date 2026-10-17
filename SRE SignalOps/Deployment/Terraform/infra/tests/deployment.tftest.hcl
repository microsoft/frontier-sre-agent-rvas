mock_provider "azurerm" {
  mock_data "azurerm_client_config" {
    defaults = {
      subscription_id = "00000000-0000-0000-0000-000000000001"
      object_id       = "00000000-0000-0000-0000-000000000002"
      tenant_id       = "00000000-0000-0000-0000-000000000003"
    }
  }
  mock_data "azurerm_subscription" {
    defaults = {
      subscription_id = "00000000-0000-0000-0000-000000000001"
      tenant_id       = "00000000-0000-0000-0000-000000000003"
      id              = "/subscriptions/00000000-0000-0000-0000-000000000001"
    }
  }
  mock_data "azurerm_container_registry" {
    defaults = {
      id           = "/subscriptions/00000000-0000-0000-0000-000000000001/resourceGroups/rg-registry/providers/Microsoft.ContainerRegistry/registries/signalopstest"
      login_server = "signalopstest.azurecr.io"
    }
  }
  mock_resource "azurerm_resource_group" {
    defaults = {
      id = "/subscriptions/00000000-0000-0000-0000-000000000001/resourceGroups/rg-test"
    }
  }
  mock_resource "azurerm_container_app_environment" {
    defaults = {
      default_domain = "test.uksouth.azurecontainerapps.io"
    }
  }
}
mock_provider "azapi" {}
mock_provider "random" {}

variables {
  container_registry_name           = "signalopstest"
  container_registry_resource_group = "rg-registry"
  vm_admin_password                 = "Offline-Test-Only!42"
  berlin_mcp_auth_token             = "offline-test-token-not-a-real-secret-42"
  container_images = {
    grubify_api      = "signalopstest.azurecr.io/signalops/grubify-api@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    grubify_frontend = "signalopstest.azurecr.io/signalops/grubify-frontend@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    lisbon           = "signalopstest.azurecr.io/signalops/lisbon@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    berlin           = "signalopstest.azurecr.io/signalops/berlin@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    berlin_mcp       = "signalopstest.azurecr.io/signalops/berlin-mcp@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    chaos_control    = "signalopstest.azurecr.io/signalops/chaos@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    vm_health        = "signalopstest.azurecr.io/signalops/health@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
  }
}

run "review_gated_agent_plan" {
  command = plan

  assert {
    condition     = azapi_resource.agent.body.properties.actionConfiguration.mode == "Review"
    error_message = "Agent write actions must require approval."
  }
  assert {
    condition     = length(azurerm_role_assignment.agent_workload) == 9 && azurerm_role_assignment.agent_monitoring.role_definition_name == "Monitoring Reader"
    error_message = "Agent write scope must be limited to the nine lab resource groups."
  }
  assert {
    condition     = output.mission_context.AZURE_RESOURCE_GROUP == var.rg_sample_food
    error_message = "Mission context must target this deployment."
  }
}
