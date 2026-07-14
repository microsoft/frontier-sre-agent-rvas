# Workflows

This folder uses a separated deployment model with dedicated workflows by concern.

## Operating model

- Workflows in this folder are the **canonical deployment path** for infrastructure changes and day-2 application deployments.
- Helper scripts in `../scripts/` are reserved for **local development**, **first-time bootstrap**, or **break-glass recovery** tasks.
- The local demo stack launcher is `../scripts/start-local-stack.sh`.
- Current workflows run on **GitHub-hosted runners**.

## Files

- `infra-whatif.yml`: Subscription-scope preview for infrastructure changes
- `infra-deploy.yml`: Manual infrastructure deployment using Bicep
- `deploy-container-apps.yml`: Deploy Lisbon, Berlin, Chaos and optional Berlin MCP and VM Health container apps
- `deploy-vm-apps.yml`: Deploy Paris and Madrid application code to VMs

There is currently **no dedicated frontend deployment workflow** in this folder. Frontend hosting is provisioned by infrastructure, and frontend build or publish steps are handled outside these workflow files.

## Non-workflow helpers

- VM Health supporting resources are provisioned by `../infrastructure/main.bicep`, and routine image rollout is handled by `deploy-container-apps.yml`
- Paris VM first-time bootstrap is handled by `../infrastructure/modules/paris-api.bicep` via cloud-init
- Madrid VM first-time bootstrap is handled by `../infrastructure/modules/madrid-api.bicep`
- `../scripts/start-local-stack.sh` is the supported local-only launcher for the full Parking Manager demo stack

## Required secret

- `AZURE_CREDENTIALS`

## Required variables

- `AZURE_CONTAINER_REGISTRY`
- `LISBON_RESOURCE_GROUP`
- `BERLIN_RESOURCE_GROUP`
- `CHAOS_CONTROL_RESOURCE_GROUP`
- `CHAOS_CONTROL_CONTAINER_APP_NAME`
- `BERLIN_MCP_RESOURCE_GROUP` (optional, only for MCP app)
- `VM_HEALTH_RESOURCE_GROUP` (optional, defaults to `CHAOS_CONTROL_RESOURCE_GROUP`)
- `VM_HEALTH_CONTAINER_APP_NAME` (optional, defaults to `ca-vm-health-control`)
- `PARIS_VM_NAME`
- `PARIS_RESOURCE_GROUP`
- `MADRID_VM_NAME`
- `MADRID_RESOURCE_GROUP`
- `DEPLOYMENT_STORAGE_ACCOUNT`
- `CHAOS_CONTROL_URL`

## Recommended deployment order

1. Run `infra-whatif.yml`
2. Run `infra-deploy.yml`
3. Run `deploy-container-apps.yml`
4. Run `deploy-vm-apps.yml`

## Responsibility split

- Use `deploy-container-apps.yml` for normal container image rollouts, including `vm-health-control` after infrastructure has been provisioned.
- Use `deploy-vm-apps.yml` for normal Paris and Madrid code redeploys.
- Use `infra-deploy.yml` only for infrastructure creation or infrastructure updates, not for routine application rollouts.
- Use `../scripts/start-local-stack.sh` only for local development and demos.
- Use the scripts only when you are preparing hosts or recovering a component that needs more than a standard application rollout.
