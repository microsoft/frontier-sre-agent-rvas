**[Home](./README.md)** | [Next Solution >](./Solution-01.md)

# Coach Guide — Challenge 00: Validate the Existing Workload

## Purpose

Validate the Terraform-deployed MCAPS food workload without changing it. Expected time: 20–30 minutes.

## Mini-Lecture (5 min before challenge)

Explain the distinction between deployment and validation. This mission proves the existing Container Apps and observability baseline without running Terraform or azd.

## Expected Student Output

The correct MCAPS subscription, Sweden Central resource inventory, running food Container Apps, frontend HTTP `200`, and workspace-backed Application Insights.

## Common Issues and Hints

- **Symptom:** No SRE resource groups are listed. **Fix:** select `MCAPS-Hybrid-REQ-150072-2026-rakau`; do not provision replacements.
- **Symptom:** API root or `/health` returns `404`. **Fix:** use Container App running state, frontend HTTP `200`, and telemetry because the deployed API has no health route.
- **Symptom:** A participant reaches for `terraform apply` or `azd up`. **Fix:** stop and use only the read-only inventory commands in the mission.

## Debrief Discussion Guide

1. Which Azure resources form the existing food application baseline?
2. Which checks prove application health rather than deployment completion?
3. Why should a validation mission avoid deployment commands?

## Success Criteria Notes

Require live resource inventory, both Container Apps in `Running`, frontend HTTP `200`, and the Application Insights workspace relationship. No deployment command is acceptable.
