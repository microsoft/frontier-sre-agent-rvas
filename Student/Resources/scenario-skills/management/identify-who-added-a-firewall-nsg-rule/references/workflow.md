# Evidence collection and analysis

## Collection

### 1. Collect network management operations and property changes

Filter Activity Log to exact resource IDs and child rule paths, plus write or delete operations; include parent writes that replace an entire rule collection. Split capped Activity Log intervals, deduplicate events and page ARG using skip_token. Retry throttling with Retry-After.

```powershell
foreach ($SUB in $SUBS) {
 az monitor activity-log list --subscription $SUB --start-time $START --end-time $END --max-events 10000 --output json
}
az graph query --subscriptions $SUBS --first 1000 --graph-query "resourcechanges | extend changed_at=todatetime(properties.changeAttributes.timestamp) | where changed_at >= datetime($START) and changed_at < datetime($END) | where properties.targetResourceType in~ ('microsoft.network/networksecuritygroups','microsoft.network/networksecuritygroups/securityrules','microsoft.network/azurefirewalls','microsoft.network/firewallpolicies','microsoft.network/firewallpolicies/rulecollectiongroups') | project id,changed_at,properties | order by changed_at asc" --output json
```

### 2. Read rule context without assuming it is historical

Read the NSG or firewall current configuration and approved policy rule collection groups. If child enumeration is unavailable through resource list, use a documented provider GET at the approved policy ID and API version discovered from az provider show --namespace Microsoft.Network. Never broaden to unapproved policy groups. Correlate recorded changes and activity operations, not just current rule names.

```powershell
az resource show --subscription $SUB --ids $NETWORK_RESOURCE_ID --output json
az resource list --subscription $POLICY_SUB --resource-group $POLICY_RG --resource-type Microsoft.Network/firewallPolicies/ruleCollectionGroups --output json
```

## Analysis rules

1. Match caller to a successful write using correlation ID, resource ID and timestamp, retaining actor confidence. Failed writes are attempts, not added rules.
2. Expand securityRules, applicationRuleCollections, networkRuleCollections, natRuleCollections or Firewall Policy rule collection changes according to the actual resource type.
3. For each changed rule, report old and new source, destination, protocol and ports from diffs or retained snapshots. Current configuration alone does not prove the historical rule contents.
4. If a parent write changed several rules, list all verified changed paths; if exact additions cannot be resolved, state collection changed with rule name and values null.
5. Preserve shared Firewall Policy inheritance and approved parent policy references when identifying the controlling rule.

## Known limits

- Activity Log alone generally does not contain a full NSG or firewall rule before and after payload.
- Truncated arrays and shared policies outside approved scope leave exact rule changes unassessed.

## Expected validation cases

- Healthy: unrelated network reads and failed attempts do not become successful rule additions.
- Finding: successful securityRules write and matching diff identify caller, exact new port and destination.
- Denied or missing: parent collection write without readable diff retains caller but rule fields null.

## Sources

- [Property diffs and change actor evidence](https://learn.microsoft.com/en-us/azure/governance/resource-graph/changes/get-resource-changes) (consulted 2026-10-21).
- [Management operation attribution](https://learn.microsoft.com/en-us/azure/azure-monitor/fundamentals/activity-log) (consulted 2026-10-21).
