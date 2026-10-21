# Evidence collection and analysis

## Collection

### 1. Read state and inherited assignment inventories

Enumerate every approved ancestor as well as the target and relevant child scopes, then filter applicability and deduplicate assignment IDs. Continue state and assignment pages or next-token; respect Retry-After. Capture each evaluation timestamp and do not trigger a scan. Missing ancestor access means effective assignment count is partial.

```powershell
az policy state list --subscription $SUB --all --output json
foreach ($SCOPE in $APPROVED_SCOPES) {
 az policy assignment list --subscription $SUB --scope $SCOPE --disable-scope-strict-match true --output json
}
```

### 2. Compare exact resource and policy evaluation keys

Use only snapshots with identical approved scope and complete manifests. If prior snapshot is absent, omit this comparison and emit null transitions. Missing old key means newly observed, not verified newly noncompliant. Normalize timestamps to UTC before comparison if offsets differ.

```python
import json
from pathlib import Path
def latest(path):
    out={}
    for x in json.loads(Path(path).read_text(encoding='utf-8')):
        key=(x['resourceId'].lower(),x['policyAssignmentId'].lower(),x.get('policyDefinitionReferenceId',''),x['policyDefinitionId'].lower())
        if key not in out or x['timestamp']>out[key]['timestamp']: out[key]=x
    return out
now=latest('policy-current.json'); old=latest('policy-previous.json')
changes=[]
for key,r in now.items():
    before=old.get(key)
    if r.get('complianceState')=='NonCompliant' and before and before.get('complianceState')!='NonCompliant': changes.append({'resource_id':r['resourceId'],'assignment_id':r['policyAssignmentId'],'previous_state':before.get('complianceState'),'current_state':'NonCompliant'})
print(json.dumps(changes,indent=2))
```

## Analysis rules

1. Select latest state per resource, assignment, definition reference and definition ID, retaining stale evaluation ages and unknown states.
2. Count distinct assigned definitions or initiatives separately from assignment count and evaluated resource count. State which meaning of total policies is reported.
3. Compute compliant and noncompliant resource totals with a documented resource rollup where any applicable NonCompliant takes precedence. Show Exempt, Unknown and NotStarted separately.
4. Rank top ten policies by distinct noncompliant resource count, including initiative reference context.
5. Only call a resource became noncompliant in seven days when a complete earlier state shows a different assessed state. Compare week percentages using consistent denominators and report scope changes.

## Known limits

- Policy evaluation is asynchronous and current states do not provide a complete seven day transition history.
- Missing prior snapshots or ancestor access prevents a complete trend or effective assignment count.

## Expected validation cases

- Healthy: complete comparable snapshots show stable compliance with explicit exempt denominator.
- Finding: previously Compliant resource is now NonCompliant under the same assignment and definition reference.
- Denied or missing: no prior snapshot leaves weekly_change and verified_transitions null, not zero.

## Sources

- [Read policy states and evaluation intervals](https://learn.microsoft.com/en-us/cli/azure/policy/state?view=azure-cli-latest) (consulted 2026-10-21).
- [Applicable and inherited policy assignments](https://learn.microsoft.com/en-us/cli/azure/policy/assignment?view=azure-cli-latest) (consulted 2026-10-21).
