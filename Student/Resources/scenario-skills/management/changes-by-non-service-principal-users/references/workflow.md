# Evidence collection and analysis

## Collection

### 1. Collect all relevant management operations

Retain operationName.value, caller, claims, authorization, resourceId, status, eventDataId and correlationId privately. Split capped windows and deduplicate eventDataId, with Retry-After backoff. Do not filter callers by email shaped strings as an identity test.

```powershell
foreach ($SUB in $SUBS) {
 az monitor activity-log list --subscription $SUB --start-time $START --end-time $END --max-events 10000 --output json
}
```

### 2. Collect independent change actor classifications

Page with skip_token. Join on resource and correlation IDs to changedByType and changedBy; compare with reviewed claims and authorized principal mapping. Do not perform directory enumeration or log token contents in customer output.

```powershell
az graph query --subscriptions $SUBS --first 1000 --graph-query "resourcechanges | extend changed_at=todatetime(properties.changeAttributes.timestamp) | where changed_at >= datetime($START) and changed_at < datetime($END) | project id,changed_at,properties | order by changed_at asc" --output json
```

## Analysis rules

1. Filter actual operation permission suffix /write or /delete, preserving failed attempts separately and excluding reads and unrelated actions.
2. Classify User only with explicit user identity evidence from claims, change actor or approved directory mapping. Service principals and managed identities are nonhuman; unknown callers remain Unknown and are not silently counted as users.
3. Group by stable internal principal key and display an approved alias with operation count, unique resources and UTC timestamps.
4. Reconcile operation lifecycle records before counting logical operations; Started and Succeeded records may describe one request.
5. Explain that absence of matching change actor does not establish a human or service principal and Activity Log is not an audit of data plane secret reads.

## Known limits

- Token claims and change actor information are not always complete.
- Optional directory mapping requires separate authorization; no email pattern heuristic can reliably distinguish human and application callers.

## Expected validation cases

- Healthy: only explicitly identified application operations occur, with zero verified human writes.
- Finding: User typed change actor matches a write correlation and is grouped under its approved alias.
- Denied or missing: unresolved GUID caller is Unknown, not assumed a human or a deleted service principal.

## Sources

- [Activity Log operation evidence](https://learn.microsoft.com/en-us/azure/azure-monitor/fundamentals/activity-log) (consulted 2026-10-21).
- [Change actor and caller type](https://learn.microsoft.com/en-us/azure/governance/resource-graph/changes/get-resource-changes) (consulted 2026-10-21).
