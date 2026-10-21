# Evidence collection and analysis

## Collection

### 1. Compare historical and current configuration

Complete ARG pages and split capped activity windows, obeying Retry-After. Reject truncated or unknown previous values and detect later changes. Do not restore read only properties, secret values, identities or deleted resources automatically.

```powershell
az graph query --subscriptions $SUB --first 1000 --graph-query "resourcechanges | where properties.targetResourceId =~ '$RESOURCE_ID' | extend changed_at=todatetime(properties.changeAttributes.timestamp) | where changed_at >= datetime($START) and changed_at < datetime($END) | project id,changed_at,properties | order by changed_at asc" --output json
az resource show --subscription $SUB --ids $RESOURCE_ID --api-version $API_VERSION --output json
az monitor activity-log list --subscription $SUB --resource-id $RESOURCE_ID --start-time $START --end-time $END --max-events 10000 --output json
```

### 2. Generate a local PATCH payload and nonexecuted command

Local input keys describe reviewed evidence, not Azure response fields. This safe route only supports confirmed PATCH APIs with ETag enforcement and simple writable property paths. For PUT only, array replacement or deletion recovery, require a complete provider specific reviewed template and previous state instead; mark draft blocked rather than synthesize a dangerous payload. Validate payload against the selected provider schema and produce a plain language diff and validation probes.

```python
import json
from pathlib import Path
p=json.loads(Path('rollback-approved-properties.json').read_text(encoding='utf-8'))
assert p['method']=='PATCH' and p['etag_supported'] and p['etag']
assert p['reviewed_provider_contract'] and p['resource_id'] in p['approved_resource_ids']
body={}
for c in p['changes']:
    assert c['path'] in p['writable_paths'] and c['previous_known'] and not c['truncated']
    assert c['current_value']==c['observed_after_value'], 'Concurrent change, stop'
    node=body; parts=c['path'].split('.')
    assert parts[0]=='properties' and all(x.isidentifier() for x in parts), 'Use provider specific review for arrays or special paths'
    for part in parts[:-1]: node=node.setdefault(part,{})
    node[parts[-1]]=c['previous_value']
Path('rollback.request.json').write_text(json.dumps(body,indent=2),encoding='utf-8')
cmd=['az','rest','--method','patch','--url','https://management.azure.com'+p['resource_id']+'?api-version='+p['api_version'],'--headers','If-Match='+p['etag'],'--body','@rollback.request.json']
Path('rollback.command.json').write_text(json.dumps({'argv':cmd,'execute':False,'requires_approval':True},indent=2),encoding='utf-8')
```

### 3. Prepare validation and recovery review

Do not invoke the command array. If using a reviewed ARM template, include the exact az deployment group what-if --subscription SUB --resource-group RG --template-file rollback.arm.json command in the approval package; running that cloud preview requires explicit permission. Arbitrary PATCH has no generic what-if switch. Record prechange backup, expected postchange probes and forward recovery steps if rollback fails.

```powershell
Get-Content -Raw .\rollback.request.json | ConvertFrom-Json | ConvertTo-Json -Depth 30
Get-FileHash .\rollback.request.json -Algorithm SHA256
Get-Content -Raw .\rollback.command.json | ConvertFrom-Json | Select-Object execute,requires_approval
```

## Analysis rules

1. Identify the exact problematic change from old and new evidence; causal suspicion is not sufficient to revert unrelated later configuration.
2. Only restore verified writable prior values and compare current state to the recorded after state. Concurrent drift, missing ETag support or unknown before values blocks this generic PATCH route.
3. Validate schema, dependencies, resource locks, policy constraints and downstream effects before presenting the draft. JSON syntax validation alone is not provider validation.
4. Require explicit approval of payload hash, resource ID, risk, maintenance window, validation checks and recovery plan before any resource mutation.
5. After a separately approved apply, re-read configuration, verify workload probes and record actual outcome. A generated command is not a successful rollback.

## Known limits

- Not all Azure resource APIs support PATCH, If-Match or reversible updates.
- Truncated history, destructive deletions and secret changes cannot be safely undone by a generic inverse command.

## Expected validation cases

- Healthy: prior value is known, writable and current state unchanged, producing a local draft only.
- Finding: proposed rollback would overwrite a later change, so generation is blocked.
- Denied or missing: missing prior value, unsupported ETag or denied current GET produces no executable rollback request.

## Sources

- [Change snapshots and truncation evidence](https://learn.microsoft.com/en-us/azure/governance/resource-graph/changes/get-resource-changes) (consulted 2026-10-21).
- [ARM validation and what-if versus deployment](https://learn.microsoft.com/en-us/cli/azure/deployment/group?view=azure-cli-latest) (consulted 2026-10-21).
