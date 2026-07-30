#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require_command curl

resource_group="$(sample_food_resource_group_name)"
workspace_id="$(tf_output demo_lab_log_analytics_workspace_customer_id)"
api_app_name="$(tf_output sample_food_api_container_app_name)"
frontend_app_name="$(tf_output sample_food_frontend_container_app_name)"
api_url="$(tf_output sample_food_api_url)"
frontend_url="$(tf_output sample_food_frontend_url)"

echo "Validating Sample Food Ordering App resources"

az containerapp show \
  --name "${api_app_name}" \
  --resource-group "${resource_group}" \
  --query "{name:name,provisioningState:properties.provisioningState,latestRevision:properties.latestRevisionName,traffic:properties.configuration.ingress.traffic}" \
  --output table

az containerapp show \
  --name "${frontend_app_name}" \
  --resource-group "${resource_group}" \
  --query "{name:name,provisioningState:properties.provisioningState,latestRevision:properties.latestRevisionName,traffic:properties.configuration.ingress.traffic}" \
  --output table

echo "Checking HTTP endpoints"
for endpoint in "${api_url}/WeatherForecast" "${api_url}/api/FoodItems" "${api_url}/api/Restaurants" "${frontend_url}"; do
  http_code="$(curl -m 10 -s -o /dev/null -w "%{http_code}" "${endpoint}" || echo "000")"
  echo "${endpoint} -> HTTP ${http_code}"
done

echo "Checking recent Container Apps logs in Log Analytics"
az monitor log-analytics query \
  --workspace "${workspace_id}" \
  --analytics-query "ContainerAppSystemLogs_CL | where TimeGenerated > ago(2h) | where ContainerAppName_s in ('${api_app_name}', '${frontend_app_name}') | summarize Records=count(), LastSeen=max(TimeGenerated) by ContainerAppName_s" \
  --output table || true

az monitor log-analytics query \
  --workspace "${workspace_id}" \
  --analytics-query "ContainerAppConsoleLogs_CL | where TimeGenerated > ago(2h) | where ContainerAppName_s in ('${api_app_name}', '${frontend_app_name}') | summarize Records=count(), LastSeen=max(TimeGenerated) by ContainerAppName_s" \
  --output table || true

az monitor log-analytics query \
  --workspace "${workspace_id}" \
  --analytics-query "ContainerAppHTTPLogs | where TimeGenerated > ago(2h) | where ContainerAppName in ('${api_app_name}', '${frontend_app_name}') | summarize Requests=count(), Errors=countif(toint(StatusCode) >= 400), LastSeen=max(TimeGenerated) by ContainerAppName" \
  --output table || true

echo "Validation complete"