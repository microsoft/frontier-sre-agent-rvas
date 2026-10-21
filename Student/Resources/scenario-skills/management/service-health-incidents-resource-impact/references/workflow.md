# Evidence collection and analysis

## Collection

### 1. Read subscription incidents

Follow every nextLink after validating its management.azure.com host and approved subscription path. Filter eventType ServiceIssue and active status locally. Retain impact, incident title, status, update timestamps and official mitigation text. Respect Retry-After on 429; do not claim no incidents if a page fails.

```powershell
foreach ($SUB in $SUBS) {
 az rest --method get --url "https://management.azure.com/subscriptions/$SUB/providers/Microsoft.ResourceHealth/events?api-version=2025-05-01&queryStartTime=$START" --output json
}
```

### 2. Join potential impact to actual resource health

Continue ARG with skip_token and Resource Health with nextLink. Join event service and region impact to resource types and normalized region names, then left join by resource ID to availability status and approved dependency inventory. Query any event supplied impacted resource details only when their API and scope are documented and approved.

```powershell
az graph query --subscriptions $SUBS --first 1000 --graph-query 'Resources | project id,name,type,location,subscriptionId,resourceGroup' --output json
foreach ($SUB in $SUBS) {
 az rest --method get --url "https://management.azure.com/subscriptions/$SUB/providers/Microsoft.ResourceHealth/availabilityStatuses?api-version=2025-05-01" --output json
}
```

## Analysis rules

1. A service and region match establishes potential exposure, not proof of outage. Mark confirmed impact only with event resource evidence, degraded Resource Health or workload telemetry.
2. Report incident title, services, impacted regions and active or resolved status at the collection instant. Retain events spanning the requested window rather than only events created within it.
3. Propagate potential impact through explicit dependency edges and show the edge source. Do not infer dependent workloads from matching names alone.
4. Quote or summarize official mitigation with its update timestamp. Treat proposed architecture alternatives as recommendations requiring separate design and approval.

## Known limits

- Subscription Service Health access does not guarantee resource specific impact detail for every service.
- Unsupported or inaccessible Resource Health is null, not Available.

## Expected validation cases

- Healthy: incident affects another service or region and is excluded with a recorded reason.
- Finding: affected service and region match a resource with Unavailable health and a documented application dependency.
- Denied or missing: event is visible but resource health is denied; potential exposure is reported with null confirmed health.

## Sources

- [List subscription Service Health events](https://learn.microsoft.com/en-us/rest/api/resourcehealth/events/list-by-subscription-id?view=rest-resourcehealth-2025-05-01) (consulted 2026-10-21).
- [List resource availability status](https://learn.microsoft.com/en-us/rest/api/resourcehealth/availability-statuses/list-by-subscription-id?view=rest-resourcehealth-2025-05-01) (consulted 2026-10-21).
