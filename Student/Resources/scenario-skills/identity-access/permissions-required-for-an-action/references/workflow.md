# Evidence collection and analysis

## Collection

### 1. Provider operation metadata

Match exact provider operation names and isDataAction where returned. Operation display text alone is not proof of all permissions required by a compound workflow.

```azurecli
az provider operation show --subscription "<subscription_id>" --namespace "<provider_namespace>" --output json
```

### 2. Candidate role definitions

Retain roleType, permissions and assignable scopes. Include built in and custom roles in evidence, but identify built in candidates explicitly.

```azurecli
az role definition list --subscription "<subscription_id>" --scope "<scope_id>" --output json
```

### 3. Local minimum permission draft

Run only after matching supplied arrays to provider metadata and reviewing dependencies. The definition's assignable scope is the enclosing resource group or subscription; the intended assignment can still be the narrower resource scope. Creates a local JSON proposal only. Host enforcement must restrict paths, prohibit role writes and substitute validated JSON arrays as escaped data rather than arbitrary source text.

```python
import json, re, uuid
from pathlib import Path
root = Path.cwd().resolve()
p = (root / '<artifact_path>').resolve()
assert root in p.parents and not p.exists() and '<' not in str(p)
scope = '<scope_id>'
assert re.fullmatch(r'/subscriptions/[0-9a-fA-F-]{36}(?:/resourceGroups/[A-Za-z0-9_.()-]+)?(?:/providers/[A-Za-z0-9_./()-]+)?', scope)
uuid.UUID(scope.split('/')[2])
parts = scope.split('/')
assignable_scope = '/'.join(parts[:5]) if len(parts) >= 5 and parts[3].lower() == 'resourcegroups' else '/'.join(parts[:3])
actions = json.loads('<required_actions_json>')
data_actions = json.loads('<required_data_actions_json>')
assert isinstance(actions, list) and isinstance(data_actions, list) and actions + data_actions
assert all(isinstance(a, str) and re.fullmatch(r'[A-Za-z0-9.]+/[A-Za-z0-9./]+', a) for a in actions + data_actions)
draft = {'Name': 'Scoped operation role draft', 'IsCustom': True, 'Description': 'Review before creation. Intended assignment scope: ' + scope, 'Actions': actions, 'NotActions': [], 'DataActions': data_actions, 'NotDataActions': [], 'AssignableScopes': [assignable_scope]}
p.parent.mkdir(parents=True, exist_ok=True)
with p.open('x', encoding='utf-8') as handle:
    json.dump(draft, handle, indent=2)

```

## Analysis rules

1. Translate the stated operation into exact provider actions, distinguishing control plane and data plane. For multi step workflows enumerate dependent read and action permissions; if documentation or evidence is missing return an incomplete mapping rather than claim a minimum.
2. Expand candidate role wildcard permissions against provider operation metadata and subtract NotActions and NotDataActions in their own planes. These exclusions are not deny assignments.
3. Keep roles that cover all required actions and are assignable at the target scope. Rank by excess permission count and scope breadth, reporting ties and any sensitive unrelated grants.
4. If no exact built in permission match exists, generate the reviewed local custom role JSON with only confirmed actions and narrow assignable scope. An existing broader role can be an alternative but must be labeled broader.
5. Check ABAC conditions, deny assignments, resource locks, PIM and provider specific authorization independently. A matching role is not proof the caller can execute the operation.
6. Validate JSON syntax and compare the draft permission set against the approved action list. An administrator must review and approve creation and assignment separately; this workflow executes neither.

## Known limits

- Provider operation metadata does not document every prerequisite for compound tasks or service data plane policies.
- Role coverage does not override locks, deny assignments, conditions or PIM activation requirements.

## Expected validation cases

- Healthy: an exact required read action matches a scoped built in role with no omitted dependency.
- Finding: no exact built in role exists, so the validated custom JSON contains only approved exact action names.
- Denied or missing: unreadable provider operations or an ambiguous requested action leaves minimum_mapping_status incomplete and blocks a definitive role draft.

## Sources

- [Role action and data action evaluation](https://learn.microsoft.com/en-us/azure/role-based-access-control/role-definitions) (consulted 2026-10-21).
- [Custom role JSON and assignable scope constraints](https://learn.microsoft.com/en-us/azure/role-based-access-control/custom-roles) (consulted 2026-10-21).
- [Provider operation metadata command](https://learn.microsoft.com/en-us/cli/azure/provider/operation?view=azure-cli-latest) (consulted 2026-10-21).
- [Scope and role assignment boundaries](https://learn.microsoft.com/en-us/cli/azure/role/assignment?view=azure-cli-latest) (consulted 2026-10-21).
- [Azure resource operations context](https://learn.microsoft.com/en-us/cli/azure/resource?view=azure-cli-latest) (consulted 2026-10-21).
