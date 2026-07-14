# Azure SRE Agent — How many agents are needed? The "1 agent per team" anti-pattern (Conway's Law)

Date: 2026-07-04
Scope: **focused and authoritative** answer to the question *"how many Azure SRE Agents are needed and how to
organize them"*, with specific attention to the **"1 agent per team"** anti-pattern. It is the **executive
companion** to the complete fleet guide
[azure-sre-agent-fleet-architecture-guidelines.md](./azure-sre-agent-fleet-architecture-guidelines.md)
(which contains the counting method, the subagent catalogs, and the detailed decision trees).
Audience: Principal/Cloud Architect, Platform Engineering, SRE Lead, CCoE.

> Every key claim is anchored to official Microsoft Learn sources and org-design sources
> (Conway/Fowler, Team Topologies, CAF, WAF), listed at the [bottom](#verified-sources-live). Azure SRE
> Agent is in **public preview**: verify the sources as limits and prices may change.

## Direct Verdict

**"1 agent per team" is a *category error* and collapses into an anti-pattern documented in *both* real
organizational models.** The **number of agents is not a function of teams**: it is a function of
**governance boundaries**. Teams — in whatever form — map to the **internal axis** (subagents), never to
the number of agents. The complete details, with decision tree and pros/cons, are in the fleet guide,
§[4.1](./azure-sre-agent-fleet-architecture-guidelines.md#41-un-agent-per-team-anti-pattern-strutturale-legge-di-conway).

## 1. How enterprise IT teams are organized (concrete example)

The dominant model is organization **by functional silos** (functional silo = team divided by technical
specialization, not by value stream), also called **activity-oriented** (organization by activity/competency):

| Functional team (silo) | Scope | Corresponding Azure SRE Agent subagent |
|---|---|---|
| Network Engineering | VNet, NSG, UDR, firewall, DNS, LB, VPN/ER | `network-expert` |
| Cloud Infra / Platform Eng | Landing zone, IaC, subscription, policy | `config-compliance-auditor` |
| Compute / Systems | VM, AKS, container, OS | `vm-iaas-expert`, `aks-kubernetes-expert` |
| Database / Data | SQL, Cosmos, PostgreSQL, Synapse | `sql-database-expert`, `cosmos-nosql-expert` |
| Application / Software Eng | code, deploy, runtime app | `appservice-functions-expert`, `rca-source-code-expert` |
| Security / IAM | Entra, Key Vault, Defender | `identity-security-expert` |
| SRE / Central NOC | incident, on-call, monitoring | orchestrator + `observability-expert` |

**Certification:** Martin Fowler explicitly documents that *"Teams organized by software layer (e.g. front-end, back-end, and database) lead to dominant PresentationDomainDataLayering structures, which is **problematic because each feature needs close collaboration between the layers**"* — [Conway's Law, Martin Fowler](https://martinfowler.com/bliki/ConwaysLaw.html). This is **exactly** the "1 agent per layer" anti-pattern: cross-layer correlation is the core value and silos destroy it.

## 2. The reductio ad absurdum (certified)

**Conway's Law** (Conway's Law = an organization produces systems whose structure mirrors the communication structure of the organization — [Fowler](https://martinfowler.com/bliki/ConwaysLaw.html)): if you map 1 agent → 1 team, the system *inherits* the team topology. Therefore:

| Real org model (Conway) | "1 agent per team" becomes | Documented anti-pattern | Certification |
|---|---|---|---|
| **Functional silos** (Network/Infra/Compute/DB/App/Sec) | 1 agent per **layer** | ❌ *"1 agent per every layer" = worst anti-pattern* — destroys cross-layer correlation | Fleet guide §1; [Overview — investigation in a **single thread**](https://learn.microsoft.com/en-us/azure/sre-agent/overview); [Fowler — problematic layer teams](https://martinfowler.com/bliki/ConwaysLaw.html) |
| **Stream-aligned** (1 team per workload, "you build it you run it") | 1 agent per **application** | ❌ *"Do not segment by application"* — always-on cost explodes, you lose cross-workload correlation | Fleet guide §1; [Pricing FAQ — *"consolidating workloads under one agent reduces always-on costs"*](https://learn.microsoft.com/en-us/azure/sre-agent/pricing-billing#frequently-asked-questions); [Permissions — one agent covers many RG/subscription](https://learn.microsoft.com/en-us/azure/sre-agent/permissions) |

**Both paths lead to a documented anti-pattern ⇒ "1 agent per team" is void. QED.** Furthermore, **no: stream-aligned teams do NOT save the rule**: "1 agent per workload" is also wrong at scale, because (a) always-on is a fixed cost of 4 AAU/agent-hour from creation to deletion ([Pricing](https://learn.microsoft.com/en-us/azure/sre-agent/pricing-billing)), (b) a single agent already covers many resource groups and multiple subscriptions ([Permissions](https://learn.microsoft.com/en-us/azure/sre-agent/permissions)), and (c) a shared dependency that breaks (hub firewall, APIM, shared DB) impacts *N* workloads and an agent-per-workload does not correlate them. The fleet guide certifies this: with 20 or 100 apps the number of agents **does not change**.

## 3. The resolution: two orthogonal axes

> **Teams map to the INTERNAL axis (subagents). Governance maps to the EXTERNAL axis (number of agents). Never mix them.**

- **Internal axis (Conway → subagent).** The competency of each functional team becomes a **subagent** ("Domain Expert", whose official pattern is literally *"VM Expert, AKS Expert, Network Expert"* — [Custom agents](https://learn.microsoft.com/en-us/azure/sre-agent/sub-agents)), all **inside the same agent** and in the **same thread** with handoff to shared context (*"they share a single conversation context... handoff chains where each specialist builds on the previous agent's work"* — [sub-agents](https://learn.microsoft.com/en-us/azure/sre-agent/sub-agents)). This way cross-layer correlation is **preserved**, not fragmented (App Insights memory trend + GitHub commit + pod restart in the **same thread**, resolution in 7 minutes — [Overview](https://learn.microsoft.com/en-us/azure/sre-agent/overview)). This is the **Inverse Conway Maneuver** (Inverse Conway Maneuver = deliberately designing the structure to achieve the desired architecture — [Fowler](https://martinfowler.com/bliki/ConwaysLaw.html)): the *internal* structure of the agent mirrors the teams, but the *count* does not.
- **External axis (governance → count).** Add an agent **only** when crossing a *governance* boundary: residency/region (hard), Prod/Non-Prod (risk), Platform/Application (blast radius), **independent approval authority** (the *SRE Agent Administrator* role that approves is **per-agent** — [User roles](https://learn.microsoft.com/en-us/azure/sre-agent/user-roles)), permission posture. **None of these is "an engineering team" or "an application".**

Why "approval authority" ≠ "team": CAF itself says that organizational structures *"don't necessarily have to map to an org chart... designed to capture the alignment of roles and responsibilities"* and can be **virtual teams** ([CAF Organize](https://learn.microsoft.com/en-us/azure/cloud-adoption-framework/organize/)). The 7 functional teams become 7 subagents **inside** a few agents governed by the central SRE — which WAF recommends: *"take advantage of centralized operations teams with specialized skills"* ([WAF Operational Excellence](https://learn.microsoft.com/en-us/azure/well-architected/operational-excellence/principles)).

## 4. The actual guidelines, mapped to the 8 quality objectives

| Objective | Actual rule (not "1 per team") | Certification |
|---|---|---|
| **Effectiveness** (accurate RCA) | 1 agent per *correlatable* estate; cross-layer correlation in one thread | [Overview](https://learn.microsoft.com/en-us/azure/sre-agent/overview), [sub-agents](https://learn.microsoft.com/en-us/azure/sre-agent/sub-agents) |
| **Efficiency / Costs** | Consolidate workloads under one agent; the count depends on boundaries, not on apps/teams | [Pricing FAQ](https://learn.microsoft.com/en-us/azure/sre-agent/pricing-billing#frequently-asked-questions) |
| **Accuracy / Precision** | Subagent per domain + knowledge/skill per app → grounding, fewer wasted tokens | [sub-agents (Domain Expert + KB)](https://learn.microsoft.com/en-us/azure/sre-agent/sub-agents), [Pricing — add context](https://learn.microsoft.com/en-us/azure/sre-agent/pricing-billing) |
| **Performance** (MTTR) | One thread, no context-switching between tools | [Overview](https://learn.microsoft.com/en-us/azure/sre-agent/overview) |
| **Resiliency / Reliability** | Per-agent isolation only for Tier-0; persistent knowledge reduces human SPOF | [Security overview](https://learn.microsoft.com/en-us/azure/sre-agent/security-overview), [Overview](https://learn.microsoft.com/en-us/azure/sre-agent/overview) |
| **Security** | Least-privilege RBAC on UAMI (granularity = resource group), Reader+OBO by default, permission gate/Review in prod | [Permissions](https://learn.microsoft.com/en-us/azure/sre-agent/permissions), [User roles](https://learn.microsoft.com/en-us/azure/sre-agent/user-roles) |
| **Governance** | Boundary = **independent** approval authority (per-agent) + Prod/Non-Prod + Platform/App | [User roles](https://learn.microsoft.com/en-us/azure/sre-agent/user-roles), [Permissions](https://learn.microsoft.com/en-us/azure/sre-agent/permissions) |

**Cross-cutting constraint (Team Topologies):** the real limit is **cognitive load** (cognitive load = how much complexity a unit can manage — [Team Topologies](https://teamtopologies.com/key-concepts)). This applies to teams *and* to the agent: an agent with too many subagents/skills saturates configuration budgets — that is why "internal richness" has a ceiling, not "one subagent per app".

## 5. Status: corrections already applied to the fleet guide

The defect was **textual**, not conceptual (the guide already excluded layers and number of apps as
drivers, and counted `K = independent approval domains`, not teams). The following corrections have
**already been applied** to the fleet guide
[azure-sre-agent-fleet-architecture-guidelines.md](./azure-sre-agent-fleet-architecture-guidelines.md):

1. **Renamed** boundary S3 from *"Ownership/Approval (team)"* → **"Independent approval authority (BU/governance)"** (diagram label + tables §5.1/§5.3).
2. **Added** in Part V the anti-pattern entry *"1 agent per team (functional or stream-aligned)"*, with the certified *reductio*.
3. **Added** section §4.1 *"One agent per team: structural anti-pattern (Conway's Law)"* with Inverse Conway Maneuver, team→subagent mapping, decision tree, and pros/cons table.
4. **Extended** glossary and sources (Conway, Inverse Conway, functional silos, stream-aligned, cognitive load; Fowler, Team Topologies, CAF Organize, WAF Operational Excellence).

---

### Summary Table

| Question | Certified answer |
|---|---|
| How are enterprise teams divided? | Functional silos (Network/Infra/Compute/DB/App/Sec) + central SRE |
| Does "1 agent per team" make sense? | **No** — category error |
| Functional silos → | ❌ 1 agent per layer (worst anti-pattern) |
| Stream-aligned → | ❌ 1 agent per app (anti-pattern) |
| What determines the **number** of agents? | **Governance** boundaries (residency, prod/non-prod, platform/app, approval authority), not teams/apps |
| Where do teams end up? | On the **internal axis**: Domain Expert subagents in the same thread |
| Defect in the doc? | **Fixed**: *"(team)"* label of boundary S3 renamed + §4.1 added |

### Glossary
- **Conway's Law:** a system mirrors the communication structure of the organization that builds it.
- **Inverse Conway Maneuver:** deliberately redesigning structure/communication to achieve the desired architecture.
- **Functional silo / activity-oriented org:** team divided by technical specialization (network, infra, app), not by value stream.
- **Stream-aligned team:** team aligned to an end-to-end value stream ("you build it, you run it").
- **Cognitive load:** the amount of complexity a team (or agent) can effectively manage.
- **Cross-layer correlation:** correlating signals from different layers (app+infra+network+deploy) in a single investigation.
- **Subagent / Domain Expert:** specialist agent (e.g. `network-expert`) invoked *inside* an agent, with shared context/thread.
- **Blast radius:** the extent of the impact of an action/failure.
- **Always-on flow (AAU):** fixed cost (4 AAU/agent-hour) of an agent from creation to deletion.
- **UAMI:** User-Assigned Managed Identity of the agent, on which RBAC is based.
- **OBO (on-behalf-of):** temporary elevation using the credentials of an Administrator.

### Verified Sources (live)
- [Azure SRE Agent — Overview](https://learn.microsoft.com/en-us/azure/sre-agent/overview) · [Custom agents](https://learn.microsoft.com/en-us/azure/sre-agent/sub-agents) · [Pricing & billing](https://learn.microsoft.com/en-us/azure/sre-agent/pricing-billing) · [Permissions](https://learn.microsoft.com/en-us/azure/sre-agent/permissions) · [User roles](https://learn.microsoft.com/en-us/azure/sre-agent/user-roles)
- [Conway's Law — Martin Fowler](https://martinfowler.com/bliki/ConwaysLaw.html) · [Team Topologies — Key Concepts](https://teamtopologies.com/key-concepts)
- [CAF — Organize](https://learn.microsoft.com/en-us/azure/cloud-adoption-framework/organize/) · [WAF — Operational Excellence](https://learn.microsoft.com/en-us/azure/well-architected/operational-excellence/principles)
