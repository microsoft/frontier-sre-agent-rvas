# Evidence collection and analysis

## Collection

### 1. Read noncompliance and existing tasks

Also list approved resource group and resource remediation scopes, using the corresponding CLI scope flags. Select show and deployment list scope to match the task's actual scope, not always RG. Complete pages and Retry-After handling. Enumerate every approved ancestor assignment and resolve definitions and initiative references with GET before deciding the effective effect.

```powershell
foreach ($SUB in $SUBS) {
 az policy state list --subscription $SUB --all --filter "ComplianceState eq 'NonCompliant'" --output json
 az policy remediation list --subscription $SUB --output json
}
foreach ($MG in $APPROVED_MGS) {
 az policy remediation list --management-group $MG --output json
}
az policy remediation show --subscription $SUB --resource-group $RG --name $TASK_NAME --output json
az policy remediation deployment list --subscription $SUB --resource-group $RG --name $TASK_NAME --output json
```

### 2. Generate per assignment and initiative reference drafts

Local candidate records must come from resolved states and actual task history. eligible_by_age means no prior task or last terminal task older than seven days, with resources still noncompliant; an active task always blocks duplicate creation. approved_scope_args must be a reviewed CLI argument array, never a shell string. If task scope includes unapproved descendants and cannot be constrained by the supported API, block generation rather than pretending a resource_ids manifest filters task execution.

```python
import json,hashlib
from pathlib import Path
plans=[]
for r in json.loads(Path('remediation-candidates.json').read_text(encoding='utf-8')):
    assert r['effective_effect'].lower() in ('modify','deployifnotexists')
    if not r['approved_scope_complete'] or not r['identity_roles_verified'] or r['active_task'] or not r['eligible_by_age']: continue
    key=r['assignment_id']+'|'+r.get('definition_reference_id','')+'|'+r['assessment_date']
    name='review-'+hashlib.sha256(key.encode()).hexdigest()[:20]
    argv=['az','policy','remediation','create','--subscription',r['subscription_id'],'--name',name,'--policy-assignment',r['assignment_id'],'--resource-discovery-mode','ExistingNonCompliant']+r['approved_scope_args']
    if r.get('definition_reference_id'): argv+=['--definition-reference-id',r['definition_reference_id']]
    plans.append({'name':name,'argv':argv,'execute':False,'requires_approval':True,'resource_ids':r['resource_ids'],'remediable_count':len(r['resource_ids'])})
Path('remediation-task-drafts.json').write_text(json.dumps(plans,indent=2),encoding='utf-8')
```

### 3. Validate local request scope and deployment impact

Review managed identity roleDefinitionIds, actual granted permissions and assignment parameters; do not grant permissions. Validate each planned CLI flag with installed command help and current API. Include canary, task resource count and parallelism limits, expected deployments, cancellation command draft and rollback limitations. Do not invoke any generated argv or trigger a compliance scan.

```powershell
Get-Content -Raw .\remediation-task-drafts.json | ConvertFrom-Json | Select-Object name,execute,requires_approval,remediable_count
Get-FileHash .\remediation-task-drafts.json -Algorithm SHA256
```

## Analysis rules

1. Resolve assignment, initiative mappings, defaults, overrides and exemptions before classifying the effective effect as remediable. Audit or deny is not eligible for remediation tasks.
2. Count distinct still noncompliant resource IDs per assignment and definition reference. An initiative requires the correct definition reference ID in each task draft.
3. Report actual existing in progress, completed and failed task statuses and deployment details. tasks_created is zero for this draft workflow and proposed_task_count is separate.
4. Do not recreate a task just because it is older than seven days if it is active or resources are now compliant. Use a stable scoped plan key and recheck immediately before any approved apply.
5. Validate identity permissions and all descendants reached by the remediation scope. Unknown roles, inaccessible ancestors or unapproved scope block a safe apply.
6. Cancellation stops further work where supported but does not reverse completed deployments or modifications; retain per resource recovery instructions.

## Known limits

- Remediation task scope may be broader than a displayed candidate resource list.
- Tasks change resources through assignment managed identities; local validation cannot prove successful deployment or automatic rollback.

## Expected validation cases

- Healthy: no noncompliant eligible resources means no proposed task.
- Finding: stale completed task and current Modify noncompliance yield one local draft with the correct initiative reference.
- Denied or missing: unverified assignment identity roles or unapproved descendant scope blocks draft apply and tasks_created remains zero.

## Sources

- [Remediation identity and eligible effects](https://learn.microsoft.com/en-us/azure/governance/policy/how-to/remediate-resources) (consulted 2026-10-21).
- [Remediation scope, task and deployment commands](https://learn.microsoft.com/en-us/cli/azure/policy/remediation?view=azure-cli-latest) (consulted 2026-10-21).
