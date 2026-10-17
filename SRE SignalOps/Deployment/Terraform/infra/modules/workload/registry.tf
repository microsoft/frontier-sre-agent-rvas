resource "azurerm_user_assigned_identity" "image_pull" {
  name                = "uai-signalops-image-pull"
  location            = azurerm_resource_group.sample_food.location
  resource_group_name = azurerm_resource_group.sample_food.name
  tags                = local.resource_tags

  lifecycle {
    precondition {
      condition     = alltrue([for image in values(var.container_images) : startswith(image, "${var.container_registry_login_server}/")])
      error_message = "Every application image must belong to the selected existing container registry."
    }
  }
}

resource "azurerm_role_assignment" "image_pull" {
  scope                            = var.container_registry_id
  role_definition_name             = var.registry_pull_role
  principal_id                     = azurerm_user_assigned_identity.image_pull.principal_id
  principal_type                   = "ServicePrincipal"
  skip_service_principal_aad_check = true
}
