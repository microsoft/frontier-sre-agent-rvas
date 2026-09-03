#!/usr/bin/env bash
set -euo pipefail

# Report the Terraform-owned Grubify Container Apps without changing their desired state.

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

resource_group="$(sample_food_resource_group_name)"
api_app_name="$(tf_output sample_food_api_container_app_name)"
frontend_app_name="$(tf_output sample_food_frontend_container_app_name)"

container_app_url() {
  local app_name="$1"
  local fqdn
  fqdn="$(az containerapp show \
    --name "${app_name}" \
    --resource-group "${resource_group}" \
    --query "properties.configuration.ingress.fqdn" \
    --output tsv 2>/dev/null | tr -d '\r')"

  if [[ -n "${fqdn}" && "${fqdn}" != "None" ]]; then
    printf 'https://%s\n' "${fqdn}"
  fi
}

api_url="$(container_app_url "${api_app_name}")"
frontend_url="$(container_app_url "${frontend_app_name}")"

echo "Sample Food Ordering App status"
echo "Resource group: ${resource_group}"
echo "API app:        ${api_app_name}"
echo "Frontend app:   ${frontend_app_name}"
echo "API URL:        ${api_url:-not available}"
echo "Frontend URL:   ${frontend_url:-not available}"