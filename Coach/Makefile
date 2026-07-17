INFRA_DIR  := Solutions/infra
APPLY_SCRIPT := Solutions/infra/scripts/.sre-agent-apply-all.sh

# Optional Terraform variable overrides, passed directly to terraform apply.
# Usage examples:
#   make infra TF_VARS='-var="create_network_watcher=true"'
#   make infra TF_VARS='-var="create_network_watcher=true" -var="vm_admin_password=MySecret123!"'
#
# Key variables (see Solutions/infra/variables.tf for full list):
#   create_network_watcher      — set to true if NetworkWatcherRG does not already exist (default: false)
#   vm_admin_password           — admin password for Madrid and Paris parking VMs (no default, required)
#   deploy_madrid_vm            — set to false to skip the Madrid Windows VM (default: true)
#   deploy_paris_vm             — set to false to skip the Paris Ubuntu VM (default: true)
#   create_parking_public_ips   — set to true to attach public IPs to parking VMs (default: false)
TF_VARS ?=

.DEFAULT_GOAL := deploy

.PHONY: deploy infra config-sre-agent

## deploy: provision infrastructure then configure the Azure SRE Agent
deploy: infra config-sre-agent

## infra: run terraform init + apply in Solutions/infra
infra:
	terraform -chdir="$(INFRA_DIR)" init
	terraform -chdir="$(INFRA_DIR)" apply $(TF_VARS)

## config-sre-agent: run the full validate → plan → apply → verify cycle
config-sre-agent:
	bash "$(APPLY_SCRIPT)"
