**[Home](./README.md)** | [Next Solution >](./Solution-01.md)

# Coach Guide — Challenge 00: Launch the Workload

## Purpose

Deploy a known Grubify baseline using `azd` and PowerShell. Expected time: 20–30 minutes.

## Mini-Lecture (5 min before challenge)

Explain that `azd` binds Bicep, application packaging, deployment, and named environment values. It does not deploy the separate Terraform network lab.

## Expected Student Output

A selected `signalops` environment, successful `azd up`, working frontend/API URLs, and a resource inventory.

## Common Issues and Hints

- **Symptom:** Docker connection fails. **Fix:** start Docker Desktop and rerun `docker info`.
- **Symptom:** Deployment uses the wrong subscription. **Fix:** compare `az account show` with `azd env get-value AZURE_SUBSCRIPTION_ID`.
- **Symptom:** Name conflict or stale environment. **Fix:** select the intended azd environment before provisioning.

## Debrief Discussion Guide

1. What belongs to azd environment state?
2. Which checks prove application health rather than deployment completion?
3. Why is the network sandbox explicitly separate?

## Success Criteria Notes

Require endpoint checks and `azd env get-values`; a successful provisioning command alone is insufficient.
