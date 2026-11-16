# SQL Server DBA lab: Azure infrastructure (SQL MCP Container App and sample Azure SQL database).
#
# Usage (run from labs/02-sql-server-dba/):
#   make preflight
#   make infra TF_VARS='-var="sql_client_ip_address=<your-public-ip>"'
#   make destroy
#
# Key variables (see resources/infra/variables.tf for the full list):
#   location               - Azure region (default: swedencentral)
#   resource_group_name    - resource group created for this lab (default: rg-sre-dba-rvas)
#   sql_client_ip_address  - public IP allowed through the Azure SQL firewall for setup scripts (default: none)
INFRA_DIR := resources/infra
TF_VARS ?=

.DEFAULT_GOAL := infra

.PHONY: preflight infra destroy outputs

## preflight: read-only checks for the DBA track
preflight:
	bash "$(INFRA_DIR)/scripts/preflight.sh" --track sql-dba

## infra: check prerequisites, then run terraform init + apply in resources/infra
infra: preflight
	terraform -chdir="$(INFRA_DIR)" init
	terraform -chdir="$(INFRA_DIR)" apply $(TF_VARS)

## destroy: destroy all infrastructure managed by the SQL Server DBA Terraform state
destroy:
	terraform -chdir="$(INFRA_DIR)" init
	terraform -chdir="$(INFRA_DIR)" destroy $(TF_VARS)

## outputs: print the SQL MCP URL, identity and SQL server details
outputs:
	terraform -chdir="$(INFRA_DIR)" output
