# Evidence collection and analysis

## Collection

### 1. Hierarchy tree

Retain node IDs, parent relationships and visible child types. Do not interpret inaccessible child nodes as empty. Keep approval exclusions visible rather than recursively querying outside the authorized subtree.

```azurecli
az account management-group show --subscription "<subscription_id>" --name "<management_group_id>" --expand --recurse --output json
```

### 2. Policy assignments and exemptions by node

Repeat per approved node. Retain assignment scope, definition ID, parameters, enforcementMode, notScopes and exemption references. Distinguish returned ancestor assignments from direct node assignments.

```azurecli
az policy assignment list --subscription "<subscription_id>" --scope "<scope_id>" --output json
az policy exemption list --subscription "<subscription_id>" --scope "<scope_id>" --output json
```

### 3. Role assignments by node

Retain full scopes and assignment IDs to mark direct versus inherited and avoid duplicate role counts.

```azurecli
az role assignment list --subscription "<subscription_id>" --scope "<scope_id>" --include-inherited --fill-principal-name false --output json
```

### 4. Referenced policy or initiative definition

Accept only Microsoft.Authorization/policyDefinitions or policySetDefinitions IDs from collected assignments. Expand initiative references with approved definition reads and preserve parameters before comparing effects.

```azurecli
az resource show --subscription "<subscription_id>" --ids "<policy_definition_id>" --api-version 2023-04-01 --output json
```

## Analysis rules

1. Build the hierarchy adjacency tree and count both direct child subscriptions and all descendant subscriptions per group, clearly labeling the two counts.
2. Flag groups with no visible child groups or subscriptions only when the group read is complete. A subtree root is not necessarily the tenant root.
3. Flag subscriptions directly beneath the actual tenant root only when root identity and membership are in approved evidence; otherwise mark the root placement check Not assessed.
4. List direct and inherited policies and role assignments per node, preserving scope and condition. Exemptions and notScopes can change applicability.
5. For potential policy conflicts resolve definitions, initiative references, parameter values, aliases, applicable resource conditions, effects and enforcement modes. Prove incompatible constraints on the same applicable resource set, such as disjoint allowed location sets, before asserting conflict.
6. Different policy names or a child audit alongside a parent deny are not automatically conflicts. Unsupported policy semantics yield a review candidate with the exact unresolved expression, not a definitive conclusion.

## Known limits

- Reader visibility can be partial and cannot prove tenant wide emptiness or completeness.
- General Azure Policy conflict determination requires expression and parameter evaluation; text differences alone are not conflicts.

## Expected validation cases

- Healthy: an approved nonempty subtree with consistent applicable allowed locations reports no conflict.
- Finding: a complete root read shows a direct child subscription and proven disjoint enforced location constraints at parent and child.
- Denied or missing: hidden children cannot produce an empty group verdict, and unreadable definitions leave conflict status unknown.

## Sources

- [Management group hierarchy reads](https://learn.microsoft.com/en-us/cli/azure/account/management-group?view=azure-cli-latest) (consulted 2026-10-21).
- [Hierarchy and policy/RBAC inheritance](https://learn.microsoft.com/en-us/azure/governance/management-groups/overview) (consulted 2026-10-21).
- [Inherited role assignment sources](https://learn.microsoft.com/en-us/cli/azure/role/assignment?view=azure-cli-latest) (consulted 2026-10-21).
- [Definition resource reads](https://learn.microsoft.com/en-us/cli/azure/resource?view=azure-cli-latest) (consulted 2026-10-21).
