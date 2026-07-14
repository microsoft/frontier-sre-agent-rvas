# rbac-and-resource-access-check

Use this skill when Azure SRE Agent cannot see Azure resources, cannot query Log Analytics, cannot read monitoring data, cannot list Storage blobs, cannot use Resource Graph, or needs temporary elevation through On-Behalf-Of authorization.

## Builder Upload Settings

| Field | Value |
| --- | --- |
| Skill name | `rbac-and-resource-access-check` |
| Primary purpose | Diagnose Azure SRE Agent access, managed identity permissions, user roles and least-privilege RBAC gaps. |
| Recommended tools | `RunAzCliReadCommands`, `GetAzCliHelp`, `MicrosoftLearnMCP` |
| Recommended knowledge files | `azure-sre-agent/azure-sre-agent-implementation-guide.md`, `documentation/deployment-guide.md`, `documentation/terraform-design.md` |
| Default run mode | Review for any RBAC change; read-only diagnostics only by default. |

## Trigger Conditions

Load this skill when:

- The agent says it cannot see resources.
- KQL query fails with authorization errors.
- Azure CLI read commands return 403.
- Resource Graph returns partial or empty results.
- Storage blob listing fails.
- An action asks for OBO approval.
- The user asks which role to grant to the SRE Agent managed identity.
- A response plan or scheduled task cannot run because of missing permissions.

## Access Model

Azure SRE Agent access has three different layers. Diagnose the right layer.

| Layer | Controls | Examples |
| --- | --- | --- |
| User roles on SRE Agent | What users can do with the agent. | SRE Agent Reader, Standard User, Administrator. |
| Agent permissions on Azure resources | What the managed identity can access. | Reader, Log Analytics Reader, Monitoring Reader. |
| Run mode | Whether the agent asks before acting. | Review or Autonomous per response plan/task. |

## Recommended Least-Privilege Roles

| Scope | Role | Purpose |
| --- | --- | --- |
| Project resource group | Reader | Discover resources and properties. |
| Project resource group or workspace | Log Analytics Reader | Query workspace/log data. |
| Project resource group | Monitoring Reader | Read metrics and monitoring data. |
| Subscription | Monitoring Contributor | Only if alert acknowledge/close lifecycle is required. |
| Project resource group | Contributor | Avoid by default; only controlled Privileged scenarios. |

## Non-Goals

- Do not assign broad Contributor or Owner without explicit human approval.
- Do not grant Microsoft Graph permissions unless a concrete Graph workflow is documented.
- Do not use OBO as a substitute for durable least-privilege RBAC.
- Do not modify role assignments automatically unless an approved run mode and change process allow it.

## Procedure

1. Identify the failing operation and exact error.
2. Determine whether the failure is user-role, managed-identity RBAC, data-plane RBAC, run-mode, or external connector permission.
3. Identify the Azure SRE Agent managed identity principal ID.
4. Identify the intended scope: agent resource, project resource group, workspace, Storage Account, or subscription.
5. List current role assignments for the principal.
6. Compare current roles to required least-privilege roles.
7. Recommend the narrowest missing role at the narrowest scope.
8. If a write operation is requested and permissions are absent, explain OBO and require SRE Agent Administrator approval.
9. Return exact CLI/Terraform examples as recommendations, not automatic changes.

## Azure CLI Read Command Patterns

### Get Current Account

```bash
az account show --output table
```

### List Role Assignments For Agent Principal

```bash
az role assignment list \
  --assignee <sre-agent-principal-id> \
  --all \
  --output table
```

### Check Role Assignments At Scope

```bash
az role assignment list \
  --assignee <sre-agent-principal-id> \
  --scope <scope-resource-id> \
  --output table
```

### Recommended Reader Assignment Command

Do not run automatically unless explicitly approved.

```bash
az role assignment create \
  --assignee <sre-agent-principal-id> \
  --role Reader \
  --scope /subscriptions/<subscription-id>/resourceGroups/<resource-group-name>
```

### Recommended Log Analytics Reader Assignment Command

```bash
az role assignment create \
  --assignee <sre-agent-principal-id> \
  --role "Log Analytics Reader" \
  --scope /subscriptions/<subscription-id>/resourceGroups/<resource-group-name>
```

## Terraform Recommendation Pattern

Recommend this only when the team wants RBAC managed as IaC.

```hcl
resource "azurerm_role_assignment" "sre_agent_reader" {
  scope                = azurerm_resource_group.demo.id
  role_definition_name = "Reader"
  principal_id         = var.sre_agent_principal_id
}
```

## OBO Guidance

Use OBO only when:

- The agent is in Reader-level permission mode.
- A one-time privileged operation is requested.
- A SRE Agent Administrator with work/school Entra ID account approves.
- The agent cannot perform the operation with its managed identity.

Explain clearly that OBO permissions are not retained; the agent returns to its managed identity after the operation.

## Evidence Required

- Error message and failing operation.
- Agent managed identity principal ID, if available.
- User role in SRE Agent, if relevant.
- Azure resource scope.
- Current role assignments.
- Missing role and minimum viable scope.
- Whether OBO is required or durable RBAC is preferred.

## Output Format

```text
Access issue: <short description>
Failing operation: <query/command/action>
Identity involved: <user | SRE Agent managed identity | connector identity>
Scope: <resource/resource group/subscription>
Current permissions: <roles found or unknown>
Missing permission: <role/action/data action>
Recommended fix: <least-privilege role + scope>
Execution mode: Read-only recommendation | Review-mode RBAC change | OBO approval required
References:
- <official RBAC/SRE Agent URL>
```

## Escalation

Escalate when:

- Owner/User Access Administrator is required.
- Cross-subscription or cross-tenant access is involved.
- Microsoft Graph application permissions are requested.
- The requested role is Contributor, Owner or broad data-plane access.
- Personal Microsoft accounts are involved in OBO.

## Official Sources

- SRE Agent permissions: https://learn.microsoft.com/en-us/azure/sre-agent/permissions
- Manage SRE Agent permissions: https://learn.microsoft.com/en-us/azure/sre-agent/manage-permissions
- SRE Agent user roles: https://learn.microsoft.com/en-us/azure/sre-agent/user-roles
- Run modes: https://learn.microsoft.com/en-us/azure/sre-agent/run-modes
- Azure RBAC overview: https://learn.microsoft.com/en-us/azure/role-based-access-control/overview