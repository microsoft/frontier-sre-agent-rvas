# Scoring method

Reliability findings are ranked by severity, which reflects blast radius and likelihood, not the effort to fix. The scan tool assigns a starting severity per signal; confirm or adjust it with evidence.

## Severity bands

- Critical: an outage is likely and the blast radius is wide, for example a shared ingress point or a production database with no failover path. Reserve Critical for signals corroborated by scope (production naming, public exposure, or a large dependency fan in).
- High: a real single point of failure or a retiring platform tier that will force an outage if unaddressed. Most Basic tier and no redundancy signals start here.
- Medium: a redundancy gap that degrades resilience but has a workaround or a smaller blast radius.
- Low: a lower impact gap supported by validated workload context, not a resource name hint.
- Unknown: placement, applicability or workload evidence is insufficient. It is not a pass and makes the report Partial.

## Starting severity by signal

| Signal | Starting severity |
| --- | --- |
| Basic public IP, Basic load balancer | High |
| Compute with no zone or set redundancy | High |
| Premium SQL database without zone redundancy | High |
| Single instance scale set | Medium |
| Locally redundant storage | Medium |
| Application Gateway v2 explicitly pinned to one zone | Medium |
| Application Gateway missing zones, region applicability unverified | Unknown |
| Zonal VM or availability set, workload topology unverified | Unknown |
| AKS system pool below three production nodes | Medium |
| AKS pool zone applicability unverified | Unknown |
| Single region Cosmos DB account | Medium |

## Adjustments

- Never lower a band from substring matches such as dev or test. Names and tags are hints, not authoritative criticality.
- Manual changes require owner validated environment, business impact and dependency evidence. Record the rationale separately.
- Never raise to Critical without at least one corroborating signal beyond the base rule.

## Roll up

The report groups findings by severity and by subscription. Sort the finding table by severity, Critical first. The inline summary leads with the count of Critical and High findings, since those are the ones worth acting on first.

## Sources

- `tools/reliability_scan.py`, local rule implementation.
- [Application Gateway v2 reliability](https://learn.microsoft.com/en-us/azure/reliability/reliability-application-gateway-v2).
- [AKS system pools](https://learn.microsoft.com/en-us/azure/aks/use-system-pools).
