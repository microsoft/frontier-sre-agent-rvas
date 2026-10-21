# Evidence collection and analysis

## Collection

### 1. Assignments throughout the subscription

--all means all assignments inside this explicit subscription, not all subscriptions. Preserve principal IDs, conditions, delegated identity and scope. Unresolved names stay null rather than triggering broader directory discovery.

```azurecli
az role assignment list --subscription "<subscription_id>" --all --fill-principal-name false --output json
```

### 2. Effective inherited assignments at a selected scope

Repeat at subscription and affected child scopes. Retain Actions, NotActions, DataActions, NotDataActions, assignable scopes and conditions. Deduplicate assignment IDs across these reads.

```azurecli
az role assignment list --subscription "<subscription_id>" --scope "<scope_id>" --include-inherited --fill-principal-name false --output json
az role definition list --subscription "<subscription_id>" --scope "<scope_id>" --output json
```

### 3. Observed control plane operations

Split capped windows, deduplicate eventDataId and correlate caller/object claims only where unambiguous. Activity Log omits most reads and data plane usage, so it is not a complete permission usage source.

```azurecli
az monitor activity-log list --subscription "<subscription_id>" --start-time "<start_utc>" --end-time "<end_utc>" --max-events 10000 --output json
```

## Analysis rules

1. Group assignments by principal object ID and normalized scope ancestry. An identical role at an ancestor is a redundancy candidate only when ancestor access is active, conditions are equivalent and the child adds no distinct delegated or temporal semantics.
2. For different roles compare effective action sets after wildcard expansion and NotActions subtraction separately for control and data planes. Role names or an Owner/Contributor/Reader ranking are not a sufficient containment test.
3. Identify multiple same principal same scope assignments and calculate their permission union. Recommend consolidation only if a candidate role preserves required access without introducing unrelated permissions.
4. For Owner or Contributor compare observed successful operations with approved workload requirements and narrower built in roles. List unobserved but required actions and missing telemetry. Never infer least privilege from 30 days with no write events.
5. Treat PIM eligibility, group membership, deny assignments and ABAC conditions as separate dependencies; if not collected, declare effective access Partial. Never remove assignments during the assessment.
6. Report principal ID/type, display name when independently resolved, assignment IDs, roles, scopes, overlap proof and the owner validation required for any access change.

## Known limits

- Activity Log does not record all reads or data plane usage, and no activity does not establish unnecessary access.
- PIM, nested groups, deny assignments and conditional permissions can invalidate simple role containment conclusions.

## Expected validation cases

- Healthy: distinct required roles with disjoint action sets are not marked redundant.
- Finding: identical unconditional active Reader roles at subscription and child resource group produce a redundant child candidate.
- Denied or missing: absent parent definitions or missing data plane requirements prevents an asserted safe removal.

## Sources

- [Scoped and inherited assignment listing](https://learn.microsoft.com/en-us/cli/azure/role/assignment?view=azure-cli-latest) (consulted 2026-10-21).
- [Actions, exclusions and data actions](https://learn.microsoft.com/en-us/azure/role-based-access-control/role-definitions) (consulted 2026-10-21).
- [Control plane activity limitations](https://learn.microsoft.com/en-us/azure/azure-monitor/fundamentals/activity-log) (consulted 2026-10-21).
