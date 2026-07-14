#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# In this solution the operational scripts live in Infra/scripts/ and the Terraform root is the
# parent directory (Infra/). REPO_ROOT therefore IS the Terraform directory.
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
TERRAFORM_DIR="${REPO_ROOT}"

require_command() {
  local command_name="$1"
  if ! command -v "${command_name}" >/dev/null 2>&1; then
    echo "Missing required command: ${command_name}" >&2
    exit 1
  fi
}

tf_output() {
  local output_name="$1"
  terraform -chdir="${TERRAFORM_DIR}" output -raw "${output_name}"
}

tf_output_json() {
  local output_name="$1"
  terraform -chdir="${TERRAFORM_DIR}" output -json "${output_name}"
}

hub_resource_group_name() {
  tf_output hub_resource_group_name
}

web_api_resource_group_name() {
  tf_output web_api_resource_group_name
}

data_resource_group_name() {
  tf_output data_resource_group_name
}

sample_food_resource_group_name() {
  tf_output sample_food_resource_group_name
}

# Map a demo-lab VM role to the resource group that now owns it after the
# hub-spoke RG split: client/web VMs -> web-api spoke, api/db -> data spoke,
# nva -> hub connectivity.
vm_resource_group() {
  local role="$1"
  case "${role}" in
  client | client_vm | web_1 | web_2) web_api_resource_group_name ;;
  api | db) data_resource_group_name ;;
  nva) hub_resource_group_name ;;
  *) hub_resource_group_name ;;
  esac
}

vm_name() {
  local key="$1"
  tf_output_json demo_lab_scenario_resource_names | jq -r ".${key}"
}

vm_ip() {
  local key="$1"
  tf_output_json demo_lab_vm_private_ips | jq -r ".${key}"
}

run_on_client() {
  local remote_command="$1"
  az vm run-command invoke \
    --resource-group "$(web_api_resource_group_name)" \
    --name "$(vm_name client_vm)" \
    --command-id RunShellScript \
    --scripts "${remote_command}" \
    --query "value[0].message" \
    --output tsv
}

require_command az
require_command terraform
require_command jq