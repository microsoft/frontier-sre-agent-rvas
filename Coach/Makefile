INFRA_DIR  := Solutions/infra
APPLY_SCRIPT := Solutions/infra/scripts/.sre-agent-apply-all.sh

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
