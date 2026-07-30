INFRA_DIR  := Solutions/infra
APPLY_SCRIPT := ../Student/Resources/infra/scripts/.sre-agent-apply-all.sh
SCENARIOS  := ../Student/Resources/scenarios/scripts

# Agent configuration resolved from Terraform outputs.
# If outputs are empty, falls back to env vars or .env file.
-include .env
export

_TF_SUB  := $(shell terraform -chdir="$(INFRA_DIR)" output -raw subscription_id 2>/dev/null)
_TF_RG   := $(shell terraform -chdir="$(INFRA_DIR)" output -raw agent_resource_group 2>/dev/null)
_TF_NAME := $(shell terraform -chdir="$(INFRA_DIR)" output -raw agent_name 2>/dev/null)
_TF_BERLIN_MCP_URL := $(shell terraform -chdir="$(INFRA_DIR)" output -raw parking_berlin_mcp_url 2>/dev/null)

ifneq ($(_TF_SUB),)
SRE_AGENT_SUB := $(_TF_SUB)
endif
SRE_AGENT_SUB ?=

ifneq ($(_TF_RG),)
SRE_AGENT_RG := $(_TF_RG)
endif
SRE_AGENT_RG ?=

ifneq ($(_TF_NAME),)
SRE_AGENT_NAME := $(_TF_NAME)
endif
SRE_AGENT_NAME ?=

ifneq ($(_TF_BERLIN_MCP_URL),)
BERLIN_MCP_URL := $(_TF_BERLIN_MCP_URL)
endif
BERLIN_MCP_URL ?=

BERLIN_MCP_AUTH_TOKEN ?=
export BERLIN_MCP_AUTH_TOKEN

ifneq ($(BERLIN_MCP_AUTH_TOKEN),)
TF_VAR_berlin_mcp_auth_token := $(BERLIN_MCP_AUTH_TOKEN)
endif

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

include ../Student/Resources/scenarios/Makefile

## deploy: provision infrastructure then configure the Azure SRE Agent
deploy: infra config-sre-agent

## infra: run terraform init + apply in Solutions/infra
infra:
	terraform -chdir="$(INFRA_DIR)" init
	terraform -chdir="$(INFRA_DIR)" apply $(TF_VARS)

## config-sre-agent: run the full validate → plan → apply → verify cycle
## (script and config files live in Student/Resources — single source of truth)
config-sre-agent:
	bash "$(APPLY_SCRIPT)"
