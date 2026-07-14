#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

skip_build=""
status_only=""
for arg in "$@"; do
  case "${arg}" in
    --skip-build|--retry)
      skip_build="true"
      ;;
    --status)
      status_only="true"
      ;;
    *)
      echo "Usage: $0 [--skip-build|--retry|--status]" >&2
      exit 1
      ;;
  esac
done

resource_group="$(sample_food_resource_group_name)"
acr_name="$(tf_output sample_food_container_registry_name)"
api_app_name="$(tf_output sample_food_api_container_app_name)"
frontend_app_name="$(tf_output sample_food_frontend_container_app_name)"
source_repo="$(tf_output sample_food_app_source_repo)"
source_ref="$(tf_output sample_food_app_source_ref)"

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
  echo "ACR:            ${acr_name}"
  echo "API app:        ${api_app_name}"
  echo "Frontend app:   ${frontend_app_name}"
  echo "API URL:        ${api_url:-not available}"
  echo "Frontend URL:   ${frontend_url:-not available}"
  exit 0
fi

acr_login_server="$(az acr show --name "${acr_name}" --query loginServer --output tsv)"
api_image="${acr_login_server}/grubify-api:latest"
frontend_image="${acr_login_server}/grubify-frontend:latest"

if [[ -z "${skip_build}" ]]; then
  echo "Building API image from ${source_repo}#${source_ref}:GrubifyApi"
  az acr build \
    --registry "${acr_name}" \
    --image "grubify-api:latest" \
    --file "Dockerfile" \
    "${source_repo}#${source_ref}:GrubifyApi" \
    --no-logs \
    --output none

  echo "Building frontend image from ${source_repo}#${source_ref}:grubify-frontend"
  az acr build \
    --registry "${acr_name}" \
    --image "grubify-frontend:latest" \
    --file "Dockerfile" \
    "${source_repo}#${source_ref}:grubify-frontend" \
    --no-logs \
    --output none
else
  echo "Skipping image builds; deploying existing latest tags from ${acr_login_server}"
fi

echo "Updating API Container App image"
az containerapp update \
  --name "${api_app_name}" \
  --resource-group "${resource_group}" \
  --image "${api_image}" \
  --output none

api_url="$(container_app_url "${api_app_name}")"
if [[ -z "${api_url}" ]]; then
  echo "Could not resolve API FQDN after update. Check the Container App in Azure Portal." >&2
  exit 1
fi

echo "Updating frontend Container App image and API endpoint"
az containerapp update \
  --name "${frontend_app_name}" \
  --resource-group "${resource_group}" \
  --image "${frontend_image}" \
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