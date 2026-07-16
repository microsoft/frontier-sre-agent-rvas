#!/usr/bin/env bash
set -euo pipefail

# Deploy (or restore) the Grubify Container Apps to the canonical GHCR images.
# Use this after initial Terraform apply or after a fault-injection scenario.

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

GHCR_API_IMAGE="ghcr.io/microsoft/frontier-sre-agent-rvas/grubify-api:latest"
GHCR_WEB_IMAGE="ghcr.io/microsoft/frontier-sre-agent-rvas/grubify-web:latest"

status_only=""
for arg in "$@"; do
  case "${arg}" in
    --status)
      status_only="true"
      ;;
    *)
      echo "Usage: $0 [--status]" >&2
      exit 1
      ;;
  esac
done

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
    echo "https://${fqdn}"
  fi
}

api_url="$(container_app_url "${api_app_name}")"
frontend_url="$(container_app_url "${frontend_app_name}")"

if [[ -n "${status_only}" ]]; then
  echo "Sample Food Ordering App status"
  echo "Resource group: ${resource_group}"
  echo "API app:        ${api_app_name}"
  echo "Frontend app:   ${frontend_app_name}"
  echo "API URL:        ${api_url:-not available}"
  echo "Frontend URL:   ${frontend_url:-not available}"
  exit 0
fi

echo "Deploying API from ${GHCR_API_IMAGE}"
az containerapp update \
  --name "${api_app_name}" \
  --resource-group "${resource_group}" \
  --image "${GHCR_API_IMAGE}" \
  --output none

api_url="$(container_app_url "${api_app_name}")"
if [[ -z "${api_url}" ]]; then
  echo "Could not resolve API FQDN after update. Check the Container App in Azure Portal." >&2
  exit 1
fi

echo "Deploying frontend from ${GHCR_WEB_IMAGE}"
az containerapp update \
  --name "${frontend_app_name}" \
  --resource-group "${resource_group}" \
  --image "${GHCR_WEB_IMAGE}" \
  --set-env-vars "REACT_APP_API_BASE_URL=${api_url}/api" \
  --output none

frontend_url="$(container_app_url "${frontend_app_name}")"
if [[ -n "${frontend_url}" ]]; then
  echo "Configuring API CORS origin"
  az containerapp update \
    --name "${api_app_name}" \
    --resource-group "${resource_group}" \
    --set-env-vars "AllowedOrigins__0=${frontend_url}" \
    --output none
fi

echo "Sample Food Ordering App deployment complete"
echo "API:      ${api_url}"
echo "Frontend: ${frontend_url:-not available}"
