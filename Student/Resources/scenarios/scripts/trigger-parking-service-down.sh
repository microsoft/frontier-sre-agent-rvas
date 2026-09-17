#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

paris_vm="$(tf_output parking_paris_vm_name)"
paris_resource_group="$(tf_output_json parking_resource_groups | jq -r '.paris')"

if [[ -z "${paris_vm}" || -z "${paris_resource_group}" ]]; then
  echo "Could not resolve the Paris Parking VM and resource group from Terraform outputs." >&2
  exit 1
fi

echo "Stopping paris-parking-api.service on ${paris_vm} ..."
az vm run-command invoke \
  --resource-group "${paris_resource_group}" \
  --name "${paris_vm}" \
  --command-id RunShellScript \
  --scripts "systemctl stop paris-parking-api.service
logger --tag systemd --priority daemon.warning 'Stopped paris-parking-api.service for Challenge 15'
systemctl is-active paris-parking-api.service || true" \
  --query "value[0].message" \
  --output tsv

cat <<EOF

Paris Parking API service stopped on ${paris_vm}.
Expected detection and remediation path:
- AMA sends the systemd marker to the Syslog table.
- The Sev2 "Paris Parking API Service Down" alert fires within 3-5 minutes.
- Response plan parking-api-service-down routes only to parking-vm-incident-handler.
- The agent restarts ${paris_vm}, then validates the service and localhost API.
Manual restore (if needed): make restore-parking-service
EOF