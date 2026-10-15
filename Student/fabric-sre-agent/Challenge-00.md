**[Home](../../README.md)** — [Next Challenge >](./Challenge-01.md)

# Challenge 00 — Prepare the Fabric SRE Agent Lab

> **Capabilities added in this challenge**: Fabric SRE Agent · Fabric Readiness · FinOps and RCA

## Introduction

Reliable analysis starts with knowing which identities, workspaces, capacities,
and data sources the agent can reach. Before building a Fabric SRE Agent, verify
that you can access your infrastructure-provisioned team agent and both
coach-provisioned, shared consumption-data backends.

## Description

Validate the coach's lab handoff and confirm the required administrative
boundaries:

- Identify your running, infrastructure-provisioned Azure SRE Agent and verify
  you have **SRE Agent Administrator** on that agent to configure its capabilities.
  Record its user-assigned managed identity.
- Identify the Fabric tenant, monitored capacities and workspaces, and the
  permissions needed to read item, job, Spark, SQL endpoint, or Eventhouse data.
- Confirm access to the shared FUAM Lakehouse/SQL endpoint and Capacity Events
  Eventhouse/KQL database, their monitored workspaces, and the
  infrastructure-provisioned Fabric capacity.
- Review the Linux tooling, expected Fabric consumption, and data-retention
  implications for both backends before choosing one in Challenge 01.
- Do not provision another agent, capacity, or telemetry stack. The coach sets
  up FUAM and Capacity Events once and shares the relevant items with the audience.
- Keep Fabric data access read-only; tenant/capacity administration and shared
  backend changes belong to the coach and approved administrators.

## Pre-flight Validation Checklist

Run these checks from the Linux environment you will use for the workshop. They
verify local tools and Azure CLI context; they do not prove Fabric permissions
or grant access.

```bash
python3 --version
az version
az account show --query "{name:name,id:id,state:state}" --output table
curl --version
```

Resolve local failures and ask your coach to verify the Azure SRE Agent role,
Fabric tenant settings, shared item access, both prepared data sources, and
network egress before proceeding.

## Success Criteria

- [ ] Local pre-flight commands run successfully in Linux Bash and the intended Azure subscription is identified.
- [ ] The infrastructure-provisioned agent is Running, and SRE Agent Administrator is verified on that agent using the portal or role-assignment evidence.
- [ ] The Fabric capacity, shared telemetry items, monitored workspaces, agent identity, and responsible administrators are recorded.
- [ ] The coach confirms read access to both prepared backends for the audience and the team agent identity.
- [ ] The operating and retention cost trade-offs of FUAM and Capacity Events are understood.
- [ ] **Explain to your coach** — which access checks are tenant-level, which are workspace- or capacity-level, and why Azure RBAC alone does not establish Fabric data access?

## Learning Resources

- [Azure SRE Agent overview](https://learn.microsoft.com/azure/sre-agent/overview)
- [Fabric tenant settings](https://learn.microsoft.com/fabric/admin/tenant-settings-index)
- [Microsoft Fabric Capacity Metrics app](https://learn.microsoft.com/fabric/enterprise/metrics-app)
- [Fabric capacity operation events](https://learn.microsoft.com/fabric/real-time-hub/explore-fabric-capacity-operation-events)

## Tips

- Fabric tenant settings, Fabric item permissions, Azure resource roles, and capacity administration are distinct authorization surfaces.
- A source that is technically reachable may still lack enough history or retention for the question you want to answer.
