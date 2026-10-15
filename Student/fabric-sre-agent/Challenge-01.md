[< Previous Challenge](./Challenge-00.md) — **[Home](../../README.md)** — [Next Challenge >](./Challenge-02.md)

# Challenge 01 — Select and Validate a Shared Consumption Backend

> **Capabilities added in this challenge**: FUAM or Capacity Events · Consumption Evidence

## Introduction

An agent can only explain consumption that its telemetry source actually
records. This challenge compares two coach-provisioned, shared sources, then
validates one as the source of truth for your team's agent.

## Description

Use the coach's handoff and the two backend reference guides in
[`Student/Resources/fabric-sre-agent/`](../Resources/fabric-sre-agent/README.md)
to select and validate **one shared** backend:

- **FUAM** uses the Capacity Metrics app and a Lakehouse. It provides daily
  consumption by item and operation, with per-execution notebook CU derived
  from Spark allocation.
- **Capacity Events** streams capacity operation events to an Eventhouse. It
  can provide exact CU per operation, but has finite history and continuously
  consumes capacity while running.
- Verify your read access and that the source contains usable data; record its workspace, item,
  endpoint, capacity, region, freshness, and history-retention details.
- Document why your team chose the backend and what precision it cannot
  provide.

The coach deploys both backends once and shares their relevant items with the
audience. Do not deploy another FUAM instance, Eventstream, Eventhouse, or
subscription, or change shared refresh and retention settings. Escalate missing
access or data to the coach.

Do not paste connection strings, tokens, client secrets, or tenant identifiers
into public notes or source control. A single agent uses one backend-specific
instruction set at a time.

## Success Criteria

- [ ] The selected coach-provisioned backend returns recent consumption evidence for a known workload using the shared read-access path.
- [ ] The selected source, data grain, start of retained history, latest available data, and operating-cost implications are recorded.
- [ ] The team documents the alternative backend and the use case that would justify choosing it instead.
- [ ] The agent has not been given write access to Fabric items or KQL management operations.
- [ ] **Explain to your coach** — when is daily FUAM evidence preferable, and when does per-operation event evidence justify the always-on monitoring cost?

## Learning Resources

- [FUAM setup guide](../Resources/fabric-sre-agent/fuam/README.md)
- [Capacity Events setup guide](../Resources/fabric-sre-agent/capacity-events/README.md)
- [FUAM deployment guide](https://github.com/microsoft/fabric-toolbox/blob/main/monitoring/fabric-unified-admin-monitoring/how-to/How_to_deploy_FUAM.md)
- [Capacity operation events schema](https://learn.microsoft.com/fabric/real-time-hub/explore-fabric-capacity-operation-events#operation-events-schema)

## Tips

- Capacity Events retains no history from before its subscription started.
- Backend deployment and administrative grants are coach-owned; validate shared access rather than broadening permissions.
