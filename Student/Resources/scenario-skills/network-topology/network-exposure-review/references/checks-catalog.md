# Checks catalog

Internet exposure signals detected with Azure Resource Graph, covered by Reader. The scan tool runs these; this catalog is the source of truth for each signal and its fix. Run any command by hand with the RunAzCliReadCommands tool to verify a finding.

For each finding the tool records: resource, exposure type, subscription, resource group, what is open, a severity, and the recommended change.

HTTP reads use `shared\tools\azure_http.py` and the bundled governance policy for approved HTTPS hosts, explicit timeouts, disabled redirects and bounded transient retries. Authorization failures are not retried. Deployed bundles must include the shared tools and policy.

## 1. Broad NSG Allow configurations

Pull inbound allow rules, then classify the ports in the tool.

```
az graph query -q "resources | where type =~ 'microsoft.network/networksecuritygroups' | mv-expand rule = properties.securityRules | extend p = rule.properties | where tostring(p.direction) =~ 'Inbound' and tostring(p.access) =~ 'Allow' | project name, id, resourceGroup, subscriptionId, ruleName=tostring(rule.name), src=tostring(p.sourceAddressPrefix), srcs=p.sourceAddressPrefixes, portRange=tostring(p.destinationPortRange), portRanges=p.destinationPortRanges" --first 1000
```

A broad source includes `*`, `Internet`, IPv4 `0.0.0.0/0`, IPv6 `::/0` and equivalent unions within one address family across scalar and plural source fields. Unknown prefixes and unresolved service tags are review candidates. Narrow public ranges are outside this broad source check, not proven safe. Severity describes the Allow configuration, not proven reachability:

- Critical: all ports (*), or management ports (SSH 22, RDP 3389, WinRM 5985 and 5986) open to the internet.
- High: database ports (1433 SQL, 3306 MySQL, 5432 PostgreSQL, 6379 Redis, 27017 Mongo, 1521 Oracle) open to the internet.
- Medium: other specific ports open to the internet.

Before confirming exposure, evaluate rule priority, protocol and destination, NIC and subnet effective rules, public IP association, routes and any intermediary firewall or listener. A higher priority Deny or another NSG can block this Allow configuration. A load balancer alone is not an access restriction. Restrict unnecessary broad access after owner review.

## 2. Storage with anonymous or public access

```
az graph query -q "resources | where type =~ 'microsoft.storage/storageaccounts' | where tostring(properties.allowBlobPublicAccess) =~ 'true' | project name, id, resourceGroup, subscriptionId" --first 1000
```

Severity Medium, review needed. The account setting permits anonymous blob access but does not prove that any container is public or reachable. Review container access and network restrictions. Set allowBlobPublicAccess to false unless anonymous access is a deliberate requirement.

Open network access (no firewall):

```
az graph query -q "resources | where type =~ 'microsoft.storage/storageaccounts' | where tostring(properties.publicNetworkAccess) =~ 'Enabled' and tostring(properties.networkAcls.defaultAction) =~ 'Allow' | project name, id, resourceGroup, subscriptionId" --first 1000
```

Severity Medium. Fix: set the network default action to Deny and allow only known networks, or use Private Link.

## 3. Platform services with public network access

```
az graph query -q "resources | where type in~ ('microsoft.sql/servers','microsoft.keyvault/vaults','microsoft.documentdb/databaseaccounts','microsoft.dbforpostgresql/flexibleservers','microsoft.dbformysql/flexibleservers') | extend pna = tostring(properties.publicNetworkAccess) | where pna =~ 'Enabled' | project name, id, type, resourceGroup, subscriptionId" --first 1000
```

Severity Medium, review needed. `publicNetworkAccess=Enabled` is not proof of unrestricted SQL or PaaS access. Check the service firewall, defaultAction, IP and virtual network rules and exceptions, or report those controls Not assessed. The collector also retains missing or unknown publicNetworkAccess settings for review; it does not silently treat them as disabled.

## Severity summary

- Critical: broad Allow configuration for management or all ports.
- High: broad Allow configuration for database ports.
- Medium: other broad Allow configurations, unknown sources and public access settings requiring review.

A resource can produce more than one finding when it is exposed in more than one way.

Preserve full resource ids and available rule ids. Count distinct ids rather than resource names. Reports remain Partial until effective reachability and scope completeness are established; empty unknown scope is Not assessed.

## Sources

Verified against Microsoft Learn during this correction:

- [NSG processing at subnet and NIC](https://learn.microsoft.com/azure/virtual-network/network-security-group-how-it-works)
- [SQL public endpoints and firewall access](https://learn.microsoft.com/azure/azure-sql/database/network-access-controls-overview)
