# Evidence collection and analysis

## Collection

### 1. Source resources and target context

Account reads are prerequisite tenant/state checks, not move support evidence. Consult the official resource type move support matrix and service move guidance at execution time for every selected type.

```azurecli
az resource list --subscription "<subscription_id>" --resource-group "<source_rg>" --output json
az group show --subscription "<target_subscription_id>" --name "<target_rg>" --output json
az account show --subscription "<subscription_id>" --query '{id:id,tenant_id:tenantId,state:state}' --output json
az account show --subscription "<target_subscription_id>" --query '{id:id,tenant_id:tenantId,state:state}' --output json
```

### 2. Locks and target provider registration

Read only. Reconstruct direct and inherited locks for every selected resource and dependency. A missing provider registration is a blocker for review, never automatically registered.

```azurecli
az lock list --subscription "<subscription_id>" --output json
az lock list --subscription "<subscription_id>" --resource-group "<source_rg>" --output json
az lock list --subscription "<target_subscription_id>" --output json
az lock list --subscription "<target_subscription_id>" --resource-group "<target_rg>" --output json
az provider list --subscription "<target_subscription_id>" --output json
```

### 3. Target quota and governance

Compare additional demand for every resource family against target limits. These common usage collectors are not an exhaustive quota check for every service; unsupported quota families remain blockers until verified. Read definitions and exemptions referenced by applicable target policies.

```azurecli
az vm list-usage --subscription "<target_subscription_id>" --location "<region>" --output json
az network list-usages --subscription "<target_subscription_id>" --location "<region>" --output json
az storage account show-usage --subscription "<target_subscription_id>" --location "<region>" --output json
az policy assignment list --subscription "<target_subscription_id>" --scope "/subscriptions/<target_subscription_id>/resourceGroups/<target_rg>" --output json
az role assignment list --subscription "<subscription_id>" --all --fill-principal-name false --output json
az role assignment list --subscription "<target_subscription_id>" --scope "/subscriptions/<target_subscription_id>/resourceGroups/<target_rg>" --include-inherited --fill-principal-name false --output json
```

### 4. Local validation request and move proposal

Only writes the local draft. It does not submit even the server validation action. Validate approved IDs and safe JSON substitution in the host. Do not use az resource move --validate-only, which is not the documented move validation interface. A separately approved operator may submit validateMoveResources and poll its returned Location before any move approval.

```python
import json, re, uuid
from pathlib import Path
root = Path.cwd().resolve()
p = (root / '<artifact_path>').resolve()
assert root in p.parents and not p.exists() and '<' not in str(p)
source = str(uuid.UUID('<subscription_id>'))
target = str(uuid.UUID('<target_subscription_id>'))
source_rg, target_rg = '<source_rg>', '<target_rg>'
assert all(re.fullmatch(r'[A-Za-z0-9_.()-]{1,90}', v) for v in (source_rg, target_rg))
ids = json.loads('<resource_ids_json>')
prefix = f'/subscriptions/{source}/resourceGroups/{source_rg}/providers/'
assert isinstance(ids, list) and ids and all(isinstance(i, str) and i.lower().startswith(prefix.lower()) and '<' not in i for i in ids)
body = {'resources': ids, 'targetResourceGroup': f'/subscriptions/{target}/resourceGroups/{target_rg}'}
draft = {'status': 'DraftNotExecuted', 'validation_method': 'POST', 'validation_url': f'https://management.azure.com/subscriptions/{source}/resourceGroups/{source_rg}/validateMoveResources?api-version=2021-04-01', 'validation_body': body, 'move_cli_arguments_never_executed': ['az', 'resource', 'move', '--subscription', source, '--destination-subscription-id', target, '--destination-group', target_rg, '--ids'] + ids, 'approval_required': True, 'validation_result': None, 'rollback': 'Review reverse move feasibility, backup and restoration before approval; reverse move is not guaranteed.'}
p.parent.mkdir(parents=True, exist_ok=True)
with p.open('x', encoding='utf-8') as handle:
    json.dump(draft, handle, indent=2)

```

## Analysis rules

1. Verify both subscriptions are active and in the same tenant. Confirm each top level type supports the requested cross subscription move using current official move support and service specific guidance; reject unknown support.
2. Build dependency closure from provider references, including shared networking, disks and nested resources. Exclude child resources from the explicit top level move list where they move with parents. Unknown dependencies block a Ready recommendation.
3. Evaluate inherited/direct locks, provider registration and target service quotas for all regions and families. ReadOnly locks are a documented blocker; other lock effects require authoritative validation rather than blanket claims.
4. Compare target inherited policy effects, required tags and deny conditions, resource ID changes, source scoped role assignments and target inherited access. Role assignments do not simply transfer with moved resource IDs.
5. Generate only the local draft containing exact source, target, selected resources, validation request and never executed move arguments. Validation is a separate privileged action and the read workflow must not call it.
6. Require explicit approval for validation, capture asynchronous validation status and errors, then obtain distinct move approval with downtime/management lock impact, backups, dependency checks, owner acceptance, post move tests and a feasible rollback or restoration plan. Validation success is not a completed move.

## Known limits

- Move support and dependency requirements are resource type specific; a generic inventory cannot certify every service move.
- Server validation requires separately approved action permissions and may be asynchronous; this read assessment intentionally does not execute it.

## Expected validation cases

- Healthy: supported same tenant resources with complete dependency and quota evidence produce a draft, with validation_result still null.
- Finding: target quota shortage or ReadOnly source lock appears as a blocker and no move is executed.
- Denied or missing: unreadable target policy, unknown support or failed tenant match blocks readiness and leaves server validation unexecuted.

## Sources

- [Move checklist, changed IDs and validateMoveResources](https://learn.microsoft.com/en-us/azure/azure-resource-manager/management/move-resource-group-and-subscription) (consulted 2026-10-21).
- [Documented resource move CLI](https://learn.microsoft.com/en-us/cli/azure/resource?view=azure-cli-latest) (consulted 2026-10-21).
- [Management locks](https://learn.microsoft.com/en-us/azure/azure-resource-manager/management/lock-resources) (consulted 2026-10-21).
- [Target quota considerations](https://learn.microsoft.com/en-us/azure/azure-resource-manager/management/azure-subscription-service-limits) (consulted 2026-10-21).
