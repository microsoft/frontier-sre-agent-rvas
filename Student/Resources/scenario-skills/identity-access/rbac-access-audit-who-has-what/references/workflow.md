# Evidence collection and analysis

## Collection

### 1. Direct subscription and child assignments

Retain scope, principalType, principalId, roleDefinitionId, condition and assignment ID. --all expands assignments only in this subscription.

```azurecli
az role assignment list --subscription "<subscription_id>" --all --fill-principal-name false --output json
```

### 2. Parent sources and role permissions

Run for the subscription and selected child scopes. Compare normalized assignment scope with assessed scope to label direct or inherited and retain parent assignment ID.

```azurecli
az role assignment list --subscription "<subscription_id>" --scope "<scope_id>" --include-inherited --fill-principal-name false --output json
az role definition list --subscription "<subscription_id>" --scope "<scope_id>" --output json
```

### 3. Assigned principal existence

Read only in the explicitly approved tenant. Retain HTTP status and request ID separately from stdout. A 403, timeout or unsupported foreign principal lookup is unknown, not a missing principal. Retry a confirmed 404 after propagation delay before calling it an orphan candidate.

```azurecli
az rest --method get --subscription "<subscription_id>" --url 'https://graph.microsoft.com/v1.0/<directory_collection>/<principal_id>?$select=id,displayName' --output json
```

## Analysis rules

1. Deduplicate assignments by ID and join role definitions by roleDefinitionId, not display name. Output principal ID even when display name cannot be obtained.
2. Label source direct when assignment scope equals assessed scope, otherwise inherited only if scope ancestry is demonstrated. A child assignment is not inherited upward.
3. Flag built in Owner and Contributor at subscription scope using resolved definition identity; also report equivalent broad custom roles after permission inspection.
4. Flag direct individual user assignments as governance review candidates, not automatically invalid. Preserve approved emergency and exceptional access rationale.
5. Classify deleted principal only after an authorized typed Graph lookup returns a repeatable 404 for the correct tenant and expected object type. Foreign groups and managed identities can need additional context.
6. State that this is an assignment inventory, not a full effective access calculation: group membership, PIM state, deny assignments and data plane access may need separate analysis.

## Known limits

- Directory permission or tenant failures do not prove a principal has been deleted.
- An assignment list alone cannot establish a user's complete effective or eligible access.

## Expected validation cases

- Healthy: group Reader assignment at an approved resource group has no broad access flag.
- Finding: an individual user has a direct subscription Owner assignment and receives both review flags.
- Denied or missing: Graph 403 leaves principal existence unknown; repeatable authorized 404 yields an orphan candidate only.

## Sources

- [Assignment scope, inheritance and Graph name lookup](https://learn.microsoft.com/en-us/cli/azure/role/assignment?view=azure-cli-latest) (consulted 2026-10-21).
- [Role permission semantics](https://learn.microsoft.com/en-us/azure/role-based-access-control/role-definitions) (consulted 2026-10-21).
- [Directory read permissions and replication delays](https://learn.microsoft.com/en-us/graph/api/user-list?view=graph-rest-1.0) (consulted 2026-10-21).
