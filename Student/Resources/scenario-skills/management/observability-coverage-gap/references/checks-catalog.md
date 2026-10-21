# Checks catalog

Observability configuration signals, read with Resource Graph for inventory and alert rules, and with resource API calls for diagnostic settings. Validate effective permissions and record denied reads as not assessed.

For each finding the tool records: resource id, resource type, subscription, resource group, the missing wiring, a severity, and the recommended fix.

## Important resource types

These are the types worth monitoring. The scan enumerates them; adjust the list in the tool if your estate leans on other services.

```
az graph query -q "resources | where type in~ ('microsoft.compute/virtualmachines','microsoft.web/sites','microsoft.sql/servers/databases','microsoft.storage/storageaccounts','microsoft.keyvault/vaults','microsoft.containerservice/managedclusters','microsoft.network/applicationgateways','microsoft.network/loadbalancers','microsoft.documentdb/databaseaccounts','microsoft.cache/redis','microsoft.servicebus/namespaces','microsoft.eventhub/namespaces','microsoft.dbforpostgresql/flexibleservers','microsoft.dbformysql/flexibleservers','microsoft.apimanagement/service','microsoft.containerregistry/registries','microsoft.network/azurefirewalls') | project name, id, type, resourceGroup, subscriptionId, location" --first 1000
```

## 1. No enabled alert candidate with routing (Medium)

Inspect enabled state, supported alert type, configured actions and scope. An exact resource scope is a candidate. Broad scopes require matching target resource type metadata. Metric, scheduled query and Activity Log rules are considered, but conditions and workload applicability still need review.

```
az graph query -q "resources | where type in~ ('microsoft.insights/metricalerts','microsoft.insights/scheduledqueryrules','microsoft.insights/activitylogalerts') | project id, type, properties" --first 1000
```

A scope reference alone is not proof of coverage. Verify rule criteria, action group receivers, suppression and actual delivery. Workspace scoped log rules require additional analysis before concluding resource coverage.

## 2. No usable diagnostic routing observed (High)

Require a configured destination and at least one enabled log or metric category. No diagnostic setting does not mean no telemetry: platform metrics, agents and other collection paths can exist.

Resource Graph alone cannot conclusively enumerate diagnostic settings. Read each resource:

```
az monitor diagnostic-settings list --resource <resource id>
```

The collector checks at most 200 resources. Denied or unsupported reads and cap exclusions are unknown. The diagnostic summary is Unknown if any resources remain unassessed. Verify category requirements, destination access and delivery before proposing changes.

## 3. Cross subscription destinations

A workspace or action group need not exist locally. Assess the destination referenced by each setting or rule, including cross subscription destinations. Absence of a local object is not a finding.

```
az graph query -q "resources | where type =~ 'microsoft.insights/actiongroups' | summarize count() by subscriptionId" --first 1000
```

This inventory query is contextual only, never evidence that alerts cannot notify.

## 4. Workspace inventory (context only)

```
az graph query -q "resources | where type =~ 'microsoft.operationalinsights/workspaces' | summarize count() by subscriptionId" --first 1000
```

A resource can route logs to another subscription or a supported non workspace destination. Do not recommend a new workspace solely because none is local.

## Severity

- No usable diagnostic routing observed: High configuration review priority, not proof of blindness.
- No enabled alert candidate with actions: Medium configuration review priority.
- Unknown collection: no gap verdict. Report Partial or Not assessed.

Combine per resource: a resource missing several pieces gets one finding listing them, at the highest severity among them.

## Sources

- [Diagnostic settings](https://learn.microsoft.com/azure/azure-monitor/essentials/diagnostic-settings), verified: destinations need not be in the resource subscription.
- [Metric alert overview](https://learn.microsoft.com/azure/azure-monitor/alerts/alerts-metric-overview).
