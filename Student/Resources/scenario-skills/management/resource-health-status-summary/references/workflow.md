# Evidence collection and analysis

## Collection

### 1. Capture current subscription health

Follow all nextLink values after scope validation. Record properties.availabilityState and available reason and timing fields without synthesizing missing ones. Retry 429 per Retry-After; retain denied subscription failures.

```powershell
foreach ($SUB in $SUBS) {
 az rest --method get --url "https://management.azure.com/subscriptions/$SUB/providers/Microsoft.ResourceHealth/availabilityStatuses?api-version=2025-05-01" --output json
}
```

### 2. Reconcile health coverage to inventory

Page ARG with skip_token. Strip the ResourceHealth extension suffix from health record IDs to join to the base resource ID. Left join from the approved resource inventory; do not discard resources without a matching status.

```powershell
az graph query --subscriptions $SUBS --first 1000 --graph-query 'Resources | project id,name,type,location,subscriptionId,resourceGroup' --output json
```

## Analysis rules

1. Count Available, Degraded, Unavailable and service reported Unknown separately. Missing health records are Not assessed or unsupported, not service reported Unknown.
2. List every Degraded and Unavailable resource with returned reason, occurrence or report timestamp and collection time. Do not treat reportedTime as outage start if occurrence time is absent.
3. Preserve a reconciliation total of inventoried, health assessed, unsupported and inaccessible resources.
4. Recommend service specific owner investigation for degradation and avoid claiming an SLA breach from current health alone.

## Known limits

- Resource Health support is not universal across resource types.
- A current status listing cannot calculate outage duration or contractual availability over a month.

## Expected validation cases

- Healthy: supported inventory resources all report Available.
- Finding: Unavailable resource includes original reason and occurrence timestamp.
- Denied or missing: health response denied leaves resource status null and increases inaccessible count.

## Sources

- [Resource Health availability status listing](https://learn.microsoft.com/en-us/rest/api/resourcehealth/availability-statuses/list-by-subscription-id?view=rest-resourcehealth-2025-05-01) (consulted 2026-10-21).
