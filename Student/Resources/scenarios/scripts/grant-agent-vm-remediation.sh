#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/common.sh"

ROLE_NAME="Azure SRE Lab VM Remediator"
ROLE_DESCRIPTION="Least-privilege VM restart and Run Command access for the Azure SRE lab agent."
ARM_API_VERSION="2026-01-01"
ENV_FILE="${REPO_ROOT}/.env"

load_agent_environment() {
  local exported_subscription="${SRE_AGENT_SUB:-}"
  local exported_resource_group="${SRE_AGENT_RG:-}"
  local exported_name="${SRE_AGENT_NAME:-}"

  if [[ -f "${ENV_FILE}" ]]; then
    # shellcheck disable=SC1090
    source "${ENV_FILE}"
  fi

  [[ -n "${exported_subscription}" ]] && SRE_AGENT_SUB="${exported_subscription}"
  [[ -n "${exported_resource_group}" ]] && SRE_AGENT_RG="${exported_resource_group}"
  [[ -n "${exported_name}" ]] && SRE_AGENT_NAME="${exported_name}"

  SRE_AGENT_SUB="${SRE_AGENT_SUB:-$(tf_output subscription_id)}"
  : "${SRE_AGENT_SUB:?Set SRE_AGENT_SUB or deploy the Student Terraform infrastructure.}"
  : "${SRE_AGENT_RG:?Set SRE_AGENT_RG in Student/.env or export it.}"
  : "${SRE_AGENT_NAME:?Set SRE_AGENT_NAME in Student/.env or export it.}"
}

agent_resource_json() {
  local agent_url
  agent_url="https://management.azure.com/subscriptions/${SRE_AGENT_SUB}/resourceGroups/${SRE_AGENT_RG}/providers/Microsoft.App/agents/${SRE_AGENT_NAME}?api-version=${ARM_API_VERSION}"
  az rest --method GET --url "${agent_url}" --output json
}

resolve_agent_principal_id() {
  local agent_json="$1"
  local identity_resource_id
  local principal_id

  identity_resource_id="$(jq -r '
    (.properties.actionConfiguration.identity
      | if type == "string" then . else (.resourceId // .id // empty) end)
    // (.identity.userAssignedIdentities // {} | keys[0])
    // empty
  ' <<<"${agent_json}")"

  if [[ -n "${identity_resource_id}" ]]; then
    principal_id="$(az identity show --ids "${identity_resource_id}" --query principalId --output tsv)"
  else
    principal_id="$(jq -r '.identity.principalId // empty' <<<"${agent_json}")"
  fi

  if [[ -z "${principal_id}" || "${principal_id}" == "null" ]]; then
    echo "Could not resolve a managed identity principal for SRE Agent ${SRE_AGENT_NAME}." >&2
    echo "Confirm the agent has an action identity or a system-assigned identity." >&2
    exit 1
  fi

  printf '%s\n' "${principal_id}"
}

role_definition_json() {
  jq -cn \
    --arg role_name "${ROLE_NAME}" \
    --arg description "${ROLE_DESCRIPTION}" \
    --arg subscription_scope "/subscriptions/${SRE_AGENT_SUB}" \
    '{
      Name: $role_name,
      IsCustom: true,
      Description: $description,
      Actions: [
        "Microsoft.Compute/virtualMachines/read",
        "Microsoft.Compute/virtualMachines/restart/action",
        "Microsoft.Compute/virtualMachines/runCommands/read",
        "Microsoft.Compute/virtualMachines/runCommands/write",
        "Microsoft.Compute/virtualMachines/runCommand/action"
      ],
      NotActions: [],
      DataActions: [],
      NotDataActions: [],
      AssignableScopes: [$subscription_scope]
    }'
}

reconcile_role_definition() {
  local desired_role
  local existing_role
  local expected_actions
  local actual_actions
  local update_role

  desired_role="$(role_definition_json)"
  expected_actions="$(jq -c '.Actions | sort' <<<"${desired_role}")"
  existing_role="$(az role definition list --name "${ROLE_NAME}" --output json)"

  if [[ "$(jq 'length' <<<"${existing_role}")" -eq 0 ]]; then
    echo "Creating custom role: ${ROLE_NAME}" >&2
    if ! az role definition create --role-definition "${desired_role}" --output none; then
      echo "Custom role creation failed. The caller needs Owner or Role Based Access Control Administrator at subscription scope." >&2
      exit 1
    fi
  else
    update_role="$(jq -c \
      --arg role_name "${ROLE_NAME}" \
      --arg description "${ROLE_DESCRIPTION}" \
      --arg subscription_scope "/subscriptions/${SRE_AGENT_SUB}" \
      --argjson actions "$(jq '.Actions' <<<"${desired_role}")" \
      '.[0]
      | .roleName = $role_name
      | .description = $description
      | .permissions = [{
          actions: $actions,
          notActions: [],
          dataActions: [],
          notDataActions: []
        }]
      | .assignableScopes = [$subscription_scope]' <<<"${existing_role}")"
    echo "Reconciling custom role: ${ROLE_NAME}" >&2
    if ! az role definition update --role-definition "${update_role}" --output none; then
      echo "Custom role update failed. The caller needs Owner or Role Based Access Control Administrator at subscription scope." >&2
      exit 1
    fi
  fi

  existing_role="$(az role definition list --name "${ROLE_NAME}" --output json)"
  actual_actions="$(jq -c '.[0].permissions[0].actions | sort' <<<"${existing_role}")"

  if [[ "${actual_actions}" != "${expected_actions}" ]]; then
    echo "The reconciled ${ROLE_NAME} action set does not match the requested VM permissions." >&2
    exit 1
  fi

  jq -r '.[0].id' <<<"${existing_role}"
}

add_vm_resource_group() {
  local label="$1"
  local resource_group="$2"
  local required="$3"
  local vm_names

  if [[ -z "${resource_group}" || "${resource_group}" == "null" ]]; then
    if [[ "${required}" == "true" ]]; then
      echo "Could not resolve required VM resource group: ${label}." >&2
      exit 1
    fi
    echo "Skipping optional ${label} resource group because it is not deployed."
    return
  fi

  vm_names="$(az vm list --resource-group "${resource_group}" --query '[].name' --output tsv)"
  if [[ -z "${vm_names}" ]]; then
    if [[ "${required}" == "true" ]]; then
      echo "Required resource group ${resource_group} contains no virtual machines." >&2
      exit 1
    fi
    echo "Skipping optional resource group ${resource_group} because it contains no virtual machines."
    return
  fi

  VM_RESOURCE_GROUPS+=("${resource_group}")
  VM_NAMES+=("$(tr '\n' ',' <<<"${vm_names}" | sed 's/,$//')")
}

assign_role() {
  local principal_id="$1"
  local role_definition_id="$2"
  local resource_group="$3"
  local scope
  local existing_assignment
  local assignments_json

  scope="/subscriptions/${SRE_AGENT_SUB}/resourceGroups/${resource_group}"
  assignments_json="$(az role assignment list \
    --scope "${scope}" \
    --output json)"
  existing_assignment="$(jq -r \
    --arg principal_id "${principal_id}" \
    --arg role_definition_id "${role_definition_id}" \
    'map(select(
      (.principalId | ascii_downcase) == ($principal_id | ascii_downcase)
      and (.roleDefinitionId | ascii_downcase) == ($role_definition_id | ascii_downcase)
    ))[0].id // empty' <<<"${assignments_json}")"

  if [[ -n "${existing_assignment}" ]]; then
    printf 'existing\n'
    return
  fi

  for attempt in 1 2 3; do
    if az role assignment create \
      --assignee-object-id "${principal_id}" \
      --assignee-principal-type ServicePrincipal \
      --role "${role_definition_id}" \
      --scope "${scope}" \
      --output none; then
      printf 'created\n'
      return
    fi

    if [[ "${attempt}" -lt 3 ]]; then
      echo "Role assignment is not ready yet; retrying (${attempt}/3) ..." >&2
      sleep "$((attempt * 5))"
    fi
  done

  echo "Failed to assign ${ROLE_NAME} on ${resource_group}." >&2
  echo "The caller needs Microsoft.Authorization/roleAssignments/write on this scope, normally through Owner or Role Based Access Control Administrator." >&2
  exit 1
}

