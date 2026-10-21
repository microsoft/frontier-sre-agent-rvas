# Checks catalog

Readiness checks scoped to one target (a subscription, and optionally a resource group), read with Azure Resource Graph and the usage endpoints, all covered by Reader. The scan tool runs these across three categories and turns the severities into a verdict.

For each finding the tool records: category, resource, subscription, resource group, the issue, a severity, and the recommended change.

## Scope

Every query is filtered to the target: `subscriptionId == '<id>'`, and `resourceGroup =~ '<rg>'` when a resource group is passed. The verdict is about that scope only.

## Reliability

- Virtual machines with no availability zone and no availability set (High). Fix: deploy across zones or an availability set.
- Locally redundant storage (Medium). Fix: use ZRS or GRS where the data warrants it.
- Premium or Business Critical SQL databases without zone redundancy (High). Fix: enable zoneRedundant.

## Internet exposure

- Network security group rules that open management (SSH 22, RDP 3389) or all ports to the internet (Critical), or database ports to the internet (High). Fix: restrict the source or use Private Link.
- Storage accounts allowing anonymous blob access (High). Fix: set allowBlobPublicAccess to false.
- Platform services with public network access enabled (Medium). Fix: use Private Link or restrict to known networks.

## Capacity

- Compute and network usage counters at or above 80 percent of their quota in the regions the scope uses (severity by utilization: 95 percent or higher Critical, 90 or higher High, else Medium). Fix: request a quota increase before the change so scale out does not fail.

## Verdict

Per category, and overall:

- No-go: any Critical or High finding.
- Caution: only Medium findings.
- Incomplete: any required check is not assessed, failed, or the target scope cannot be confirmed. This blocks Go even when there are no findings.
- Go: complete reads, confirmed nonempty scope, finite capacity counters and no findings.

Overall is the worst category verdict. Clear the blocking findings, then run the check again before shipping.

Each configuration query and each capacity endpoint has a recorded assessment state. No matching resources, a failed location discovery, empty usage data, invalid counters or a zero limit must not be treated as spare capacity. An empty result from a risk query is clean only when target inventory visibility has been established. Resource Graph visibility is not proof that the identity can see every intended resource.

These six configuration signals and two usage endpoint families do not assess workload topology, actual zone failover, NSG effective rules or all quotas. One zonal VM or availability set membership alone is not workload redundancy. A quota reading does not guarantee SKU allocation or sufficient headroom for the proposed change.

## Sources and validation

- [View quotas](https://learn.microsoft.com/en-us/azure/quotas/view-quotas).
- [VM reliability](https://learn.microsoft.com/en-us/azure/reliability/reliability-virtual-machines).

Regression tests use mocked collection. No live scope, deployment or endpoint response was validated.
