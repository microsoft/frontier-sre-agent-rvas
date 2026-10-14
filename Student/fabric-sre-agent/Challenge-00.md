**[Home](../../README.md)** — [Next Challenge >](./Challenge-01.md)

# Challenge 00 — Prepare the Fabric SRE Agent Lab

> **Capabilities added in this challenge**: Fabric SRE Agent · Fabric Readiness · FinOps and RCA

## Introduction

Reliable analysis starts with knowing which identities, workspaces, capacities,
and data sources the agent can reach. Before building a Fabric SRE Agent, verify
that you have an approved Fabric environment and can choose either of the two
supported consumption-data backends.

## Description

Establish a safe, isolated lab and confirm the required administrative
boundaries with your coach:

- Identify a running Azure SRE Agent and confirm you can configure its
  capabilities and user-assigned managed identity.
- Identify the Fabric tenant, monitored capacities and workspaces, and the
  permissions needed to read item, job, Spark, SQL endpoint, or Eventhouse data.
- Confirm an approved workspace and capacity are available for FUAM or for the
  Eventstream/Eventhouse monitoring path.
- Review the Linux tooling, expected Fabric consumption, and data-retention
  implications for both backends before choosing one in Challenge 01.
- Keep access read-only; tenant administration and capacity administration
  should be performed only by their approved owners.

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
Fabric tenant settings, capacity/workspace access, approved data source, and
network egress before proceeding.

## Success Criteria

- [ ] Local pre-flight commands run successfully in Linux Bash and the intended Azure subscription is identified.
- [ ] The SRE Agent, Fabric tenant, monitored capacities/workspaces, and responsible administrators are recorded.
- [ ] The coach confirms the least-privilege access path and the source-data backend can be provisioned.
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
