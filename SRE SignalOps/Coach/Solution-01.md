[< Previous Solution](./Solution-00.md) | **[Home](./README.md)** | [Next Solution >](./Solution-02.md)

# Coach Guide — Challenge 01: Establish the Agent Core

## Purpose

Create and verify the agent control plane with a reusable PowerShell context. Expected time: 15–20 minutes.

## Mini-Lecture (5 min before challenge)

Separate ARM provisioning state from data-plane readiness. Review mode is the initial safety boundary.

## Expected Student Output

A running agent, populated endpoint, managed Grubify scope, and ARM/RBAC output.

## Common Issues and Hints

- **Symptom:** Provider registration is pending. **Fix:** use `az provider register --wait`.
- **Symptom:** ARM returns NotFound. **Fix:** verify subscription, resource group, name, and API version.
- **Symptom:** Endpoint is empty. **Fix:** wait for provisioning to reach `Succeeded` and query again.

## Debrief Discussion Guide

1. Why are control and data planes separate?
2. What does Review mode prevent?
3. Which role should a participant receive?

## Success Criteria Notes

Do not pass the mission if the resource exists but has no agent endpoint.
