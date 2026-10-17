**[Home](../README.md)** | [Next Solution >](./Solution-01.md)

# Coach Guide — Deployment stage 00: Deploy the Workload with azd

## Purpose

Deploy and verify an isolated SignalOps food workload with azd and Bicep. Expected time: 30–40 minutes plus Azure deployment time.

## Mini-Lecture (5 min before challenge)

Explain that azd orchestrates Bicep provisioning plus application packaging and deployment. The named azd environment carries the approved subscription, region, and stage flags; it owns only the isolated resources created for that environment.

## Expected Student Output

- An explicit `signalops-core` azd environment targeting the approved subscription and `swedencentral`.
- A reviewed preview containing only the isolated workload resources.
- A successful `azd up`, two running Container Apps, frontend HTTP `200`, and workspace-backed Application Insights.

## Coach Runbook

1. Before deployment, ask the student to show `AZURE_SUBSCRIPTION_ID`, `AZURE_LOCATION`, `DEPLOY_AGENT`, and `DEPLOY_CONNECTORS` from the selected azd environment.
2. Review the preview together. Compare every planned resource with the local Bicep entry point and enabled modules; the agent resource group must not appear in the workload-only stage.
3. After deployment, require resource inventory, Container App running state, the frontend HTTP result, and the Application Insights workspace ID.
4. Stop immediately if the preview targets a resource group outside the selected azd environment or proposes replacement/deletion.

## Common Issues and Hints

- **Symptom:** azd targets a different subscription from the active Azure CLI account. **Fix:** select the approved subscription and create or select the matching azd environment with explicit subscription and region values.
- **Symptom:** API root or `/health` returns `404`. **Fix:** use Container App running state, frontend HTTP `200`, and telemetry because the deployed API has no health route.
- **Symptom:** Remote container build is blocked by policy or registry permissions. **Fix:** confirm ACR task permissions; as a fallback, start Docker and set `remoteBuild: false` for both services.
- **Symptom:** The preview includes an agent resource group. **Fix:** confirm `DEPLOY_AGENT=false` and `DEPLOY_CONNECTORS=false` before Deployment stage 00 provisioning.

## Debrief Discussion Guide

1. Which workload and observability resources are created in the Bicep workload stage?
2. Why must preview, deployment completion, and runtime health be checked separately?
3. How do environment-derived names and preview review prevent accidental changes to other environments?

## Success Criteria Notes

- **Require:** explicit environment values, reviewed preview, successful deployment, both apps in `Running`, HTTP `200`, and a non-empty workspace relationship.
- **Reject:** implicit subscription selection, skipped preview, or any operation against a resource group outside the selected environment.
- **Accept:** environment-derived resource names that match the selected environment and deployment outputs.
