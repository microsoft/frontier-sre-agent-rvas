PARKING_MANAGER_ROOT := Student/Resources/parking-manager
INFRA_DIR  := Student/Resources/infra

.DEFAULT_GOAL := deploy

.PHONY: deploy

## infra: run terraform init + apply in the infra directory
deploy:
	terraform -chdir="$(INFRA_DIR)" init
	terraform -chdir="$(INFRA_DIR)" apply $(TF_VARS)