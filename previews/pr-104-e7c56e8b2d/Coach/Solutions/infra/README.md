# Terraform Layer

This directory manages only Azure resources that belong in Terraform state.

## Managed Resources

- `azurerm_resource_group.agent`
- `azurerm_user_assigned_identity.agent`
- `azurerm_log_analytics_workspace.agent`
- `azurerm_application_insights.agent`
- `azurerm_role_assignment.*`
- `azapi_resource.agent` for `Microsoft.App/agents@2026-01-01`
- `azapi_resource.log_analytics_connector` for `Microsoft.App/agents/connectors@2026-01-01`
- `azapi_resource.application_insights_connector` for `Microsoft.App/agents/connectors@2026-01-01`

## Direct Values Policy

This root configuration intentionally keeps values at the resource argument where they are used.

Do not add `variables.tf`, `.tfvars`, or pass-through locals just to rename literals. For a customer deployment, edit the concrete values directly in:

- `main.tf` for names, region, model, run mode, access level, sponsor group ID, and connector definitions.
- `locals.tf` for shared tags and managed scope role assignment construction.

Example flow:

```bash
terraform init
terraform plan
terraform apply
```

## Design Notes

- Keep connector secrets out of Terraform unless state storage and access controls are explicitly approved.
- Prefer `Review` mode and `Low` access for first production releases.
- Add managed resource IDs directly to `local.managed_resource_ids` only when the agent needs access beyond its own resource group.
- Add connector resources directly only when connector values are safe to keep in Terraform state.

## Validation

```bash
terraform fmt -recursive
terraform init -backend=false
terraform validate
```

## References

- https://learn.microsoft.com/en-us/azure/templates/microsoft.app/agents?pivots=deployment-language-terraform
- https://learn.microsoft.com/en-us/azure/templates/microsoft.app/agents/connectors?pivots=deployment-language-terraform
- https://registry.terraform.io/providers/Azure/azapi/latest/docs/resources/resource
- https://developer.hashicorp.com/terraform/language/style