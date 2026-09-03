[< Previous Solution](./Solution-00.md) | **[Home](./README.md)** | [Next Solution >](./Solution-02.md)

# Coach Guide — Challenge 01: Deploy the Agent Core with azd

## Purpose

Extend the Mission 00 azd environment with an isolated SRE Agent, identity, observability, managed scope, and RBAC. Expected time: 20–30 minutes plus Azure provisioning time.

## Mini-Lecture (5 min before challenge)

Separate ARM provisioning state from data-plane readiness. Highlight the deliberate parity choice of Autonomous/High and the safety improvement: Contributor is scoped to the isolated workload group instead of the whole subscription.

## Expected Student Output

- A running environment-named SRE Agent with a populated endpoint.
- Managed resources that include the isolated workload and its telemetry.
- Autonomous/High action configuration and RBAC output proving workload-scoped write access.

## Coach Runbook

1. Confirm the student reused `signalops-core`, set `DEPLOY_AGENT=true`, and kept `DEPLOY_CONNECTORS=false`.
2. Review the preview for the new agent group, identity, agent telemetry, agent, and RBAC; no existing resource should be replaced.
3. After provisioning, compare ARM state, power state, endpoint, action configuration, managed resources, and role assignments.
4. Stop if Contributor appears at subscription scope. Monitoring Contributor at subscription scope and Contributor on the isolated workload group are expected.

## Common Issues and Hints

- **Symptom:** Agent outputs are empty. **Fix:** select `signalops-core`, set `DEPLOY_AGENT=true`, keep `DEPLOY_CONNECTORS=false`, and provision after preview review.
- **Symptom:** ARM returns NotFound. **Fix:** verify subscription, resource group, name, and API version.
- **Symptom:** Endpoint is empty. **Fix:** wait for provisioning to reach `Succeeded` and query again.
- **Symptom:** Subscription Contributor appears. **Fix:** stop; the isolated azd design should assign subscription Monitoring Contributor and workload-group Contributor only.

## Debrief Discussion Guide

1. Why are control and data planes separate?
2. Why is a managed identity plus resource-group-scoped Contributor safer than subscription Contributor?
3. Which settings match Terraform exactly, and which one intentionally narrows its blast radius?

## Success Criteria Notes

- **Require:** reviewed preview, `Succeeded`/`Running`, a non-empty endpoint, correct managed scope, and the documented role split.
- **Reject:** subscription-wide Contributor, missing workload scope, or claims based only on portal appearance.
- **Accept:** brief endpoint propagation delay after ARM provisioning reaches `Succeeded`.
