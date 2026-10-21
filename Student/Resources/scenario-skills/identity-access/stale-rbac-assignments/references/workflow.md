# Evidence collection and analysis

## Collection

### 1. Assignments to review

Retain assignment IDs, principal IDs/types, roles and scopes. This does not include all possible tenant roles or all PIM eligible assignments.

```azurecli
az role assignment list --subscription "<subscription_id>" --all --fill-principal-name false --output json
```

### 2. Export retention and table availability

Confirm customerId equals workspace_id, and read configured analytics/total retention for both workload identity tables. Configuration is not historical ingestion continuity; the customer must also supply export start and outage evidence before a 90 day no observation conclusion.

```azurecli
az monitor log-analytics workspace show --subscription "<subscription_id>" --resource-group "<workspace_resource_group>" --workspace-name "<workspace_name>" --output json
az monitor log-analytics workspace table list --subscription "<subscription_id>" --resource-group "<workspace_resource_group>" --workspace-name "<workspace_name>" --output json
```

### 3. Principal existence and user last successful sign in

Execute the second command only for a verified User principal. Preserve 403 versus 404. User signInActivity requires appropriate tenant permissions and license; null is not evidence of no sign in.

```azurecli
az rest --method get --subscription "<subscription_id>" --url 'https://graph.microsoft.com/v1.0/<directory_collection>/<principal_id>?$select=id,displayName' --output json
az rest --method get --subscription "<subscription_id>" --url 'https://graph.microsoft.com/v1.0/users/<principal_id>?$select=id,displayName,signInActivity' --output json
```

### 4. Workload identity sign ins

Run only for service principals and managed identities. A fuzzy union warning or absent table is a coverage failure. Verify exported table presence, configured retention and ingestion continuity from the workspace evidence before interpreting a zero count. Confirm the observed ResultType encoding before accepting a successful sign in.

```azurecli
az monitor log-analytics query --subscription "<subscription_id>" --workspace "<workspace_id>" --timespan "<start_utc>/<end_utc>" --analytics-query "union isfuzzy=true AADServicePrincipalSignInLogs, AADManagedIdentitySignInLogs | where TimeGenerated >= datetime(<start_utc>) and TimeGenerated < datetime(<end_utc>) | where ServicePrincipalId == '<principal_id>' | summarize event_count=count(), last_observed=max(TimeGenerated), last_success=maxif(TimeGenerated, tostring(ResultType) in~ ('0','Success')) by Type, ServicePrincipalId" --output json
```

## Analysis rules

1. Resolve each assigned principal using the correct approved tenant and type. Only a repeatable authorized 404 after replication delay is an orphan candidate; 403, timeout and foreign principal ambiguity are unknown.
2. For users, compare signInActivity.lastSuccessfulSignInDateTime to end_utc minus 90 days. Report attempted interactive and noninteractive dates separately and never substitute failed attempts for successful access.
3. For service principals calculate last successful and last observed sign in from both application and managed identity exports, with table coverage and retention. No events in a partial or short retention window is insufficient to claim 90 day inactivity.
4. Separate no successful sign in observed, last success older than 90 days and principal deleted. Preserve groups as not applicable for user sign in checks; stale user checks do not apply to group objects.
5. Recommend owner review with assignment scope, role and last sign in evidence. Account for emergency, DR and infrequent automation use, then obtain separate approval before any removal.
6. Minimize personal names in customer summaries and retain raw sign in evidence only in the approved local evidence location.

## Known limits

- User successful sign in history is not fully backfilled and null values cannot establish inactivity.
- Workload identity logs have tenant licensing, export and retention dependencies; sign ins do not capture all ongoing token use.

## Expected validation cases

- Healthy: a user with successful sign in yesterday is not stale.
- Finding: an assigned user with last successful sign in 120 days ago becomes a review candidate with that timestamp.
- Denied or missing: Graph 403 or only 30 days of workload logs produces unknown staleness, not a removal recommendation.

## Sources

- [Assignment inventory](https://learn.microsoft.com/en-us/cli/azure/role/assignment?view=azure-cli-latest) (consulted 2026-10-21).
- [Successful versus attempted user sign in and history](https://learn.microsoft.com/en-us/graph/api/resources/signinactivity?view=graph-rest-1.0) (consulted 2026-10-21).
- [User API permissions and replication](https://learn.microsoft.com/en-us/graph/api/user-list?view=graph-rest-1.0) (consulted 2026-10-21).
- [Workload identity sign in columns](https://learn.microsoft.com/en-us/azure/azure-monitor/reference/tables/aadserviceprincipalsigninlogs) (consulted 2026-10-21).
- [Managed identity sign in columns](https://learn.microsoft.com/en-us/azure/azure-monitor/reference/tables/aadmanagedidentitysigninlogs) (consulted 2026-10-21).
- [Table presence and retention metadata](https://learn.microsoft.com/en-us/cli/azure/monitor/log-analytics/workspace/table?view=azure-cli-latest) (consulted 2026-10-21).
- [Workspace evidence queries](https://learn.microsoft.com/en-us/cli/azure/monitor/log-analytics?view=azure-cli-latest) (consulted 2026-10-21).
