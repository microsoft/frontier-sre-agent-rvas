# Azure Cost Levers by Service

Per-service playbook for the `cost-optimization-agent`. For each Azure service family: the cost
lever, the signal that justifies it, the read-only check, the matching Azure Advisor
recommendation, and the guardrail. All checks are read-only. Advisor recommendation wording is from
the official catalog (https://learn.microsoft.com/en-us/azure/advisor/advisor-reference-cost-recommendations).

## Compute — Virtual Machines and Scale Sets

| Lever | Signal | Read-only check | Advisor | Guardrail |
| --- | --- | --- | --- | --- |
| Right-size or shut down | Low CPU/memory over 7 days | `az monitor metrics list --metric "Percentage CPU"` | "Right-size or shutdown underutilized virtual machines / scale sets" (High) | Keep instance count ≥ SLA floor for business/mission-critical |
| Deallocate off-hours | Dev-test, idle nights/weekends | Tags + utilization | — | dev-test only |
| Spot for interruptible | Fault-tolerant batch | Workload profile | (AKS Spot) | Never for stateful/critical |

## Managed Disks

| Lever | Signal | Read-only check | Advisor |
| --- | --- | --- | --- |
| Delete unattached disks | Disk not attached to a VM | `az disk list --query "[?managedBy==null]"` | "Review disks that aren't attached to a VM" (Medium) — snapshot before delete |
| Snapshots to Standard storage | Premium snapshots | `az snapshot list` | "Use Standard Storage to store Managed Disks snapshots" (High, ~60%) |
| Standard SSD billing caps | High-IO Standard HDD | Metrics | "Standard SSD disks billing caps" (Medium) |

## App Service

| Lever | Signal | Advisor |
| --- | --- | --- |
| Delete empty plans | Plan with no apps | "Unused/Empty App Service plan" (Medium) |
| Right-size plan | Low CPU 7 days | "Right-size underutilized App Service plans" (Medium) |
| Reserved instances | Steady-state | "Consider App Service reserved instance" (High) |

## Azure Kubernetes Service

| Lever | Advisor |
| --- | --- |
| Vertical Pod Autoscaler (rightsize requests/limits) | "Enable Vertical Pod Autoscaler recommendation mode" (Medium) |
| Cluster Cost Analysis | "Use Azure Kubernetes Service Cost Analysis" (Medium) |
| Aggressive scale-down profile | "Fine-tune the cluster autoscaler profile" (Medium) |
| Spot node pools | "Consider Spot nodes for workloads that can handle interruptions" (Medium) |
| Prometheus-based Container Insights | "Switch to Prometheus-based Container Insights" (Medium, up to 80% on metrics) |

## Azure Cosmos DB

| Lever | Advisor |
| --- | --- |
| Enable autoscale | "Enable autoscale on your Azure Cosmos DB database or container" (Medium) |
| Idle containers | "Consider taking action on the idle Azure Cosmos DB containers" (Medium) |
| Reserved capacity | "Consider Cosmos DB reserved instance" (High) |

## Databases (SQL / MySQL / PostgreSQL)

| Lever | Advisor |
| --- | --- |
| Right-size MySQL | "Right-size underutilized MySQL servers" (Medium) |
| Reserved instances | "Consider SQL PaaS DB / Database for MySQL / PostgreSQL reserved instance" (High) |

## Storage

| Lever | Signal | Read-only check | Advisor |
| --- | --- | --- | --- |
| Lifecycle to cool/cold/archive | Infrequently accessed blobs | `az storage account management-policy show` | — (tier via lifecycle) |
| Revisit classic log retention | Large classic logs | — | "Revisit retention policy for classic log data" (Medium) |
| Premium vs Standard by tx/TB | High transactions/TB | Metrics | "high transactions/TB ratio … premium storage" (Medium) |
| Reservations | Steady Blob v2 / Files | — | "Consider Blob storage / Azure Files reserved instance" (High) |
| Redundancy right-fit | GRS/ZRS where LRS suffices | `az storage account show --query sku` | — (guardrail: only reduce for dev-test) |

## Log Analytics & Azure Monitor

| Lever | Signal | Read-only check | Advisor |
| --- | --- | --- | --- |
| Basic logs plan | >1 GB/mo eligible tables | `Usage` KQL by `DataType` | "Consider configuring the low-cost Basic logs plan" (Low) |
| Commitment (pricing) tier | High steady ingestion | `Usage` KQL volume | "Consider Changing Pricing Tier" (Medium) |
| Investigate ingestion anomaly | Spike vs prior weeks | `Usage` KQL trend | "Data ingestion anomaly was detected" (Medium) |
| Remove unused restored tables | Restored data lingering | `az monitor log-analytics ...` | "Consider removing unused restored tables" (Low) |
| Retention right-fit | Retention > RCA/compliance need | `az monitor log-analytics workspace show --query retentionInDays` | — (guardrail: keep ≥ compliance) |

Observability-specific levers (folded from the prior retention skill): VNet Flow Logs scope and
duplicate-logging avoidance; Traffic Analytics processing interval; flow-log Storage retention and
redundancy; alert noise (threshold/window/cooldown); SRE Agent scheduled-task frequency and
`monthlyAgentUnitLimit`.

## Networking

| Lever | Advisor |
| --- | --- |
| Front Door Classic → Standard/Premium | "Consider migrating to Front Door Standard/Premium" (Medium) |
| Consolidate Front Door endpoints | "Consider using multiple endpoints under one Front Door profile" (Medium) |
| App Gateway/Front Door single-origin probes | "Disable health probes when there's only one origin" (Low) |

## Reservations and Savings Plans (subscription scope)

Advisor surfaces these at subscription scope for steady-state usage: VM, App Service, SQL PaaS,
MySQL, PostgreSQL, Cosmos DB, Redis, Storage (Blob/Files), Managed Disk, Data Explorer, Synapse,
Dedicated Host, NetApp, OpenAI PTU, Fabric, plus "Consider purchasing a savings plan for compute"
and "Configure automatic renewal for the expiring reservations" (High). Recommend only for
workloads the profile marks steady-state; reservations are commitments.

## Orphaned, idle, and off-hours detection (Resource Graph)

Detect waste not always surfaced by Advisor, with read-only `az graph query`:

```bash
# Unattached public IPs
az graph query -q "Resources | where type=='microsoft.network/publicipaddresses' and isnull(properties.ipConfiguration) | project name, resourceGroup, location"

# NICs not attached to a VM
az graph query -q "Resources | where type=='microsoft.network/networkinterfaces' and isnull(properties.virtualMachine) | project name, resourceGroup"

# Load balancers with empty backend pools
az graph query -q "Resources | where type=='microsoft.network/loadbalancers' | where array_length(properties.backendAddressPools)==0 | project name, resourceGroup"

# Snapshots older than 90 days
az graph query -q "Resources | where type=='microsoft.compute/snapshots' | extend age=datetime_diff('day', now(), todatetime(properties.timeCreated)) | where age>90 | project name, resourceGroup, age"
```

Off-hours non-production: correlate `env=dev-test` tags (workload profile) with Azure Monitor
metrics showing near-zero CPU outside working hours, then recommend a scheduled scale-to-zero or
deallocation — never for production.

## References

- Azure Advisor — Cost recommendations (full catalog): https://learn.microsoft.com/en-us/azure/advisor/advisor-reference-cost-recommendations
- Cost Management — Query (Usage) REST API: https://learn.microsoft.com/en-us/rest/api/cost-management/query/usage
- Azure Resource Graph — Overview: https://learn.microsoft.com/en-us/azure/governance/resource-graph/overview
- Well-Architected — Cost Optimization: https://learn.microsoft.com/en-us/azure/well-architected/cost-optimization/
