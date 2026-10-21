# Evidence collection and analysis

## Collection

### 1. Retrieve actual policy catalog

Follow pagination tokens if present and respect Retry-After. Normalize REST properties versus flattened CLI output, then retain only policyType BuiltIn. Preserve exact definition IDs, metadata, policyRule and parameters.

```powershell
az policy definition list --subscription $SUB --output json
```

### 2. Rank literal candidates locally before semantic review

Use this concrete shortlist route, then inspect the actual conditions and effect parameter values of candidates. Select the final top five by resource applicability and enforcement fit, not keyword count alone. Verify exact definitions by ID using an approved GET if catalog content was truncated.

```python
import json,re
from pathlib import Path
spec=json.loads(Path('policy-requirement.json').read_text(encoding='utf-8')); words=set(re.findall(r'[a-z0-9]+',spec['requirement'].lower()))
out=[]
for d in json.loads(Path('policy-catalog.json').read_text(encoding='utf-8')):
    p=d.get('properties',d)
    if p.get('policyType')!='BuiltIn': continue
    text=' '.join([p.get('displayName',''),p.get('description',''),json.dumps(p.get('policyRule',{}))]).lower()
    score=sum(w in text for w in words)
    out.append({'policy_id':d['id'],'display_name':p.get('displayName'),'description':p.get('description'),'effect_expression':p.get('policyRule',{}).get('then',{}).get('effect'),'parameters':p.get('parameters',{}),'metadata':p.get('metadata',{}),'literal_score':score})
print(json.dumps(sorted(out,key=lambda d:(-d['literal_score'],d['policy_id']))[:20],indent=2))
```

## Analysis rules

1. Match actual resource type, alias conditions and policy mode to the requirement; a matching display name is not enough.
2. Resolve parameterized effect to allowedValues and defaultValue. State whether audit, deny, modify or deployIfNotExists is actually available.
3. Show top five with exact policy ID, display name, description, effect options and required custom parameter values.
4. Exclude or flag deprecated and preview definitions using returned metadata and exact version evidence. Do not equate old creation date with deprecation.
5. If no built in meets the requirement, say so and explain the missing capability rather than claiming a partial match is full enforcement.

## Known limits

- Built in catalogs and versions change over time.
- Keyword ranking is only a candidate generator; actual rule conditions determine semantic fit.

## Expected validation cases

- Healthy: exact resource and condition match supports desired deny effect with reviewed parameters.
- Finding: highest keyword match only audits and cannot enforce the requested behavior.
- Denied or missing: catalog retrieval incomplete means ranking is Partial and no claim of exhaustive best fit.

## Sources

- [Read policy definitions and versions](https://learn.microsoft.com/en-us/cli/azure/policy/definition?view=azure-cli-latest) (consulted 2026-10-21).
- [Definition conditions, effects and parameters](https://learn.microsoft.com/en-us/azure/governance/policy/concepts/definition-structure-basics) (consulted 2026-10-21).
