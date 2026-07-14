# Workflows

This folder uses a separated deployment model with dedicated workflows by concern.

## Operating model

- Workflows in this folder are the **canonical deployment path** for infrastructure changes and day-2 application deployments.
- Helper scripts in `../scripts/` are reserved for **local development**, **first-time bootstrap**, or **break-glass recovery** tasks.
- Current workflows run on **GitHub-hosted runners**.

## Files

- `infra-whatif.yml`: Subscription-scope preview for infrastructure changes
- `infra-deploy.yml`: Manual infrastructure deployment using Bicep
- `deploy-container-apps.yml`: Deploy Lisbon, Berlin, Chaos and optional Berlin MCP and VM Health container apps
- `deploy-vm-apps.yml`: Deploy Paris and Madrid application code to VMs

## Non-workflow helpers

- `../scripts/start-chaos-stack.sh`: local development only
- `../scripts/bootstrap/bootstrap-vm-health-control.sh`: bootstrap or recovery path for VM Health when the workflow is not sufficient
- `../scripts/bootstrap/setup-paris-api.sh`: first-time Paris VM setup only

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

- Use `deploy-container-apps.yml` for normal container image rollouts, including `vm-health-control`.
- Use `deploy-vm-apps.yml` for normal Paris and Madrid code redeploys.
- Use the scripts only when you are preparing hosts, running the stack locally, or recovering a component that needs more than a standard application rollout.
