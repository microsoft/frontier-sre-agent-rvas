INFRA_DIR  := Resources/infra
SCRIPT     := Resources/infra/scripts/sre-agent-config.sh

# Agent configuration.
# Terraform outputs take precedence when available (full infra deployments).
# If the output is empty, values fall back to env vars or .env file.
# Fallback options:
#   Option 1 — .env file in this directory (Student/):
#     echo 'SRE_AGENT_RG=<your-resource-group>'  >> .env
#     echo 'SRE_AGENT_NAME=<your-agent-name>'    >> .env
#   Option 2 — shell export:
#     export SRE_AGENT_RG=<your-resource-group>
#     export SRE_AGENT_NAME=<your-agent-name>
#   Option 3 — inline override:
#     make connectors SRE_AGENT_RG=<rg> SRE_AGENT_NAME=<name>
-include .env
export

# Try Terraform outputs first; fall back to env / .env values if empty.
_TF_SUB   := $(shell terraform -chdir="$(INFRA_DIR)" output -raw subscription_id 2>/dev/null)
_TF_RG    := $(shell terraform -chdir="$(INFRA_DIR)" output -raw agent_resource_group 2>/dev/null)
_TF_NAME  := $(shell terraform -chdir="$(INFRA_DIR)" output -raw agent_name 2>/dev/null)
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
# Usage: make infra TF_VARS='-var="vm_admin_password=MySecret123!"'
TF_VARS ?=

.DEFAULT_GOAL := deploy

SCENARIOS  := Resources/scenarios/scripts

# Scenarios Makefile (includes Parking Manager fault controls)
include Resources/scenarios/Makefile

.PHONY: deploy infra check-env \
        connectors repos knowledge-files skills subagents incident-platforms incident-filters scheduled-tasks config-sre-agent
		
## deploy: provision lab infrastructure (Challenge 00)
deploy: infra

## infra: run terraform init + apply in Resources/infra
infra:
	terraform -chdir="$(INFRA_DIR)" init
	terraform -chdir="$(INFRA_DIR)" apply $(TF_VARS)

# Validate that agent env vars are set before any agent configuration target.
check-env:
ifndef SRE_AGENT_RG
	$(error SRE_AGENT_RG is not set. See the .env instructions at the top of this Makefile.)
endif
ifndef SRE_AGENT_NAME
	$(error SRE_AGENT_NAME is not set. See the .env instructions at the top of this Makefile.)
endif

## connectors: apply connector YAMLs — GitHub OAuth + Microsoft Learn MCP + Berlin MCP (Challenges 01, 04, 07)
connectors: check-env
	$(SCRIPT) apply --target connectors --subscription $(SRE_AGENT_SUB) --resource-group $(SRE_AGENT_RG) --agent $(SRE_AGENT_NAME)

## repos: apply repository link YAMLs — Grubify (Challenge 01)
repos: check-env
	$(SCRIPT) apply --target repos --subscription $(SRE_AGENT_SUB) --resource-group $(SRE_AGENT_RG) --agent $(SRE_AGENT_NAME)

## knowledge-files: upload knowledge documents to agent memory (Challenge 02)
knowledge-files: check-env
	$(SCRIPT) apply --target knowledge-files --subscription $(SRE_AGENT_SUB) --resource-group $(SRE_AGENT_RG) --agent $(SRE_AGENT_NAME)

## skills: apply skill YAMLs (Challenge 03)
skills: check-env
	$(SCRIPT) apply --target skills --subscription $(SRE_AGENT_SUB) --resource-group $(SRE_AGENT_RG) --agent $(SRE_AGENT_NAME)

## subagents: apply subagent YAMLs (Challenge 05)
subagents: check-env
	$(SCRIPT) apply --target subagents --subscription $(SRE_AGENT_SUB) --resource-group $(SRE_AGENT_RG) --agent $(SRE_AGENT_NAME)

## incident-platforms: connect Azure Monitor as the incident source (Challenge 06)
incident-platforms: check-env
	$(SCRIPT) apply --target incident-platforms --subscription $(SRE_AGENT_SUB) --resource-group $(SRE_AGENT_RG) --agent $(SRE_AGENT_NAME)

## incident-filters: apply incident filter / response plan YAMLs (Challenge 06)
incident-filters: check-env
	$(SCRIPT) apply --target incident-filters --subscription $(SRE_AGENT_SUB) --resource-group $(SRE_AGENT_RG) --agent $(SRE_AGENT_NAME)

## scheduled-tasks: apply scheduled task YAMLs (Challenge 06)
scheduled-tasks: check-env
	$(SCRIPT) apply --target scheduled-tasks --subscription $(SRE_AGENT_SUB) --resource-group $(SRE_AGENT_RG) --agent $(SRE_AGENT_NAME)

## config-sre-agent: apply full desired state in one shot (all targets)
config-sre-agent: check-env
	bash "Resources/infra/scripts/.sre-agent-apply-all.sh"
