# Scripts

This folder is intentionally limited to utilities that are **not** the canonical CI/CD deployment path.

## Use these scripts for

- local development orchestration
- first-time host or service bootstrap
- break-glass or recovery operations

## Do not use these scripts for

- normal infrastructure rollouts
- regular container image deployments
- regular Paris or Madrid application redeploys

Those standard deployment paths live in `../workflows/`.

## Layout

- `start-local-stack.sh`: one-command local launcher for the full Parking Manager demo stack

## Local development

- `start-local-stack.sh` installs missing dependencies, builds the frontend when needed, and starts the local backend services plus the frontend proxy.
- This is a local-only convenience script. It is not part of the Azure deployment path.

## Canonical workflow replacements

- Use `../workflows/infra-whatif.yml` and `../workflows/infra-deploy.yml` for infrastructure
- Use `../workflows/deploy-container-apps.yml` for normal container application rollouts, including `vm-health-control`
- Use `../workflows/deploy-vm-apps.yml` for normal Paris and Madrid application redeploys