require_command az
require_command jq
require_command terraform

load_agent_environment
az account show --query id --output tsv >/dev/null
az account set --subscription "${SRE_AGENT_SUB}"

echo "Azure SRE Agent: ${SRE_AGENT_NAME} (${SRE_AGENT_RG})"
echo "Subscription: ${SRE_AGENT_SUB}"
echo "The caller must be Owner or Role Based Access Control Administrator; Contributor cannot grant RBAC."

agent_json="$(agent_resource_json)"
agent_principal_id="$(resolve_agent_principal_id "${agent_json}")"

declare -a VM_RESOURCE_GROUPS=()
declare -a VM_NAMES=()
parking_resource_groups="$(tf_output_json parking_resource_groups)"

add_vm_resource_group "hub" "$(tf_output hub_resource_group_name)" true
add_vm_resource_group "web/API spoke" "$(tf_output web_api_resource_group_name)" true
add_vm_resource_group "data spoke" "$(tf_output data_resource_group_name)" true
add_vm_resource_group "Parking Madrid" "$(jq -r '.madrid // empty' <<<"${parking_resource_groups}")" false
add_vm_resource_group "Parking Paris" "$(jq -r '.paris // empty' <<<"${parking_resource_groups}")" false

role_definition_id="$(reconcile_role_definition)"
declare -a ASSIGNMENT_STATUSES=()

for resource_group in "${VM_RESOURCE_GROUPS[@]}"; do
  ASSIGNMENT_STATUSES+=("$(assign_role "${agent_principal_id}" "${role_definition_id}" "${resource_group}")")
done

printf '\n%-32s %-48s %-10s\n' "RESOURCE GROUP" "VIRTUAL MACHINES" "ASSIGNMENT"
printf '%-32s %-48s %-10s\n' "--------------" "----------------" "----------"
for index in "${!VM_RESOURCE_GROUPS[@]}"; do
  printf '%-32s %-48s %-10s\n' \
    "${VM_RESOURCE_GROUPS[${index}]}" \
    "${VM_NAMES[${index}]}" \
    "${ASSIGNMENT_STATUSES[${index}]}"
done

echo
echo "Granted ${ROLE_NAME} to the SRE Agent managed identity on all deployed VM resource groups."
echo "Azure RBAC propagation can take several minutes. Retry the autonomous investigation after propagation."