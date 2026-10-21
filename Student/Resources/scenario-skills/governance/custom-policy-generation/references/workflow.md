# Evidence collection and analysis

## Collection

### 1. Discover reusable definitions and valid aliases

Inspect relevant built in policies before creating custom behavior. Follow any CLI pagination token to completion and handle Retry-After. Validate all custom fields against actual alias metadata and resource API versions; do not assume property paths are policy aliases. For modify, obtain Modifiable alias evidence using an approved Azure Policy tooling environment.

```powershell
az policy definition list --subscription $SUB --output json
az provider show --subscription $SUB --namespace $PROVIDER_NAMESPACE --expand resourceTypes/aliases --output json
```

### 2. Generate rule, parameters and nonexecuted command

The local spec is a reviewed translation of the requirement, not an unrestricted prompt. Check condition schema, alias types, parameter references, allowedValues and defaults using Azure Policy VS Code extension or approved schema validator. Run fixture evaluation for supported logical operators and document unsupported expressions; local fixture simulation is not Azure Policy engine equivalence. No create command is executed.

```python
import json,re
from pathlib import Path
s=json.loads(Path('approved-policy-spec.json').read_text(encoding='utf-8'))
assert re.fullmatch(r'[A-Za-z0-9_.-]{1,64}',s['name'])
assert s['effect'] in ('audit','deny','modify') and s['mode'] in ('All','Indexed')
assert s['aliases_verified'] and s['fixtures_reviewed']
then={'effect':s['effect']}
if s['effect']=='modify':
    assert s['modifiable_aliases_verified'] and s['details']['roleDefinitionIds'] and s['details']['operations']
    then['details']=s['details']
rule={'if':s['condition'],'then':then}
props={'displayName':s['display_name'],'description':s['description'],'mode':s['mode'],'parameters':s['parameters'],'policyRule':rule,'metadata':{'category':s['category'],'version':s['version']}}
for name,obj in [('policy.definition.json',{'properties':props}),('policy.rules.json',rule),('policy.parameters.json',s['parameters'])]: Path(name).write_text(json.dumps(obj,indent=2),encoding='utf-8')
argv=['az','policy','definition','create','--subscription',s['subscription_id'],'--name',s['name'],'--display-name',s['display_name'],'--description',s['description'],'--mode',s['mode'],'--rules','@policy.rules.json','--params','@policy.parameters.json']
Path('policy.deploy-command.json').write_text(json.dumps({'argv':argv,'execute':False,'requires_approval':True},indent=2),encoding='utf-8')
```

### 3. Validate local artifacts and approval evidence

Review a definition diff and test fixtures, policy mode applicability, modify conflictEffect and identity role requirements. Include a canary assignment plan with initial audit or DoNotEnforce where applicable, expected impact, previous version backup and rollback. Definition creation and assignment are separate operations and approvals.

```powershell
Get-Content -Raw .\policy.definition.json | ConvertFrom-Json | ConvertTo-Json -Depth 50
Get-FileHash .\policy.definition.json -Algorithm SHA256
Get-Content -Raw .\policy.deploy-command.json | ConvertFrom-Json | Select-Object execute,requires_approval
```

## Analysis rules

1. Map the actual requirement to supported resource properties and aliases. If Azure Policy cannot observe the condition, report the unsupported requirement instead of inventing an alias.
2. Choose mode and parameter types appropriate to resource applicability; Indexed is not a universal mode for all resource and child resource controls.
3. Audit and deny use condition matching; modify additionally requires supported writable aliases, valid operations, conflict behavior and reviewed identity role requirements.
4. Validate fixtures with compliant, violating, missing property and out of scope resources. Do not call JSON parsing an actual policy engine test.
5. Do not claim a universal Microsoft naming convention. Use the customer's approved name, meaningful display name, category, description and semantic version.
6. Preserve generated, validated, approved and deployed states separately; no policy definition, assignment or identity grant is created automatically.

## Known limits

- Local fixture evaluation cannot reproduce every Azure Policy expression or runtime behavior.
- A valid custom definition does not enforce anything until separately approved assignment and evaluation.

## Expected validation cases

- Healthy: audit definition uses verified aliases and valid typed parameters with passing fixture review.
- Finding: deny condition would also match required production resources, so canary review blocks enforcement.
- Denied or missing: unsupported alias or unreadable provider metadata blocks a verified deployable claim and leaves deployed=false.

## Sources

- [Policy definition structure and modes](https://learn.microsoft.com/en-us/azure/governance/policy/concepts/definition-structure-basics) (consulted 2026-10-21).
- [Supported and modifiable policy aliases](https://learn.microsoft.com/en-us/azure/governance/policy/concepts/definition-structure-alias) (consulted 2026-10-21).
- [Policy definition CLI contract](https://learn.microsoft.com/en-us/cli/azure/policy/definition?view=azure-cli-latest) (consulted 2026-10-21).
