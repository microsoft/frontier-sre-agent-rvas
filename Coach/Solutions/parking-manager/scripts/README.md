# Scripts

This folder is intentionally limited to utilities that are **not** the canonical CI/CD deployment path.

## Use these scripts for

- local development
- first-time host or service bootstrap
- break-glass or recovery operations

## Do not use these scripts for

- normal infrastructure rollouts
- regular container image deployments
- regular Paris or Madrid application redeploys

Those standard deployment paths live in `../workflows/`.

## Layout

- `start-chaos-stack.sh`: one-command local development stack launcher
- `bootstrap/`: first-time setup, recovery, and certificate helper scripts

## Bootstrap files

- `bootstrap/bootstrap-vm-health-control.sh`: bootstrap or recovery deployment for VM Health when the normal workflow path is not enough
- `bootstrap/setup-paris-api.sh`: first-time Paris VM setup only
- `bootstrap/generate-paris-certs.sh`: Linux/macOS certificate helper for Paris
- `bootstrap/generate-paris-certs.ps1`: PowerShell certificate helper for Paris
- `bootstrap/generate-madrid-certs.ps1`: PowerShell certificate helper for Madrid

## Canonical workflow replacements

- Use `../workflows/infra-whatif.yml` and `../workflows/infra-deploy.yml` for infrastructure
- Use `../workflows/deploy-container-apps.yml` for normal container application rollouts, including `vm-health-control`
- Use `../workflows/deploy-vm-apps.yml` for normal Paris and Madrid application redeploys
