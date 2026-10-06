#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="${SCRIPT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"
REPO_ROOT="${REPO_ROOT:-$(cd "${SCRIPT_DIR}/../../.." && pwd)}"
TERRAFORM_DIR="${TERRAFORM_DIR:-${REPO_ROOT}/Resources/infra}"

require_command() {
  local command_name="$1"
  if ! command -v "${command_name}" >/dev/null 2>&1; then
    echo "Missing required command: ${command_name}" >&2
    exit 1
  fi
}

tf_output() {
  local output_name="$1"
  terraform -chdir="${TERRAFORM_DIR}" output -json | jq -er --arg output_name "${output_name}" '.[$output_name].value // empty'
}

tf_output_json() {
  local output_name="$1"
  terraform -chdir="${TERRAFORM_DIR}" output -json | jq -ce --arg output_name "${output_name}" '.[$output_name].value // empty'
}

rvas_resource_group_name() {
  tf_output rvas_resource_group_name
}

parking_vm_health_control_url() {
  tf_output parking_vm_health_control_url
}

parking_berlin_mcp_url() {
  tf_output parking_berlin_mcp_url
}

parking_chaos_control_url() {
  tf_output parking_chaos_control_url
}

# All demo-lab VM roles now live in the single shared workload resource group.
vm_resource_group() {
  rvas_resource_group_name
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
  timeout 660 az vm run-command invoke \
    --resource-group "$(rvas_resource_group_name)" \
    --name "$(vm_name client_vm)" \
    --command-id RunShellScript \
    --scripts "${remote_command}" \
    --query "value[0].message" \
    --output tsv
}

require_command az
require_command terraform
require_command jq