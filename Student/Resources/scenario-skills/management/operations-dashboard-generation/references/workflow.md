# Evidence collection and analysis

## Collection

### 1. Discover resources, charts and health snapshot

Repeat definitions and values per resource. Derive panels for VM CPU, memory and disk where available, App Service requests, errors and response time, and SQL DTU and connections using actual supported names, units and aggregations. Guest memory needs an approved workspace or an explicit unavailable tile. Follow all pages, obey Retry-After, and sanitize the timestamped health snapshot. Build panel-specs.json locally with resource_id, metric_name and label from those reads, not invented metrics.

```powershell
az resource list --subscription $SUB --resource-group $RG --output json
az monitor metrics list-definitions --subscription $SUB --resource $RESOURCE_ID --output json
az monitor metrics list --subscription $SUB --resource $RESOURCE_ID --namespace $NAMESPACE --metrics $METRIC_NAMES --start-time $START --end-time $END --interval PT5M --aggregation Average --output json
az rest --method get --url "https://management.azure.com/subscriptions/$SUB/providers/Microsoft.ResourceHealth/events?api-version=2025-05-01&queryStartTime=$START" --output json
```

### 2. Generate dashboard JSON with real chart parts

Append explicit Markdown gap tiles for unavailable requested signals rather than fake charts. Python standard library is sufficient. Validate chart metric names against definitions and every ID against the approved allowlist. A portal import or cloud template validate or what-if call is a separate explicitly approved preview operation, not part of local generation; deployment requires another approval.

```python
import json
from pathlib import Path
panels=json.loads(Path('panel-specs.json').read_text(encoding='utf-8'))
parts=[]
for i,p in enumerate(panels):
    parts.append({'position':{'x':(i%2)*6,'y':(i//2)*4,'colSpan':6,'rowSpan':4},'metadata':{'type':'Extension/Microsoft_Azure_Monitoring/PartType/MetricsChartPart','inputs':[{'name':'queryInputs','value':{'timespan':{'duration':'PT4H'},'id':p['resource_id'],'chartType':0,'metrics':[{'name':p['metric_name'],'resourceId':p['resource_id']}]}}]}})
y=((len(parts)+1)//2)*4
parts.append({'position':{'x':0,'y':y,'colSpan':12,'rowSpan':4},'metadata':{'type':'Extension/HubsExtension/PartType/MarkdownPart','inputs':[],'settings':{'content':{'settings':{'title':'Service Health snapshot, not live','content':Path('service-health.txt').read_text(encoding='utf-8'),'markdownUri':None}}}}})
d={'properties':{'lenses':[{'order':0,'parts':parts}],'metadata':{}},'name':'operations-preview','type':'Microsoft.Portal/dashboards','location':'[resourceGroup().location]','apiVersion':'2020-09-01-preview'}
t={'$schema':'https://schema.management.azure.com/schemas/2019-04-01/deploymentTemplate.json#','contentVersion':'1.0.0.0','resources':[d]}
Path('dashboard-preview.json').write_text(json.dumps(t,indent=2),encoding='utf-8')
assert all(p['position']['colSpan']>0 for p in parts)
json.loads(Path('dashboard-preview.json').read_text()); print('Local dashboard ARM draft only')
```

## Analysis rules

1. Include all requested resource families present in the group. Mark absent families Not applicable and missing telemetry Not assessed.
2. Chart only metric names verified in that resource's definitions; ensure displayed unit, aggregation and time window are appropriate. SQL DTU is not applicable to every purchasing model.
3. Use a two column 12 unit grid with no overlapping parts and a full width timestamped health tile. Static health text must never be described as a live Service Health integration.
4. Validate outer ARM JSON and dashboard part structure locally. State generated preview, cloud validation not run, and deployed false until separately approved and verified.
5. Retain a previous deployed dashboard export and expected resource diff in the approval package; do not replace an existing dashboard automatically.

## Known limits

- Local syntax checks do not validate Azure portal extension rendering or deployment permissions.
- Platform guest memory availability varies; a static health tile is only current at collection time.

## Expected validation cases

- Healthy: metric chart IDs and names match discovered resources and grid positions do not overlap.
- Finding: VM memory is unavailable and is displayed as a gap, not a zero chart.
- Denied or missing: resource metrics read denied leaves that panel unassessed; local JSON generation still cannot claim cloud validation.

## Sources

- [Dashboard JSON structure and metric chart parts](https://learn.microsoft.com/en-us/azure/azure-portal/azure-portal-dashboards-structure) (consulted 2026-10-21).
- [Discover actual metric names](https://learn.microsoft.com/en-us/cli/azure/monitor/metrics?view=azure-cli-latest) (consulted 2026-10-21).
