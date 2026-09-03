#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TERRAFORM_DIR="${TERRAFORM_DIR:-$(cd "${SCRIPT_DIR}/../../infra" && pwd)}"
source "${SCRIPT_DIR}/common.sh"

require_command curl

health_control_url="$(tf_output parking_vm_health_control_url 2>/dev/null || true)"

if [[ -z "${health_control_url}" || "${health_control_url}" == "null" ]]; then
  echo "Could not determine parking_vm_health_control_url from ${TERRAFORM_DIR}." >&2
  exit 1
fi

set_vm_health() {
  local vm_name="$1"
  local healthy="$2"

  curl -m 10 -sfS \
    -X PATCH \
    "${health_control_url}/api/vm-health/${vm_name}" \
    -H "Content-Type: application/json" \
    -d "{\"healthy\": ${healthy}}" >/dev/null
}

set_vm_health madrid true
set_vm_health paris true

state_json="$(curl -m 10 -sfS "${health_control_url}/api/vm-health/state")"

if [[ "$(jq -r '.data.vms.madrid.healthy' <<<"${state_json}")" != "true" ]]; then
  echo "Madrid VM health did not restore successfully." >&2
  exit 1
fi

if [[ "$(jq -r '.data.vms.paris.healthy' <<<"${state_json}")" != "true" ]]; then
  echo "Paris VM health did not restore successfully." >&2
  exit 1
fi

echo "Parking Manager VM health restored."
echo "${state_json}" | jq .
