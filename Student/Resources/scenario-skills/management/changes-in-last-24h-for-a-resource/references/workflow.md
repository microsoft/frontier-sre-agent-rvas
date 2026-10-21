# Evidence collection and analysis

## Collection

### 1. Retrieve property level change records

Validate resource ID and timestamps before interpolation. Keep id for skip_token pagination and expand properties.changes locally, including previousValue, newValue and isTruncated. Page completely and obey Retry-After.

```powershell
az graph query --subscriptions $SUB --first 1000 --graph-query "resourcechanges | where properties.targetResourceId =~ '$RESOURCE_ID' | extend changed_at=todatetime(properties.changeAttributes.timestamp) | where changed_at >= datetime($START) and changed_at < datetime($END) | project id,changed_at,properties | order by changed_at asc" --output json
```

### 2. Read management operations and actor evidence

If returned count reaches max-events, split time intervals and deduplicate eventDataId at boundaries until each segment is complete or explicitly capped. Correlate correlationId and resource ID with changeAttributes.correlationId; retain caller and changedByType where available.

```powershell
az monitor activity-log list --subscription $SUB --resource-id $RESOURCE_ID --start-time $START --end-time $END --max-events 10000 --output json
```

## Analysis rules

1. Expand each changed property into a timeline row with previous and new values, redacting sensitive properties before persistence or sharing.
2. Use changeType for Create, Update or Delete. Operation permission name alone does not identify the exact field changed.
3. Attribute actors only from recorded caller or change actor evidence. Correlation and temporal proximity are not proof of causation when IDs do not match.
4. Truncated values, unsupported properties or missing snapshots remain null with a reason. Activity Log generally records management changes, not Key Vault secret reads.

## Known limits

- Resource change history has finite retention and not every resource property is captured.
- Activity Log lacks a complete before and after resource payload and does not establish data plane access.

## Expected validation cases

- Healthy: no changes in complete window is reported as observed no changes.
- Finding: changed SKU has matching correlation ID and old and new values.
- Denied or missing: truncated previous value remains null and cannot be reconstructed from a guessed current value.

## Sources

- [ARG property changes and change actor](https://learn.microsoft.com/en-us/azure/governance/resource-graph/changes/get-resource-changes) (consulted 2026-10-21).
- [Activity Log control plane scope](https://learn.microsoft.com/en-us/azure/azure-monitor/fundamentals/activity-log) (consulted 2026-10-21).
