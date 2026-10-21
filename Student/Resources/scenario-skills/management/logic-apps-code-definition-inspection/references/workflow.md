# Evidence collection and analysis

## Collection

### 1. Read the actual workflow definition

Use REST only for Microsoft.Logic/workflows Consumption IDs; do not send a Standard Microsoft.Web/sites ID to that endpoint. For Standard, read workflow.json and connections.json from the approved local package. Obtain authoritative package provenance and compare deployed revision metadata if available. Bound retry on 429 and retain denial rather than retrieving publishing credentials.

```powershell
az rest --method get --url "https://management.azure.com$LOGIC_ID`?api-version=2019-05-01" --output json
Get-ChildItem -Path .\approved-standard-package -Recurse -Filter workflow.json | Select-Object FullName
```

### 2. Walk nested actions and report structural evidence

Normalize the retrieved Consumption definition or each Standard workflow.json into workflow-definition.json. Traverse Scope, Condition, Foreach, Until and Switch branches recursively. Inspect literal inputs locally for parameterization candidates without emitting sensitive values. Do not run the workflow or connector operations.

```python
import json
from pathlib import Path
d=json.loads(Path('workflow-definition.json').read_text(encoding='utf-8')); d=d.get('properties',{}).get('definition',d.get('definition',d))
def walk(actions,prefix=''):
    for name,a in actions.items():
        path=prefix+'/'+name
        print(json.dumps({'path':path,'type':a.get('type'),'run_after':a.get('runAfter',{}),'retry_policy':a.get('inputs',{}).get('retryPolicy'),'concurrency':a.get('runtimeConfiguration',{}).get('concurrency'),'connector':a.get('inputs',{}).get('host',{})}))
        walk(a.get('actions',{}),path)
        walk(a.get('else',{}).get('actions',{}),path+'/else')
        for case,c in a.get('cases',{}).items(): walk(c.get('actions',{}),path+'/'+case)
        walk(a.get('default',{}).get('actions',{}),path+'/default')
walk(d.get('actions',{}))
```

## Analysis rules

1. Build the runAfter graph for each action scope. Check whether a failed or timed out action is handled by a downstream action or enclosing Scope handler before declaring missing error handling.
2. Inspect HTTP retryPolicy. Missing explicit policy can mean the documented default retry behavior, not no retries; flag explicit None or a business requirement that defaults do not satisfy.
3. Evaluate loop concurrency against workload ordering and downstream limits. An omitted explicit limit is a review candidate because platform defaults still exist.
4. Detect hardcoded environment endpoints, resource IDs and configuration values as parameterization candidates, but redact potential secrets and do not quote them in findings.
5. Only mark deprecated connector versions with exact official lifecycle evidence for that connector and operation. API version age alone is not deprecation.

## Known limits

- Standard local package may not match the currently deployed revision unless provenance is verified.
- Structural inspection cannot prove runtime connector availability or end to end recovery.

## Expected validation cases

- Healthy: Scope catch path handles failed actions and omitted HTTP retry uses a supported default.
- Finding: HTTP action explicitly disables retry despite required transient recovery and no enclosing failure path.
- Denied or missing: unavailable Standard deployment package leaves definition revision and inspection unassessed.

## Sources

- [Consumption workflow definition GET](https://learn.microsoft.com/en-us/rest/api/logic/workflows/get?view=rest-logic-2019-05-01) (consulted 2026-10-21).
- [Logic Apps error handling and default retry policies](https://learn.microsoft.com/en-us/azure/logic-apps/error-exception-handling) (consulted 2026-10-21).
