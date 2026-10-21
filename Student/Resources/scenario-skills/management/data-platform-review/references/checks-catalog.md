# Checks catalog

Data platform reliability checks, read from configuration with Azure Resource Graph and covered by Reader. The scan tool evaluates each service; this catalog is the source of truth for each check and its fix. Some overlap with the reliability-posture-review skill is intentional; this is the data tier deep dive.

For each finding the tool records: resource, engine, subscription, resource group, the check, a severity, and the recommended change.

## Azure SQL (engine: SQL)

Databases:

```
az graph query -q "resources | where type =~ 'microsoft.sql/servers/databases' | where name != 'master' | project name, id, subscriptionId, resourceGroup, sku, properties" --first 1000
```

- Premium or Business Critical database without zone redundancy (High). Fix: enable zoneRedundant.
- Locally redundant backup storage (Medium). Fix: set backup storage redundancy to Geo or Zone where the data warrants it.

Servers:

```
az graph query -q "resources | where type =~ 'microsoft.sql/servers' | project name, id, subscriptionId, resourceGroup, properties" --first 1000
```

- Public network access enabled (Low). Fix: use Private Link or firewall rules and disable public access.
- Minimum TLS below 1.2 (Medium). Fix: set the minimum TLS version to 1.2.

Long term retention is not in Resource Graph; check it by hand where longer retention is required:

```
az sql db ltr-policy show --resource-group <rg> --server <server> --name <db> --subscription <id>
```

## PostgreSQL and MySQL Flexible Server (engine: PostgreSQL or MySQL)

```
az graph query -q "resources | where type in~ ('microsoft.dbforpostgresql/flexibleservers','microsoft.dbformysql/flexibleservers') | project name, id, type, subscriptionId, resourceGroup, location, sku, properties" --first 1000
```

- Explicit highAvailability.mode Disabled (Medium only when tier is known). Review eligible engine, compute tier, region, zones and capacity before planning HA. Missing mode or tier is Not assessed.
- Explicit backup.geoRedundantBackup Disabled (Medium). PostgreSQL permits configuration only at server creation; plan a new server and tested migration or restore path when regional recovery is required. Verify MySQL change constraints separately rather than applying PostgreSQL rules to both engines.
- Storage auto grow disabled (Low). Fix: enable auto grow to avoid a storage full outage.
- Public network access enabled (Low). Fix: use private access (VNet integration) and disable public access.

## Cosmos DB (engine: Cosmos DB)

```
az graph query -q "resources | where type =~ 'microsoft.documentdb/databaseaccounts' | project name, id, subscriptionId, resourceGroup, properties" --first 1000
```

- Single region account (Medium). Fix: add a second region.
- Automatic failover disabled on a multi region account (Medium). Fix: enable automatic failover so a regional loss fails over without manual action.
- Periodic backup mode (Low). Fix: consider continuous backup for critical accounts, for point in time restore.

## Severity

Blast radius and likelihood drive severity. Do not infer workload criticality or downgrade a finding from a name alone.

## Evidence limits

Absent or null SQL zone settings, TLS, backup redundancy, Flexible Server HA, backup and storage settings, or Cosmos locations and failover settings are Unknown, not disabled or passing. SQL checks cover selected Premium and Business Critical configurations, not every SKU or capability. Resource Graph fields vary by engine and API version; missing data requires an approved service API read.

Backup and replication configuration does not establish measured RTO or RPO, successful restore, replication lag or application recovery. Obtain business objectives, timed drills and workload dependency evidence separately.

## Sources and validation

- [PostgreSQL backup and restore](https://learn.microsoft.com/en-us/azure/postgresql/backup-restore/concepts-backup-restore), creation only geo backup rule checked 2026-10-21.
- [SQL availability](https://learn.microsoft.com/en-us/azure/azure-sql/database/high-availability-sla-local-zone-redundancy).
- [MySQL HA](https://learn.microsoft.com/en-us/azure/mysql/flexible-server/concepts-high-availability).

Tests are offline fixtures. No live database or endpoint behavior was validated.
