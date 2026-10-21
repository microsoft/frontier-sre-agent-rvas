# Evidence collection and analysis

## Collection

### 1. Collect health and resource appropriate metric evidence

Repeat metric reads for every detected resource family using definitions, not generic CPU for every type. Intersect subscription health response with exact approved group resources. Page list results and obey Retry-After; write normalized sanitized health and per resource metric trend panels to panels\health.json and panels\metrics.json.

```powershell
az resource list --subscription $SUB --resource-group $RG --output json
az rest --method get --url "https://management.azure.com/subscriptions/$SUB/providers/Microsoft.ResourceHealth/availabilityStatuses?api-version=2025-05-01" --output json
az monitor metrics list-definitions --subscription $SUB --resource $RESOURCE_ID --output json
az monitor metrics list --subscription $SUB --resource $RESOURCE_ID --metrics $METRIC_NAMES --start-time $START --end-time $END --interval PT5M --aggregation Average --output json
```

### 2. Collect errors, cost trend and changes

Inspect workspace schema first and query AppExceptions separately when present to include exception trends; no table means a coverage gap. Partition log queries when capped, split Activity Log windows when max-events is reached, and follow Cost properties.nextLink with the same body. Store sanitized actual trend tables and provenance as panels\errors.json, panels\cost.json and panels\changes.json; POST cost query is read only.

```powershell
$KQL="AppTraces | where TimeGenerated >= datetime($START) and TimeGenerated < datetime($END) | where _ResourceId in~ (dynamic($RESOURCE_IDS_JSON)) | where SeverityLevel >= 3 | summarize errors=count() by _ResourceId,bin(TimeGenerated,1h)"
az monitor log-analytics query --subscription $SUB --workspace $WORKSPACE_GUID --timespan "$START/$END" --analytics-query $KQL --output json
az monitor activity-log list --subscription $SUB --resource-group $RG --start-time $START --end-time $END --max-events 10000 --output json
$body=@{type='ActualCost';timeframe='Custom';timePeriod=@{from=$START;to=$END};dataset=@{granularity='Daily';aggregation=@{cost=@{name='PreTaxCost';function='Sum'}}}} | ConvertTo-Json -Depth 8 -Compress
$body | Set-Content -Encoding utf8 workbook-cost-query.json
az rest --method post --url "https://management.azure.com/subscriptions/$SUB/resourceGroups/$RG/providers/Microsoft.CostManagement/query?api-version=2025-03-01" --body '@workbook-cost-query.json' --output json
```

### 3. Build serialized workbook and ARM wrapper locally

This executable route creates actual workbook text panels with collected trends and resource type detail, not fabricated live queries. JSON serializer handles escaping. For live panels, use the workbook Advanced Editor to export a reviewed working Logs, Metrics or ARG item and validate its resource parameters before replacing a snapshot item. Local ARM and serializedData parsing precede any separately approved cloud template validation, editor import or deployment.

```python
import json,uuid
from pathlib import Path
items=[]
for key in ['health','metrics','errors','cost','changes']:
    d=json.loads((Path('panels')/(key+'.json')).read_text(encoding='utf-8'))
    text='## '+key.title()+'\nSnapshot preview, not a live query panel.\n\n'+json.dumps(d,indent=2)
    items.append({'type':1,'content':{'json':text},'name':key})
w={'version':'Notebook/1.0','items':items,'isLocked':False}
r={'type':'Microsoft.Insights/workbooks','apiVersion':'2018-06-17-preview','name':str(uuid.uuid4()),'location':'[resourceGroup().location]','kind':'shared','properties':{'displayName':'Workload operational snapshot preview','serializedData':json.dumps(w),'version':'1.0','sourceId':'[resourceGroup().id]','category':'workbook'}}
t={'$schema':'https://schema.management.azure.com/schemas/2019-04-01/deploymentTemplate.json#','contentVersion':'1.0.0.0','resources':[r]}
Path('workbook-preview.arm.json').write_text(json.dumps(t,indent=2),encoding='utf-8')
assert len(json.loads(r['properties']['serializedData'])['items'])==5
print('Workbook local ARM draft created; deployed=false')
```

## Analysis rules

1. Detect workload resource types before selecting metric panels and preserve every requested section, marking unavailable data explicitly.
2. Health is a collection time snapshot; metric and error trend rows have explicit UTC bins; cost has explicit currency and dates; changes include actor aliases.
3. Keep serializedData a JSON string containing Notebook/1.0 and valid typed items. No secrets, raw credentials or password workbook parameters are allowed.
4. Validate both ARM and inner workbook JSON locally, verify all five sections and source IDs, and record preview versus deployed state separately.
5. Do not promise live refresh for snapshot panels. Cloud rendering, template what-if, publishing and scheduling are distinct approval steps with previous version backup and rollback.

## Known limits

- The baseline generated workbook contains real evidence snapshots, not live refresh panels.
- Local JSON validation cannot prove portal rendering, current cost completeness or query permission in another identity.

## Expected validation cases

- Healthy: all five snapshot sections contain evidence and both JSON layers parse.
- Finding: no error collection is configured and the errors panel explicitly records the gap.
- Denied or missing: cost denied leaves a Not assessed cost panel and deployed false.

## Sources

- [Workbook serializedData and ARM automation](https://learn.microsoft.com/en-us/azure/azure-monitor/visualize/workbooks-automate) (consulted 2026-10-21).
- [Supported workbook data sources](https://learn.microsoft.com/en-us/azure/azure-monitor/visualize/workbooks-data-sources) (consulted 2026-10-21).
- [Daily cost query](https://learn.microsoft.com/en-us/rest/api/cost-management/query/usage?view=rest-cost-management-2025-03-01) (consulted 2026-10-21).
