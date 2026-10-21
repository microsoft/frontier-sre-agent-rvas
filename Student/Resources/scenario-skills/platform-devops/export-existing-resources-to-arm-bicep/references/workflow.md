# Evidence collection and analysis

## Collection

### 1. Inventory and export only selected resources

Persist raw output only to an approved private local evidence file after explicit export consent. This export action is nonmutating but may reveal sensitive configuration; do not publish raw output. Verify selected IDs belong to the approved group, check resource count and export errors, and follow supported export limits. Honor Retry-After. Do not call listKeys, listSecrets or retrieve passwords to fill omitted values.

```powershell
az resource list --subscription $SUB --resource-group $RG --output json
az group export --subscription $SUB --name $RG --resource-ids $RESOURCE_IDS --include-parameter-default-value --output json
```

### 2. Generate sanitized parameter and resource drafts locally

Parameterization review must explicitly cover names, SKUs and locations by actual JSON paths and provider schema. Do not automatically strip every id or name because some are writable references. Remove provider specific read only properties using an explicit reviewed per type patch, then scan scalar values for connection strings, tokens and secrets as well as sensitive key names. The sample key redaction is only one defense, not proof of complete sanitization. Secret parameters have no raw current value or default; use an approved Key Vault reference or require secure runtime injection.

```python
import json,re
from pathlib import Path
s=json.loads(Path('approved-export-review.json').read_text(encoding='utf-8')); t=json.loads(Path('private-export.json').read_text(encoding='utf-8')); t=t.get('template',t)
assert s['resource_type_schemas_reviewed'] and s['dependency_map_reviewed']
params=t.setdefault('parameters',{}); values={}
for n,p in params.items():
    secret=p.get('type','').lower() in ('securestring','secureobject') or re.search(s['sensitive_name_pattern'],n,re.I)
    if secret: p.pop('defaultValue',None)
    elif 'defaultValue' in p: values[n]={'value':p.pop('defaultValue')}
for change in s['parameterizations']:
    r=t['resources'][change['resource_index']]; node=r; keys=change['path']
    for k in keys[:-1]: node=node[k]
    old=node[keys[-1]]; name=change['parameter_name']; assert name not in params
    params[name]={'type':change['parameter_type']}; node[keys[-1]]="[parameters('"+name+"')]"
    if not change['sensitive']: values[name]={'value':old}
def clean(x):
    if isinstance(x,dict): return {k:clean(v) for k,v in x.items() if not re.search(s['sensitive_name_pattern'],k,re.I)}
    if isinstance(x,list): return [clean(v) for v in x]
    return x
for i,r in enumerate(t['resources']):
    for key in s['read_only_top_level_keys']: r.pop(key,None)
    r['properties']=clean(r.get('properties',{}))
    r['dependsOn']=s['reviewed_dependencies'].get(str(i),r.get('dependsOn',[]))
Path('export-reviewed.arm.json').write_text(json.dumps(t,indent=2),encoding='utf-8')
Path('export-reviewed.parameters.json').write_text(json.dumps({'$schema':'https://schema.management.azure.com/schemas/2019-04-01/deploymentParameters.json#','contentVersion':'1.0.0.0','parameters':values},indent=2),encoding='utf-8')
```

### 3. Decompile, modularize and rebuild locally

Both Bicep operations are local with the prerequisite compiler already installed. Resolve decompiler warnings manually using current type schemas. For modular output, move reviewed resource families into local modules\<provider-family>.bicep files, declare typed inputs and outputs, replace cross resource IDs with module outputs or explicit existing resource references, and rebuild the root after each move. Keep a resource ID to symbolic name mapping and compare rebuilt semantic resources and dependencies, not raw file text. A separately approved cloud what-if may be drafted but never run or deploy automatically.

```powershell
az bicep decompile --file .\export-reviewed.arm.json
az bicep build --file .\export-reviewed.arm.bicep --outfile .\export-rebuilt.arm.json
Get-Content -Raw .\export-reviewed.parameters.json | ConvertFrom-Json | ConvertTo-Json -Depth 40
Get-FileHash .\export-reviewed.arm.json -Algorithm SHA256
```

## Analysis rules

1. Treat export as a starting snapshot, not a proven redeployable backup. Record every export warning, unsupported type and omitted resource and compare selected inventory with exported resources.
2. Review the documented resource group export count limit and split by supported selections where appropriate. Azure Data Factory needs its dedicated export process; do not claim generic ARM export covers it.
3. Parameterize actual names, SKU choices and locations with nonsecret current values in the parameter file. Redact secret values in both parameters and nested resource properties before generating shareable drafts.
4. Remove read only and generated properties by resource type schema, not a global deletion of all IDs. Preserve writable dependency references and explicitly repair missing dependencies.
5. For Bicep, decompile locally, organize reviewed modules by resource family and validate their interfaces and dependencies through local build. Compilation is not a deployment or service behavior test.
6. Report artifact state Draft, local validation result, cloud validation Not run and deployed false. Include exact approved scope, expected resource diff, previous configuration evidence and redeployment recovery plan before requesting apply approval.

## Known limits

- Export schemas can be incomplete or stale, password parameters may be omitted and some resource types need dedicated manual export routes.
- Local JSON parsing and Bicep build do not establish safe redeployment, dependency completeness or secret free output without manual review.

## Expected validation cases

- Healthy: selected supported resources reconcile to sanitized draft and Bicep build succeeds with reviewed dependencies.
- Finding: unsupported export type or missing dependency is reported and prevents a deployable claim.
- Denied or missing: export action denied produces no fabricated template; secret or unavailable parameter value stays omitted and deployed=false.

## Sources

- [CLI export, resource selection, parameter defaults and limits](https://learn.microsoft.com/en-us/azure/azure-resource-manager/templates/export-template-cli) (consulted 2026-10-21).
- [Export snapshots versus deployment history](https://learn.microsoft.com/en-us/azure/azure-resource-manager/templates/export-template-portal) (consulted 2026-10-21).
- [Local Bicep decompile and build](https://learn.microsoft.com/en-us/azure/azure-resource-manager/bicep/bicep-cli) (consulted 2026-10-21).
