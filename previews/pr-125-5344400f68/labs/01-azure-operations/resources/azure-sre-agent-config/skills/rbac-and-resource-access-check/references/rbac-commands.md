# RBAC Command And Template Reference

Copy-ready commands and Terraform for diagnosing and remediating access failures. Everything here
is a recommendation to return to a human, not an action to take autonomously, unless the active
trigger explicitly permits the exact change.

## Least-privilege role map

| Scope | Role | Purpose |
| --- | --- | --- |
| Project resource group | Reader | Discover resources and properties. |
| Project resource group or workspace | Log Analytics Reader | Query workspace and log data. |
| Project resource group | Monitoring Reader | Read metrics and monitoring data. |
| Subscription | Monitoring Contributor | Only when the alert acknowledge and close lifecycle is required. |
| Project resource group | Contributor | Avoid by default; only for controlled privileged scenarios. |

## Read-only diagnostics

### Identify the current account

```bash
az account show --output table
```

### List every role assignment for the agent principal

```bash
az role assignment list \
  --assignee <sre-agent-principal-id> \
  --all \
  --output table
```

### Check role assignments at a specific scope

```bash
az role assignment list \
  --assignee <sre-agent-principal-id> \
  --scope <scope-resource-id> \
  --output table
```

## Recommended assignments

Do not run these automatically unless explicitly approved.

### Reader on the project resource group

```bash
az role assignment create \
  --assignee <sre-agent-principal-id> \
  --role Reader \
  --scope /subscriptions/<subscription-id>/resourceGroups/<resource-group-name>
```

### Log Analytics Reader on the project resource group

```bash
az role assignment create \
  --assignee <sre-agent-principal-id> \
  --role "Log Analytics Reader" \
  --scope /subscriptions/<subscription-id>/resourceGroups/<resource-group-name>
```

## Terraform pattern

Recommend this when the team wants RBAC managed as infrastructure as code, so the grant is
reviewable and reproducible instead of applied by hand.

```hcl
resource "azurerm_role_assignment" "sre_agent_reader" {
  scope                = azurerm_resource_group.demo.id
  role_definition_name = "Reader"
  principal_id         = var.sre_agent_principal_id
}
```
