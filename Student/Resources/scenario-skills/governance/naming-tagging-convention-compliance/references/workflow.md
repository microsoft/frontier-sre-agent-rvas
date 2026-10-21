# Evidence collection and analysis

## Collection

### 1. Read resources and groups including tags

Page both queries with skip_token, retain IDs and obey Retry-After. Include resource groups from ResourceContainers because Resources alone does not enumerate them. Record configuration collection time and exceptions.

```powershell
az graph query --subscriptions $SUBS --first 1000 --graph-query 'Resources | project id,name,type,tags,subscriptionId,resourceGroup' --output json
az graph query --subscriptions $SUBS --first 1000 --graph-query "ResourceContainers | where type =~ 'microsoft.resources/subscriptions/resourcegroups' | project id,name,type,tags,subscriptionId" --output json
```

### 2. Read monthly actual resource costs

POST performs a read query only. Follow properties.nextLink with the same body, map row positions from returned columns and respect Retry-After. Normalize resource IDs for joins, retain currency and period, and keep unallocated costs separate.

```powershell
$body=@{type='ActualCost';timeframe='Custom';timePeriod=@{from=$START;to=$END};dataset=@{granularity='None';aggregation=@{cost=@{name='PreTaxCost';function='Sum'}};grouping=@(@{type='Dimension';name='ResourceId'})}} | ConvertTo-Json -Depth 8 -Compress
$body | Set-Content -Encoding utf8 naming-cost-query.json
foreach ($SUB in $SUBS) {
 az rest --method post --url "https://management.azure.com/subscriptions/$SUB/providers/Microsoft.CostManagement/query?api-version=2025-03-01" --body '@naming-cost-query.json' --output json
}
```

### 3. Evaluate conventions locally

Use only reviewed bounded regex patterns and resource names, with no arbitrary code evaluation. Merge resource and group arrays into local naming-inventory.json. Join findings with actual resource cost after validation; Owner values are sensitive and should not be emitted.

```python
import json,re
from pathlib import Path
s=json.loads(Path('approved-conventions.json').read_text(encoding='utf-8'))
for r in json.loads(Path('naming-inventory.json').read_text(encoding='utf-8')):
    pattern=s['patterns'].get(r['type'].lower()); tags={k.lower():v for k,v in (r.get('tags') or {}).items()}
    missing=[k for k in s['required_tags'] if not str(tags.get(k.lower(),'')).strip()]
    ok=bool(re.fullmatch(pattern,r['name'])) if pattern else None
    if missing or ok is False: print(json.dumps({'resource_id':r['id'],'name_compliant':ok,'missing_tags':missing,'environment':tags.get('environment')}))
```

## Analysis rules

1. Apply only the regex designated for the actual resource type using full match, distinguishing an absent convention from a failed name.
2. Check direct tags case insensitively by key and treat empty required values as missing. Resource group tags are not automatically inherited by resources.
3. Prioritize production from approved values and exceptions. Sort within production and other groups by actual cost descending, then stable resource ID.
4. Keep currency groups separate and unavailable costs null, with unknown cost findings last rather than zero. Group cost is a separate aggregate, not a duplicate resource charge.
5. Do not propose renaming immutable resource names as an in place operation; describe migration review where a rename is unsupported.

## Known limits

- Tags are not automatically inherited from resource groups.
- Some resource names cannot be changed in place; cost lag or denied billing access prevents complete cost ranking.

## Expected validation cases

- Healthy: approved name pattern and all required nonempty direct tags.
- Finding: production VM fails full name match and lacks CostCenter, ranked with verified actual spend.
- Denied or missing: cost denied leaves monthly_actual_cost null without hiding configuration findings.

## Sources

- [Resource regex and tag query patterns](https://learn.microsoft.com/en-us/azure/governance/resource-graph/samples/advanced) (consulted 2026-10-21).
- [Actual cost query and grouping](https://learn.microsoft.com/en-us/rest/api/cost-management/query/usage?view=rest-cost-management-2025-03-01) (consulted 2026-10-21).
