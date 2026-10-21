# Evidence collection and analysis

## Collection

### 1. Custom and default NSG rules

Retain securityRules and defaultSecurityRules, all singular/plural source/destination and port fields, ASG references, protocol, direction, access and priority. Defaults are shown separately from custom findings.

```azurecli
az network nsg list --subscription "<subscription_id>" --output json
```

### 2. NSG association and subnet context

Map NIC and subnet networkSecurityGroup IDs to actual target scope. A broad rule in an unassociated NSG is a configuration risk candidate, not demonstrated internet exposure.

```azurecli
az network nic list --subscription "<subscription_id>" --output json
az network vnet list --subscription "<subscription_id>" --output json
```

## Analysis rules

1. Evaluate Allow rules first, separating custom from default and inbound from outbound. Broad Deny rules are not permissive allow findings.
2. Normalize sourceAddressPrefix/sourceAddressPrefixes and destination equivalents. Flag *, Any if returned, 0.0.0.0/0 and ::/0; retain Internet and other service tags as distinct semantics rather than expanding them from memory.
3. Normalize destinationPortRange/destinationPortRanges, parse valid inclusive intervals and compute union cardinality to avoid counting overlaps twice. Flag wildcard ports and ranges spanning more than 100 distinct ports.
4. Apply rules in increasing numeric priority within each direction. Identify potentially shadowed broad rules and preserve uncertainty where ASGs, service tags or multiple target scopes prevent exact local evaluation.
5. Do not exempt broad sources just because ports look like load balancer ports. Only a documented source/service/protocol/purpose match, such as a legitimate AzureLoadBalancer probe rule, can satisfy an approved exception.
6. Report NIC/subnet associations, full source/destination/protocol/ports and the exact triggering condition. Recommend least scope changes for owner review without claiming effective reachability from rule text alone.

## Known limits

- NSG rules alone do not prove public reachability because routing, public IP translation, other NSGs and guest controls also apply.
- Service tags and ASGs require additional membership context for exact shadow or reachability evaluation.

## Expected validation cases

- Healthy: specific source CIDR to approved TCP 443 does not trigger broad source or port range flags.
- Finding: inbound Allow from ::/0 to ports 1000 through 1200 reports 201 ports and broad source.
- Denied or missing: unreadable subnet associations leave exposure unknown, while the observed broad rule remains a configuration finding.

## Sources

- [NSG priority, augmented ranges, state and NAT behavior](https://learn.microsoft.com/en-us/azure/virtual-network/network-security-groups-overview) (consulted 2026-10-21).
- [NSG, NIC and VNet read commands](https://learn.microsoft.com/en-us/cli/azure/network?view=azure-cli-latest) (consulted 2026-10-21).
