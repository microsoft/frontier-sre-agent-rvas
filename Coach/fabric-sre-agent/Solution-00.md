**[Home](../../README.md)** | [Next Solution >](./Solution-01.md)

# Coach Guide — Challenge 00: Prepare the Fabric SRE Agent Lab

## Purpose

- Establish a permission-ready Fabric and Azure SRE Agent environment.
- Explain the difference between Azure resource authorization and Fabric data access.
- Expected time: 30–45 minutes.

## Mini-Lecture (8 min before challenge)

- Fabric tenant settings and Fabric workspace permissions are separate layers.
- The SRE Agent's user-assigned managed identity is the runtime identity; a
  participant's Azure CLI login is not a substitute for it.
- Capacity Events requires capacity-administrator ownership of subscriptions.
- FUAM requires its own tenant/API setup and scheduled refresh path.
- Backend data collection creates ongoing CU cost and retention responsibility.

## Expected Student Output

- Linux tools and Azure CLI context are checked.
- A running SRE Agent, its managed identity, monitored Fabric scope, and named
  administrative owners are recorded.
- A capacity/workspace owner confirms one backend can be provisioned under an
  approved read-only plan.
- Students understand that pre-flight does not grant or certify Fabric access.

## Common Issues and Hints

- **Symptom:** `az account show` reports that no subscription is selected. **Fix:** authenticate Azure in the same Linux environment and select the approved subscription; GitHub login does not authenticate Azure.
- **Symptom:** The SRE Agent is not in `Running` state. **Fix:** ask the agent owner to confirm provisioning and power state before configuring capabilities.
- **Symptom:** The managed identity is absent from Fabric access controls. **Fix:** obtain its principal/client IDs from the agent's Azure identity page and have an authorized Fabric administrator add the identity to the intended security scope.
- **Symptom:** The student has Azure Contributor but cannot query Fabric. **Fix:** verify tenant setting, Fabric workspace permissions, and capacity-specific administration independently.

## Debrief Discussion Guide

- Which identity does the agent use at runtime, and which identity performs setup?
- What is the difference between Azure RBAC and Fabric item authorization?
- Which operator owns the cost and retention of the telemetry backend?

## Success Criteria Notes

- Be strict that runtime identity and data scope are identified.
- Accept an approved non-production tenant/capacity and any supported Linux environment.
- Do not treat successful local CLI checks as proof of Fabric data access.
