**[Home](./README.md)** | [Next Solution >](./Solution-01.md)

# Coach Guide — Challenge 00: Deploy the Workload with azd

## Purpose

Deploy and verify an isolated SignalOps food workload with azd, using the Terraform deployment as the architecture reference. Expected time: 30–40 minutes plus Azure deployment time.

## Mini-Lecture (5 min before challenge)

Explain that azd orchestrates Bicep provisioning plus application packaging and deployment. The named azd environment carries the approved subscription, region, and stage flags; it does not import or take ownership of Terraform state.

## Expected Student Output

- An explicit `signalops-core` azd environment targeting the approved subscription and `swedencentral`.
- A reviewed preview containing only the isolated workload resources.
- A successful `azd up`, two running Container Apps, frontend HTTP `200`, and workspace-backed Application Insights.

## Coach Runbook

1. Before deployment, ask the student to show `AZURE_SUBSCRIPTION_ID`, `AZURE_LOCATION`, `DEPLOY_AGENT`, and `DEPLOY_CONNECTORS` from the selected azd environment.
2. Review the preview together. Expect seven creates and no changes or deletes; the agent resource group must not appear.
3. After deployment, require resource inventory, Container App running state, the frontend HTTP result, and the Application Insights workspace ID.
4. Stop immediately if the preview targets an existing Terraform-managed resource group or proposes replacement/deletion.

## Common Issues and Hints

- **Symptom:** azd targets subscription `0c4a479b-54ab-483a-b4ca-6458b22778f7` from global defaults. **Fix:** recreate or select the mission environment with explicit `--subscription b1e100ca-fff5-4e0e-9847-2e44bf47b68c --location swedencentral`.
- **Symptom:** API root or `/health` returns `404`. **Fix:** use Container App running state, frontend HTTP `200`, and telemetry because the deployed API has no health route.
- **Symptom:** Remote container build is blocked by policy or registry permissions. **Fix:** confirm ACR task permissions; as a fallback, start Docker and set `remoteBuild: false` for both services.
- **Symptom:** The preview includes an agent resource group. **Fix:** confirm `DEPLOY_AGENT=false` and `DEPLOY_CONNECTORS=false` before Mission 00 provisioning.

## Debrief Discussion Guide

1. Which Terraform capabilities are represented in the focused azd workload stage?
2. Why must preview, deployment completion, and runtime health be checked separately?
3. How does a named azd environment prevent accidental ownership of the existing Terraform deployment?

## Success Criteria Notes

- **Require:** explicit environment values, reviewed preview, successful deployment, both apps in `Running`, HTTP `200`, and a non-empty workspace relationship.
- **Reject:** implicit subscription selection, skipped preview, or any operation against a Terraform-managed resource group.
- **Accept:** environment-derived resource names; they do not need to match the Terraform names.
