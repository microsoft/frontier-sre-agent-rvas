# Evidence collection and analysis

## Collection

### 1. Collect configuration and incident evidence

Select metrics from definitions and query errors only after confirming actual table schema; use the service's resource log adapter when AppTraces is not applicable. Intersect health with exact resource ID. Complete pages, split capped log and Activity Log windows and handle Retry-After. Normalize configuration and SKU, metric window, errors, recent changes and health into sanitized ticket-evidence.json.

```powershell
az resource show --subscription $SUB --ids $RESOURCE_ID --output json
az monitor metrics list-definitions --subscription $SUB --resource $RESOURCE_ID --output json
az monitor metrics list --subscription $SUB --resource $RESOURCE_ID --metrics $METRIC_NAMES --start-time $START --end-time $END --interval PT5M --aggregation Average Maximum --output json
az monitor activity-log list --subscription $SUB --resource-id $RESOURCE_ID --start-time $START --end-time $END --max-events 10000 --output json
az rest --method get --url "https://management.azure.com/subscriptions/$SUB/providers/Microsoft.ResourceHealth/availabilityStatuses?api-version=2025-05-01" --output json
$KQL="AppTraces | where TimeGenerated >= datetime($START) and TimeGenerated < datetime($END) | where _ResourceId =~ '$RESOURCE_ID' | where SeverityLevel >= 3 | summarize count() by bin(TimeGenerated,5m),tostring(Properties['ErrorCode'])"
az monitor log-analytics query --subscription $SUB --workspace $WORKSPACE_GUID --timespan "$START/$END" --analytics-query $KQL --output json
```

### 2. Read current support taxonomy

The catalog read is an explicit nonresource scope exception. Select $SERVICE_NAME from returned IDs, follow pagination and verify classification belongs to that service. Do not invent a service or category GUID.

```powershell
az rest --method get --url 'https://management.azure.com/providers/Microsoft.Support/services?api-version=2024-04-01' --output json
az rest --method get --url "https://management.azure.com/providers/Microsoft.Support/services/$SERVICE_NAME/problemClassifications?api-version=2024-04-01" --output json
```

### 3. Create and validate an unsent request body

Validate severity, contact fields, consent enum and required fields against the consulted support request schema and actual support plan; do not assign contact consent automatically. The private contact profile is never part of a shareable library artifact. API attachment support is not assumed; keep a separate sanitized evidence manifest for an approved portal upload. Do not PUT the request.

```python
import json,hashlib
from pathlib import Path
p=json.loads(Path('approved-support-profile.json').read_text(encoding='utf-8')); e=json.loads(Path('ticket-evidence.json').read_text(encoding='utf-8'))
assert e['resource_id'] in p['approved_resource_ids']
assert p['problem_classification_id'].startswith(p['service_id']+'/problemClassifications/')
body={'properties':{'title':p['title'],'description':p['issue_description']+'\n\n'+json.dumps(e,indent=2),'severity':p['severity'],'serviceId':p['service_id'],'problemClassificationId':p['problem_classification_id'],'contactDetails':p['contact_details'],'technicalTicketDetails':{'resourceId':e['resource_id']},'advancedDiagnosticConsent':p['advanced_diagnostic_consent']}}
Path('support-ticket.unsent.json').write_text(json.dumps(body,indent=2),encoding='utf-8')
manifest={'submitted':False,'requires_approval':True,'payload_sha256':hashlib.sha256(Path('support-ticket.unsent.json').read_bytes()).hexdigest(),'resource_id':e['resource_id'],'evidence_sections':list(e)}
Path('support-ticket.manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
```

## Analysis rules

1. Describe observed symptoms, business impact, UTC timeline and attempted mitigations separately from suspected cause.
2. Include resource SKU and config summary, supported metrics, error counts, changes and current health with collection timestamps and section coverage.
3. Select service and problem classification from current catalog results, and validate severity against impact and support plan response obligations without promising response times.
4. Scan description and evidence for secrets, personal data and unsafe log content. Contact details stay in a private unsent body, not the customer shareable evidence summary.
5. Require approval of exact payload, contact consent and destination before submission. No ticket number exists until a separately authorized response confirms creation.

## Known limits

- Technical support creation depends on the customer's eligible support plan and permissions.
- The support API does not provide a generic evidence attachment or diagnostic sharing consent workflow; review current schema and portal process.

## Expected validation cases

- Healthy: all evidence sections and actual service classification validate, producing submitted=false.
- Finding: impact merits urgent severity review but the draft does not promise an unsupported response time.
- Denied or missing: logs denied leaves error evidence null and clearly flags draft coverage, while ticket_id remains null.

## Sources

- [Support ticket request fields and prerequisites](https://learn.microsoft.com/en-us/rest/api/support/support-tickets/create?view=rest-support-2024-04-01) (consulted 2026-10-21).
- [Current support services](https://learn.microsoft.com/en-us/rest/api/support/services/list?view=rest-support-2024-04-01) (consulted 2026-10-21).
- [Current support problem classifications](https://learn.microsoft.com/en-us/rest/api/support/problem-classifications/list?view=rest-support-2024-04-01) (consulted 2026-10-21).
