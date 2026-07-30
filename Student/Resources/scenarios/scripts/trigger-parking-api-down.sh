#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TERRAFORM_DIR="$(cd "${SCRIPT_DIR}/../../infra" && pwd)"
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

echo "Triggering Parking Manager VM unhealthy state"
echo "Target: ${health_control_url}"

set_vm_health madrid false
set_vm_health paris false

cat <<EOF
Parking Manager unhealthy state triggered for madrid and paris.
Expected evidence:
- VM health metric changes for the Madrid and Paris backend VMs
- New records in Log Analytics table VMHealthStatus_CL
- Alert fires within 3-5 minutes and routes to iaas-vm-incident-handler
Restore with: make restore-parking
EOF
