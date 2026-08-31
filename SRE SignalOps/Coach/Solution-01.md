[< Previous Solution](./Solution-00.md) | **[Home](./README.md)** | [Next Solution >](./Solution-02.md)

# Coach Guide — Challenge 01: Deploy the Agent Core with azd

## Purpose

Extend the Mission 00 azd environment with an isolated SRE Agent, identity, observability, managed scope, and RBAC. Expected time: 20–30 minutes plus Azure provisioning time.

## Mini-Lecture (5 min before challenge)

Separate ARM provisioning state from data-plane readiness. Highlight the deliberate parity choice of Autonomous/High and the safety improvement: Contributor is scoped to the isolated workload group instead of the whole subscription.

## Expected Student Output

A running environment-named agent, populated endpoint, managed-resource list, Autonomous/High action configuration, and RBAC output proving workload-scoped write access.

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

Do not pass if preview was skipped, the endpoint is absent, managed resources omit the isolated workload, action mode/access are inaccurate, or the identity receives subscription-wide Contributor.
