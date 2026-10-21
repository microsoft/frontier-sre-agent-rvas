# Evidence collection and analysis

## Collection

### 1. Top twenty denied network flows

Uses verified resource specific table columns. First confirm diagnostics route this category to this workspace. A missing table is Not assessed, not no denials.

```azurecli
az monitor log-analytics query --subscription "<subscription_id>" --workspace "<workspace_id>" --timespan "<start_utc>/<end_utc>" --analytics-query "AZFWNetworkRule | where TimeGenerated >= datetime(<start_utc>) and TimeGenerated < datetime(<end_utc>) | where _ResourceId =~ '<firewall_id>' and Action =~ 'Deny' | summarize flow_hits=count() by SourceIp, DestinationIp, DestinationPort, Protocol, RuleCollection, Rule | top 20 by flow_hits desc" --output json
```

### 2. All internal source denied groups

Do not limit this to the top twenty overall. Validate CIDRs as data. Split UTC windows on partial errors or row limits and merge counts without overlapping endpoints.

```azurecli
az monitor log-analytics query --subscription "<subscription_id>" --workspace "<workspace_id>" --timespan "<start_utc>/<end_utc>" --analytics-query "AZFWNetworkRule | where TimeGenerated >= datetime(<start_utc>) and TimeGenerated < datetime(<end_utc>) | where _ResourceId =~ '<firewall_id>' and Action =~ 'Deny' | where ipv4_is_in_any_range(SourceIp,dynamic(<internal_cidrs_json>)) | summarize flow_hits=count(), first_seen=min(TimeGenerated), last_seen=max(TimeGenerated) by SourceIp, DestinationIp, DestinationPort, Protocol, RuleCollection, Rule" --output json
```

### 3. Allowed flows matching approved indicators

A match is an indicator hit, not proof of compromise. Treat fuzzy union warnings and absent branches as Partial. Empty approved indicator sets mean no indicator analysis, not no suspicious traffic.

```azurecli
az monitor log-analytics query --subscription "<subscription_id>" --workspace "<workspace_id>" --timespan "<start_utc>/<end_utc>" --analytics-query "union isfuzzy=true (AZFWNetworkRule | where TimeGenerated >= datetime(<start_utc>) and TimeGenerated < datetime(<end_utc>) | where _ResourceId =~ '<firewall_id>' and Action =~ 'Allow' | where DestinationIp in (dynamic(<suspicious_ips_json>)) | project TimeGenerated, SourceIp, destination=DestinationIp, RuleCollection, Rule, match_type='ip'), (AZFWApplicationRule | where TimeGenerated >= datetime(<start_utc>) and TimeGenerated < datetime(<end_utc>) | where _ResourceId =~ '<firewall_id>' and Action =~ 'Allow' | where tolower(Fqdn) in (dynamic(<suspicious_fqdns_json>)) | project TimeGenerated, SourceIp, destination=Fqdn, RuleCollection, Rule, match_type='fqdn') | summarize flow_hits=count(), last_seen=max(TimeGenerated) by SourceIp,destination,RuleCollection,Rule,match_type" --output json
```

### 4. Rule collection hit volume

The verified rule tables have hit records, not per flow payload bytes. _BilledSize is log ingestion size, never network bytes. Aggregate hits are a clearly labeled activity proxy.

```azurecli
az monitor log-analytics query --subscription "<subscription_id>" --workspace "<workspace_id>" --timespan "<start_utc>/<end_utc>" --analytics-query "union isfuzzy=true AZFWNetworkRule,AZFWApplicationRule | where TimeGenerated >= datetime(<start_utc>) and TimeGenerated < datetime(<end_utc>) | where _ResourceId =~ '<firewall_id>' | summarize rule_hits=count() by Type, RuleCollectionGroup, RuleCollection, Action, hour=bin(TimeGenerated,1h)" --output json
```

### 5. Firewall wide processed bytes and diagnostic routing

DataProcessed is aggregate firewall bytes without a rule collection dimension. Read routing configuration and report legacy AzureDiagnostics mode separately; do not parse its free text as the resource specific schema.

```azurecli
az monitor metrics list --subscription "<subscription_id>" --resource "<firewall_id>" --metrics DataProcessed --start-time "<start_utc>" --end-time "<end_utc>" --interval PT1H --aggregation Total --output json
az monitor diagnostic-settings list --subscription "<subscription_id>" --resource "<firewall_id>" --output json
```

## Analysis rules

1. Rank denied network tuples by log hit count, preserving source, destination, port and protocol. Denial counts are not unique connections and must not be labeled as such.
2. Analyze all internal source denials against customer CIDRs, not just RFC1918 or the overall top twenty. Correlate approved application flows before suggesting a misconfiguration.
3. Join allowed IP/FQDN hits to approved indicators with source timestamp and expiration. Report false positive review and do not infer suspiciousness from an arbitrary destination list.
4. Report hourly hit counts per rule collection, action and table. Per collection traffic bytes remain null because these tables do not contain payload byte counts; present aggregate DataProcessed separately.
5. Verify log category coverage, table plan, diagnostic destination, observation bounds and partial query warnings. If legacy mode is configured, report that the supplied resource specific queries cannot assess those records until a separately verified legacy parser is supplied.
6. Recommend narrowly scoped rule or application owner review, never automatically add allow rules, block indicators or change diagnostic routing.

## Known limits

- Resource specific rule logs report rule hits rather than complete flow payload volume; per collection network bytes cannot be derived from _BilledSize.
- Logging mode, table plan and retention can limit coverage; an empty or missing table is not evidence of no traffic.

## Expected validation cases

- Healthy: approved application flows contain no reviewed indicator hits and required log tables are present.
- Finding: a denied internal flow and an allowed approved indicator hit appear as distinct review findings.
- Denied or missing: missing application logs produce Partial and rule_collection_bytes stays null even with DataProcessed metrics.

## Sources

- [Verified network rule log columns](https://learn.microsoft.com/en-us/azure/azure-monitor/reference/tables/azfwnetworkrule) (consulted 2026-10-21).
- [Verified application rule FQDN columns](https://learn.microsoft.com/en-us/azure/azure-monitor/reference/tables/azfwapplicationrule) (consulted 2026-10-21).
- [Aggregate DataProcessed metric](https://learn.microsoft.com/en-us/azure/firewall/monitor-firewall-reference) (consulted 2026-10-21).
- [Workspace query command](https://learn.microsoft.com/en-us/cli/azure/monitor/log-analytics?view=azure-cli-latest) (consulted 2026-10-21).
