# Evidence collection and analysis

## Collection

### 1. Establish hierarchy and collect operational sections

Intersect hierarchy descendants with $SUBS; enumerate approved ancestors separately for inherited governance and RBAC. Page ARG, REST nextLink and CLI lists to completion; respect Retry-After and split log windows when capped. For stale RBAC, resolve principal IDs using separately authorized directory evidence and report unresolved identities as unknown, not deleted. For orphan candidates verify unattached disks, unassociated IPs and empty plans against owner exceptions and telemetry; configuration alone only establishes candidates.

```powershell
az account management-group show --name $MG --expand --recurse --output json
az graph query --subscriptions $SUBS --first 1000 --graph-query 'Resources | project id,name,type,location,subscriptionId,resourceGroup,tags,sku,properties' --output json
foreach ($SUB in $SUBS) {
 az security secure-scores list --subscription $SUB --output json
 az security assessment list --subscription $SUB --output json
 az policy state list --subscription $SUB --all --output json
 az role assignment list --subscription $SUB --all --include-inherited --output json
 az rest --method get --url "https://management.azure.com/subscriptions/$SUB/providers/Microsoft.ResourceHealth/availabilityStatuses?api-version=2025-05-01" --output json
 az rest --method get --url "https://management.azure.com/subscriptions/$SUB/providers/Microsoft.AlertsManagement/alerts?api-version=2019-03-01&customTimeRange=$START/$END" --output json
}
```

### 2. Collect current and prior daily actual costs

This POST is a read query, not resource mutation. Follow properties.nextLink with the same query body and validate allowed host and subscription. Map column names to row positions rather than hardcoding offsets. Persist raw current and prior results privately. Obtain incident histories from approved monitoring exports and owner timelines; score trend from retained snapshots; alert durations and action evidence from alert history.

```powershell
foreach ($SUB in $SUBS) {
 $body=@{type='ActualCost';timeframe='Custom';timePeriod=@{from=$PREVIOUS_START;to=$END};dataset=@{granularity='Daily';aggregation=@{totalCost=@{name='PreTaxCost';function='Sum'}};grouping=@(@{type='Dimension';name='ResourceId'},@{type='Dimension';name='ServiceName'})}} | ConvertTo-Json -Depth 10 -Compress
 $body | Set-Content -Encoding utf8 cost-query.json
 az rest --method post --url "https://management.azure.com/subscriptions/$SUB/providers/Microsoft.CostManagement/query?api-version=2025-03-01" --body '@cost-query.json' --output json
}
```

### 3. Read approved historical and owner evidence

Read the required local source package rather than invent history from current configuration. Join snapshots by subscription and initiative, recommendations by definition and resource, incidents by impact interval, RBAC by principal ID and orphan evidence by resource ID. Apply the explicit analysis algorithms before normalizing report metrics; retain source links and unknown coverage.

```powershell
Get-Content -Raw .\approved-operations-history.json | ConvertFrom-Json | ConvertTo-Json -Depth 40
```

### 4. Render a real PDF and verify content locally

Normalize computed section metrics and details into the explicitly declared local executive-report-evidence.json contract used by this script. ReportLab is a prerequisite, not an Azure service. Escape all text to prevent markup injection. Inspect page count and page breaks in a local PDF viewer; require every section to be present, dates and currencies consistent, and sensitive identifiers replaced by approved aliases before sharing.

```python
import json
from pathlib import Path
from xml.sax.saxutils import escape
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
r=json.loads(Path('executive-report-evidence.json').read_text(encoding='utf-8'))
styles=getSampleStyleSheet(); story=[Paragraph('Executive operational report',styles['Title']),Paragraph(escape(r['executive_summary']),styles['BodyText'])]
for section in ['cost','security','availability','compliance','operational_hygiene']:
    d=r['sections'][section]
    story += [Spacer(1,16),Paragraph(escape(section.replace('_',' ').title()),styles['Heading1'])]
    rows=[['Metric','Value','Coverage']]+[[str(x['name']),str(x.get('value') if x.get('value') is not None else 'Not assessed'),str(x['coverage'])] for x in d['metrics']]
    t=Table([[Paragraph(escape(c),styles['BodyText']) for c in row] for row in rows],repeatRows=1,colWidths=[150,170,150]); t.setStyle([('GRID',(0,0),(-1,-1),0.3,colors.grey)]); story.append(t)
    for text in d['details']+d['recommendations']: story.append(Paragraph(escape(text),styles['BodyText']))
story += [Paragraph('Sources and limitations',styles['Heading1'])]+[Paragraph(escape(s),styles['BodyText']) for s in r['sources']+r['limitations']]
SimpleDocTemplate('executive-report-preview.pdf').build(story)
p=Path('executive-report-preview.pdf'); assert p.read_bytes().startswith(b'%PDF-') and p.stat().st_size>1000
print('Local PDF preview created; not published')
```

## Analysis rules

1. Sum actual spend separately by currency and period, calculate percent change only when previous spend is nonzero, rank top five resource or service drivers, and flag daily cost deviations against the previous comparable period with the threshold recorded.
2. Show score trend only from historical samples; identify new High recommendations by snapshot difference. Resource Health current state is not an availability percentage or evidence of contractual SLA breach.
3. Compute incident durations from verified impact intervals and rank the top five. Evaluate SLA claims only against approved service terms, exclusions, measurement basis and customer telemetry; otherwise state not assessed.
4. Compute compliance from latest resource and policy evaluation pairs, distinguish exempt and unknown states, and rank policies by distinct noncompliant resource count.
5. Join orphan candidates to actual resource costs, resolve suspected stale RBAC against authorized principal evidence, and compute alert noise ratio with its numerator, denominator and coverage. Never count unresolved identities as confirmed stale.
6. Produce executive summary, metric table, section details and recommendations. A local preview PDF is not a deployed report, approved disclosure or configured monthly schedule.

## Known limits

- Cost data can arrive late and does not establish orphan savings until ownership and ongoing billing are verified.
- Score history, customer impact, SLA breach and RBAC deletion evidence are not guaranteed by read access; missing values remain null.

## Expected validation cases

- Healthy: all five sections have complete evidence and the PDF opens with summary and metric table.
- Finding: spend rises while compliance falls; PDF preserves both independent findings and their baselines.
- Denied or missing: Cost API denied leaves total and MoM null, and the PDF labels cost Not assessed rather than zero.

## Sources

- [Cost Management query usage](https://learn.microsoft.com/en-us/rest/api/cost-management/query/usage?view=rest-cost-management-2025-03-01) (consulted 2026-10-21).
- [Historical security evidence export](https://learn.microsoft.com/en-us/azure/defender-for-cloud/continuous-export) (consulted 2026-10-21).
- [Azure reliability and workload responsibility](https://learn.microsoft.com/en-us/azure/reliability/overview) (consulted 2026-10-21).
