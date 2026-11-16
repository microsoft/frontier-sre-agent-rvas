# Workload Cost Profiles

The keystone context for the `cost-optimization-agent`. Cost optimization is only safe when the
agent knows how critical each workload is and what it requires. The agent reads this file (Step 1
of the method) to weigh every recommendation against criticality, SLA, resiliency, performance,
and budget — so it never trades away capability a workload actually needs to shave the bill.

## Schema

One profile per workload (application/project). Map resources to a profile by resource group or by
tag selector.

| Field | Meaning | Drives |
| --- | --- | --- |
| Workload | Application / project name | Identity |
| Resource selector | Resource group(s) and/or tag filter | Mapping resources to the profile |
| Environment | `prod` / `nonprod` / `dev-test` / `lab` | Aggressiveness of right-sizing and shutdown |
| Criticality tier | `mission-critical` / `business` / `dev-test` | Whether redundancy/retention/capacity may be reduced |
| SLA / SLO | Availability target | Floor for redundancy and instance count |
| Resiliency | single-zone / zone-redundant / multi-region | Whether ZRS→LRS or zone removal is allowed |
| Performance / scalability | Latency target; autoscale range | Whether a smaller SKU is acceptable |
| Monthly budget | Expected spend ceiling | Budget adherence and anomaly threshold |
| Headroom target | Min spare capacity (e.g. keep p95 CPU < 70%) | Floor for right-sizing |
| p95 / p99 latency | Performance SLO percentiles | Whether a smaller SKU is acceptable |
| Seasonal peaks | Known high-demand windows (sales, month-end) | Avoid right-sizing before a peak |
| Failover capacity | Reserved spare for HA / DR | Capacity that must not be removed |
| RTO / RPO | Recovery objectives | Backup / replication that must be preserved |
| Expected growth | Forecast volume trend | Sustainability of current sizing |
| Release calendar | Deployment / freeze windows | Do not recommend changes during a release / freeze |
| Owner | Team / contact | Escalation routing |

## Decision rule (by criticality tier)

| Tier | Allowed optimizations | Not allowed |
| --- | --- | --- |
| `dev-test` | Aggressive right-sizing, off-hours shutdown/deallocation, lowest redundancy (LRS), shortest retention | — |
| `business` | Right-size on confirmed low utilization, rate optimization (reservations/savings plans/Basic logs), consolidation | Reducing required redundancy/retention below SLA |
| `mission-critical` | Rate optimization only (reservations, savings plans, commitment tiers) | Reducing redundancy, retention, capacity, or DR posture |

Unknown production resources default to **business-critical** until profiled.

## Profiles (this environment)

> These are **lab baseline** values for the Contoso SRE Agent demo subscription. Replace them with
> real workload data when this agent is pointed at a production subscription.
>
> **Status of the budget figures below.** They are provisional monthly allocations set by the demo
> programme, derived from the deployed resource mix, not measured spend. They exist because budget
> variance cannot be computed against an empty field: an absent budget silently disables a step of
> the cost method. Reconcile each one against actual spend on the first optimization run and
> replace it with the observed figure.

### grubify-app (Sample Food ordering application)

| Field | Value |
| --- | --- |
| Resource selector | Azure Container Apps `ca-vflta-food-*` (API + frontend); RG `rg-frc-spoke-foodapp-paas`; tag `app=grubify` |
| Environment | `nonprod` (demo-facing) |
| Criticality tier | `business` (used live in demos) |
| SLA / SLO | Best-effort (demo); target no user-visible 5xx during a demo |
| Resiliency | Single-region (Sweden Central), Container Apps managed redundancy |
| Performance / scalability | Container Apps autoscale; API `targetPort` 8080 |
| Monthly budget | EUR 150 — provisional allocation: two Container Apps and one Application Insights resource. Images are pulled from public GitHub Packages, so no Azure Container Registry cost is allocated. |
| Owner | SRE Agent demo team |

### vflta-iaas-lab (hub-spoke IaaS demo)

| Field | Value |
| --- | --- |
| Resource selector | VMs `vm-vflta-*` (client, web-1, web-2, api, db, nva); hub-spoke VNets; Azure Firewall; Bastion; RGs `rg-weu-hub-connectivity` / `rg-weu-spoke-web-api-iaas` / `rg-weu-spoke-data-iaas` |
| Environment | `dev-test` / `lab` |
| Criticality tier | `dev-test` |
| SLA / SLO | None (lab) |
| Resiliency | Single-zone lab topology; internal Standard LB across web-1/web-2 |
| Performance / scalability | Fixed small VM SKUs; no autoscale |
| Monthly budget | EUR 700 — provisional allocation dominated by the two always-on fixed costs, Azure Firewall and Azure Bastion, plus six small virtual machines |
| Owner | SRE Agent demo team |
the dominant fixed costs (evaluate Bastion SKU and firewall tier vs lab need); the NVA VM is
inactive (real NVA is Azure Firewall) → candidate for shutdown.

### observability-platform (telemetry + the agent itself)

| Field | Value |
| --- | --- |
| Resource selector | Log Analytics `law-vflta-*`; flow-logs Storage; Traffic Analytics; agent `appi/law/uai-contoso-sre-agent-dev`; RG `rg-sec-sreagent` |
| Environment | `nonprod` |
| Criticality tier | `business` (required for demos and incident response) |
| SLA / SLO | Telemetry freshness sufficient for demo scenarios |
| Resiliency | Single-region |
| Performance / scalability | LAW pay-as-you-go; flow logs + Traffic Analytics on demo scope |
| Monthly budget | EUR 250 — provisional allocation driven by Log Analytics ingestion and retention, flow-log Storage, and agent unit consumption |
| Owner | SRE Agent demo team |

Optimization notes: Log Analytics retention and table plan (Basic logs), Traffic Analytics
processing interval, flow-log Storage retention/redundancy, and SRE Agent `monthlyAgentUnitLimit`
are the levers — tune for demo, not production retention. Do not disable Traffic Analytics without
explaining the loss of enriched analysis.

## Maintenance

Keep this file current: add a profile per real workload, set true budgets and SLAs, and review
quarterly. The accuracy of every cost recommendation depends on the accuracy of these profiles.
