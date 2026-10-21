# Idle and orphaned resource detection

This is the termination candidate half of the report. It enumerates idle or
orphaned resources across every subscription the agent can read, scores each one
by a confidence to terminate value from 0 to 100, prices it conservatively, and
feeds the `candidates` list that generate_report renders. The agent never
deletes anything. Each candidate carries a copyable az delete command for an
operator to review and run.

## Enumerate with Azure Resource Graph

Azure Resource Graph reads across all accessible subscriptions in one query and
is covered by Reader. Run these with the RunAzCliReadCommands tool. Page with
`--first 1000` and `--skip` if a query returns a full page.

If the resource-graph extension is missing, `az extension add --name resource-graph`
is a one time install; the queries themselves are read only.

Unattached managed disks:

```
az graph query -q "resources | where type =~ 'microsoft.compute/disks' | where tostring(properties.diskState) == 'Unattached' | project name, id, resourceGroup, location, subscriptionId, skuName=tostring(sku.name), diskSizeGB=toint(properties.diskSizeGB), timeCreated=todatetime(properties.timeCreated)" --first 1000
```

Unassociated public IP addresses:

```
az graph query -q "resources | where type =~ 'microsoft.network/publicipaddresses' | where isnull(properties.ipConfiguration) and isnull(properties.natGateway) | project name, id, resourceGroup, location, subscriptionId, skuName=tostring(sku.name), allocation=tostring(properties.publicIPAllocationMethod)" --first 1000
```

Orphan network interfaces:

```
az graph query -q "resources | where type =~ 'microsoft.network/networkinterfaces' | where isnull(properties.virtualMachine) | project name, id, resourceGroup, location, subscriptionId, timeCreated=todatetime(properties.timeCreated)" --first 1000
```

Standalone snapshots (with age and size):

```
az graph query -q "resources | where type =~ 'microsoft.compute/snapshots' | project name, id, resourceGroup, location, subscriptionId, diskSizeGB=toint(properties.diskSizeGB), incremental=tobool(properties.incremental), timeCreated=todatetime(properties.timeCreated)" --first 1000
```

Deallocated virtual machines:

```
az graph query -q "resources | where type =~ 'microsoft.compute/virtualmachines' | extend powerState = tostring(properties.extended.instanceView.powerState.code) | where powerState == 'PowerState/deallocated' | project name, id, resourceGroup, location, subscriptionId, vmSize=tostring(properties.hardwareProfile.vmSize), powerState" --first 1000
```

Empty App Service plans:

```
az graph query -q "resources | where type =~ 'microsoft.web/serverfarms' | where toint(properties.numberOfSites) == 0 | project name, id, resourceGroup, location, subscriptionId, skuName=tostring(sku.name), tier=tostring(sku.tier)" --first 1000
```

Public load balancers with no backend members (heuristic, score low):

```
az graph query -q "resources | where type =~ 'microsoft.network/loadbalancers' | where tostring(sku.name) =~ 'Standard' | extend pools = properties.backendAddressPools | where isnull(pools) or array_length(pools) == 0 | project name, id, resourceGroup, location, subscriptionId, skuName=tostring(sku.name)" --first 1000
```

Storage stays out of the termination set. Deleting a storage account is high
risk, so redundancy and lifecycle savings for storage remain recommendations in
the checks catalog, not termination candidates. Orphaned disks and standalone
snapshots above are review candidates, not safe deletion conclusions.

## Score confidence to terminate

Start from a base by evidence type, apply the adjustments, then clamp to 0 to 100.

Base:

- Unattached disk, unassociated public IP, orphan NIC, standalone snapshot: 80.
- Deallocated virtual machine: 60. Compute is stopped, but parking is often deliberate.
- Empty App Service plan, load balancer with no members: 55.

Age adjustment, from timeCreated where available:

- Older than 90 days: add 10.
- 14 to 90 days: no change.
- Newer than 14 days: subtract 20. Recent resources may be mid provisioning or mid teardown.

Naming adjustment, strongest signal wins:

- Disaster recovery or replica patterns (asr, replica, dr, recoveryvault): cap the score at 20 (Low). Do not propose termination without verified decommissioning.
- Shared network infrastructure (fw, azfw, firewall, natgw, nat, bastion, gateway, hub, shared): subtract 45.
- Hybrid or integration patterns (onprem, hybrid, adds, dc0, domaincontroller): subtract 15.
- Disposable looking names (lab, demo, test, poc, temp, sandbox, spot): no positive score adjustment. Names do not prove nonproduction or idleness. Confirm the environment and workload owner.

Bands: 90 or above Very high, 70 to 89 High, 50 to 69 Medium, below 50 Low.

Optional metric refinement, only when Azure Monitor is readable: for a running
virtual machine, average CPU below 5 percent and low network over 30 days is a
weak idle signal. Treat it as Medium at most and never as a delete default. If
Monitor metrics or Activity Logs are not readable, skip this refinement and mark
idleness unknown. Association and age still provide review evidence, not proof
that deletion is safe. No score substitutes for owner approval, dependency
checks, retention and recovery requirements, locks, or change approval.

## Price conservatively

Use the azure-pricing approach (Azure Retail Prices API) for a lower bound
monthly figure. Label every estimate as a lower bound.

- Managed disk: price by SKU and provisioned size. For Premium SSD v2, price the
  provisioned capacity at the baseline included performance (3000 IOPS, 125 MBps)
  when exact provisioned IOPS and throughput are unknown, and say so in saving_note.
- Snapshot: snapshot storage meter times the size in GB.
- Public IP: the applicable live meter times the stated billing hours assumption.
  If the meter lookup fails, mark the resource unpriced and exclude the estimate;
  do not insert a flat price without currency or source.
- Network interface: no separate hourly charge. Set monthly_saving to 0 and keep
  it as a cleanup candidate.
- Deallocated virtual machine: direct compute saving is 0 because compute is
  already stopped. Note that attached disks and public IPs may still bill; those
  appear as their own candidates where the queries above detect them.
- Empty App Service plan: the plan SKU meter times 730.
- If a resource cannot be priced, set excluded to true with a short exclusion_reason.
  Excluded resources are not counted in the savings total.

## Delete command

Deletion is destructive, not a read only check. Only an authorized operator may
prepare and run a command after owner, dependency, recovery and change approval.
The renderer does not build commands automatically from ids. If an operator
requests a command, retain the exact full resource id:

```
az resource delete --ids '<full resource id>'
```

## Candidate record for the report

Build one object per candidate for the `candidates` list that generate_report
renders:

- resource: the resource name.
- resource_type: a friendly label, for example Managed disk, Snapshot, Public IP,
  Network interface, Virtual machine, App Service plan, Load balancer.
- resource_id: the full Azure resource id.
- subscription: the subscription display name. subscription_id: the id.
- resource_group and location.
- monthly_saving: the lower bound number. saving_note: a short basis, for example
  150 GB Standard HDD managed disk.
- confidence: 0 to 100. band: Very high, High, Medium, or Low (generate_report
  derives the band from confidence if you omit it).
- reason: one line on why it looks unused.
- next_step: the recommended check before deleting.
- delete_command: the az resource delete command above.
- excluded and exclusion_reason: set when the resource could not be priced.

## Sources

- [Cost Management query properties and pagination](https://learn.microsoft.com/javascript/api/@azure/arm-costmanagement/queryproperties)
- [Cost Management access boundaries](https://learn.microsoft.com/azure/cost-management-billing/costs/assign-access-acm-data)

The scoring rubric is a local review heuristic, not a Microsoft safety guarantee.
