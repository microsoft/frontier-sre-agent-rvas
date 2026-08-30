[< Previous Solution](./Solution-00.md) | **[Home](./README.md)** | [Next Solution >](./Solution-02.md)

# Coach Guide — Challenge 01: Validate the Existing Agent Core

## Purpose

Verify the existing Terraform-deployed agent control plane with a reusable PowerShell context. Expected time: 15–20 minutes.

## Mini-Lecture (5 min before challenge)

Separate ARM provisioning state from data-plane readiness. The controlled lab currently uses Autonomous mode with High access, so customer demonstrations must remain read-only or approval-gated.

## Expected Student Output

A running `contoso-sre-agent-dev`, populated endpoint, complete MCAPS managed-resource list, action configuration, and ARM/RBAC output.

## Common Issues and Hints

- **Symptom:** A participant cannot find `signalops-agent`. **Fix:** use the deployed `rg-sre-agent/contoso-sre-agent-dev`; do not create another agent.
- **Symptom:** ARM returns NotFound. **Fix:** verify subscription, resource group, name, and API version.
- **Symptom:** Endpoint is empty. **Fix:** wait for provisioning to reach `Succeeded` and query again.

## Debrief Discussion Guide

1. Why are control and data planes separate?
2. Which controls are essential when Autonomous mode and High access are already configured?
3. Which role should a participant receive?

## Success Criteria Notes

Do not pass the mission if the endpoint is absent, scope differs from the deployed MCAPS resource set, or action mode/access level are reported inaccurately. Do not change those settings during validation.
