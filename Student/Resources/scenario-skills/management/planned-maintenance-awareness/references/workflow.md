# Evidence collection and analysis

## Collection

### 1. Retrieve maintenance notices and update history

Set $LOOKBACK to the separately approved announcement lookback, not just the future window. Follow nextLink to completion and handle 429 Retry-After. Select PlannedMaintenance events locally and preserve announced scheduled impact bounds and updates, including notices announced before $START.

```powershell
foreach ($SUB in $SUBS) {
 az rest --method get --url "https://management.azure.com/subscriptions/$SUB/providers/Microsoft.ResourceHealth/events?api-version=2025-05-01&queryStartTime=$LOOKBACK" --output json
}
```

### 2. Map maintenance scope to actual inventory

Page with skip_token. Map event impact service and region to exact approved resources; if the event provides narrower resource impact, intersect it with the inventory. Record unknown mappings for service names without an approved resource type mapping.

```powershell
az graph query --subscriptions $SUBS --first 1000 --graph-query 'Resources | project id,name,type,location,subscriptionId,resourceGroup,tags' --output json
```

## Analysis rules

1. Include maintenance whose scheduled interval overlaps [START,END), using start < END and end > START. Do not use lastUpdateTime as the scheduled maintenance time.
2. Distinguish cancelled, completed, rescheduled and active notices and retain the latest official update with provenance.
3. Report event name, service, region, UTC start and end, and matched resources. Region matching alone is potential impact, not a guarantee of downtime.
4. Recommend owner review of redundancy and workload windows; creating reminders, rescheduling workloads or sending notifications is outside this read workflow.

## Known limits

- A short announcement lookback can miss old announcements; explicitly disclose history coverage.
- Some notices contain narrative rather than structured schedule or resource details; ambiguous times remain null pending owner review.

## Expected validation cases

- Healthy: completed maintenance outside the future window is excluded.
- Finding: notice announced ten days ago overlaps the next seven days and maps to an approved production resource.
- Denied or missing: missing structured end time is null and requires review, not an invented duration.

## Sources

- [Service Health event listing and impact](https://learn.microsoft.com/en-us/rest/api/resourcehealth/events/list-by-subscription-id?view=rest-resourcehealth-2025-05-01) (consulted 2026-10-21).
