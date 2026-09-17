#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

paris_vm="$(tf_output parking_paris_vm_name)"
paris_resource_group="$(tf_output_json parking_resource_groups | jq -r '.paris')"

if [[ -z "${paris_vm}" || -z "${paris_resource_group}" ]]; then
  echo "Could not resolve the Paris Parking VM and resource group from Terraform outputs." >&2
  exit 1
fi

echo "Starting and validating paris-parking-api.service on ${paris_vm} ..."
az vm run-command invoke \
  --resource-group "${paris_resource_group}" \
  --name "${paris_vm}" \
  --command-id RunShellScript \
  --scripts "set -e
systemctl start paris-parking-api.service
systemctl is-active paris-parking-api.service
for attempt in \$(seq 1 15); do
  if curl --fail --silent --max-time 10 http://localhost:3003/api/parking | grep -q '\"success\":true'; then
    echo 'Paris Parking API validation succeeded.'
    exit 0
  fi
  sleep 2
done
echo 'Paris Parking API did not recover within 30 seconds.' >&2
exit 1" \
  --query "value[0].message" \
  --output tsv

echo "Paris Parking API service restore complete on ${paris_vm}."