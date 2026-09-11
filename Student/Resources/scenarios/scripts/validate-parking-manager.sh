#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require_command curl

frontend_name="$(tf_output parking_frontend_name)"
frontend_rg="$(tf_output parking_frontend_resource_group_name)"
frontend_url="$(tf_output parking_frontend_url)"
parking_network="$(tf_output_json parking_network)"
parking_resource_groups="$(tf_output_json parking_resource_groups)"

if [[ -z "${frontend_name}" || -z "${frontend_rg}" || -z "${frontend_url}" ]]; then
  echo "Could not determine the Parking Manager Web App from Terraform outputs." >&2
  exit 1
fi

frontend_url="${frontend_url%/}"

echo "Validating Parking Manager Web App"
webapp_json="$(az webapp show \
  --name "${frontend_name}" \
  --resource-group "${frontend_rg}" \
  --query '{name:name,state:state,defaultHostName:defaultHostName,httpsOnly:httpsOnly,publicNetworkAccess:publicNetworkAccess,virtualNetworkSubnetId:virtualNetworkSubnetId}' \
  --output json)"
echo "${webapp_json}" | jq .

state="$(jq -r '.state // ""' <<<"${webapp_json}")"
https_only="$(jq -r '.httpsOnly // false' <<<"${webapp_json}")"
public_access="$(jq -r '.publicNetworkAccess // ""' <<<"${webapp_json}")"
integration_subnet_id="$(jq -r '.virtualNetworkSubnetId // ""' <<<"${webapp_json}")"

if [[ "${state}" != "Running" ]]; then
  echo "Parking Manager Web App is not running (state: ${state:-<missing>})." >&2
  exit 1
fi
if [[ "${https_only}" != "true" ]]; then
  echo "Parking Manager Web App does not enforce HTTPS." >&2
  exit 1
fi
if [[ "${public_access,,}" != "enabled" ]]; then
  echo "Parking Manager public network access is not enabled (value: ${public_access:-<missing>})." >&2
  exit 1
fi
if [[ -z "${integration_subnet_id}" ]]; then
  echo "Parking Manager Web App has no VNet integration subnet." >&2
  exit 1
fi

expected_frontend_subnet_id="$(jq -r '.frontend_subnet_id' <<<"${parking_network}")"
expected_vm_subnet_id="$(jq -r '.vm_subnet_id' <<<"${parking_network}")"
expected_nat_gateway_id="$(jq -r '.vm_nat_gateway_id' <<<"${parking_network}")"
parking_vnet_name="$(jq -r '.vnet_name' <<<"${parking_network}")"
if [[ "${integration_subnet_id,,}" != "${expected_frontend_subnet_id,,}" ]]; then
  echo "Parking Manager Web App is not integrated with the dedicated Parking frontend subnet." >&2
  exit 1
fi

for city in madrid paris; do
  vm_name="$(tf_output "parking_${city}_vm_name")"
  [[ -n "${vm_name}" ]] || continue
  vm_rg="$(jq -r --arg city "${city}" '.[$city]' <<<"${parking_resource_groups}")"
  nic_id="$(az vm show --name "${vm_name}" --resource-group "${vm_rg}" --query 'networkProfile.networkInterfaces[0].id' --output tsv)"
  vm_subnet_id="$(az network nic show --ids "${nic_id}" --query 'ipConfigurations[0].subnet.id' --output tsv)"
  if [[ "${vm_subnet_id,,}" != "${expected_vm_subnet_id,,}" ]]; then
    echo "${city^} VM is not attached to the dedicated Parking VM subnet." >&2
    exit 1
  fi
done
echo "Parking frontend, Madrid VM, and Paris VM use the dedicated Parking VNet."

peering_count="$(az network vnet peering list \
  --resource-group "${frontend_rg}" \
  --vnet-name "${parking_vnet_name}" \
  --query 'length(@)' \
  --output tsv)"
if [[ "${peering_count}" != "0" ]]; then
  echo "Parking VNet must not have any VNet peerings (found: ${peering_count})." >&2
  exit 1
fi

vm_subnet_json="$(az network vnet subnet show --ids "${expected_vm_subnet_id}" --output json)"
vm_route_table_id="$(jq -r '.routeTable.id // ""' <<<"${vm_subnet_json}")"
vm_nat_gateway_id="$(jq -r '.natGateway.id // ""' <<<"${vm_subnet_json}")"
if [[ -n "${vm_route_table_id}" ]]; then
  echo "Parking VM subnet unexpectedly has a route table: ${vm_route_table_id}" >&2
  exit 1
fi
if [[ "${vm_nat_gateway_id,,}" != "${expected_nat_gateway_id,,}" ]]; then
  echo "Parking VM subnet is not associated with its dedicated NAT Gateway." >&2
  exit 1
fi
echo "Parking VNet has no peerings or route tables; VM outbound uses its dedicated NAT Gateway."

echo "Checking App Service container and routing configuration"
config_json="$(az webapp config show \
  --name "${frontend_name}" \
  --resource-group "${frontend_rg}" \
  --query '{linuxFxVersion:linuxFxVersion,healthCheckPath:healthCheckPath,vnetRouteAllEnabled:vnetRouteAllEnabled}' \
  --output json)"
echo "${config_json}" | jq .

linux_fx_version="$(jq -r '.linuxFxVersion // ""' <<<"${config_json}")"
health_path="$(jq -r '.healthCheckPath // ""' <<<"${config_json}")"
route_all="$(jq -r '.vnetRouteAllEnabled // false' <<<"${config_json}")"

if [[ "${linux_fx_version}" != DOCKER\|* ]]; then
  echo "Parking Manager Web App is not configured with a custom container." >&2
  exit 1
fi
if [[ "${health_path}" != "/health" ]]; then
  echo "Unexpected Web App health check path: ${health_path:-<missing>}." >&2
  exit 1
fi
if [[ "${route_all}" != "false" ]]; then
  echo "VNet route-all must remain disabled so public traffic bypasses the lab firewall." >&2
  exit 1
fi

route_table_id="$(az network vnet subnet show --ids "${integration_subnet_id}" --query 'routeTable.id' --output tsv 2>/dev/null || true)"
if [[ -n "${route_table_id}" ]]; then
  echo "Parking Manager integration subnet unexpectedly has a route table: ${route_table_id}" >&2
  exit 1
fi
echo "VNet integration is enabled and its subnet has no route table."

check_endpoint() {
  local label="$1"
  local path="$2"
  local response_type="$3"
  local endpoint="${frontend_url}${path}"
  local response_file
  local http_code="000"
  local attempt

  response_file="$(mktemp)"
  for attempt in 1 2 3 4 5; do
    http_code="$(curl \
      --connect-timeout 10 \
      --max-time 30 \
      --silent \
      --show-error \
      --location \
      --output "${response_file}" \
      --write-out '%{http_code}' \
      "${endpoint}" 2>/dev/null || true)"
    http_code="${http_code:-000}"

    if [[ "${http_code}" =~ ^2[0-9][0-9]$ ]]; then
      case "${response_type}" in
        html)
          if grep -Eqi '<!doctype html|<html' "${response_file}"; then
            printf 'PASS  %-32s HTTP %s  %s\n' "${label}" "${http_code}" "${path}"
            rm -f "${response_file}"
            return 0
          fi
          ;;
        health)
          if jq -e '.status == "healthy"' "${response_file}" >/dev/null 2>&1; then
            printf 'PASS  %-32s HTTP %s  %s\n' "${label}" "${http_code}" "${path}"
            rm -f "${response_file}"
            return 0
          fi
          ;;
        api)
          if jq -e '.success == true and has("data")' "${response_file}" >/dev/null 2>&1; then
            printf 'PASS  %-32s HTTP %s  %s\n' "${label}" "${http_code}" "${path}"
            rm -f "${response_file}"
            return 0
          fi
          ;;
      esac
    fi

    [[ "${attempt}" -eq 5 ]] || sleep 5
  done

  printf 'FAIL  %-32s HTTP %s  %s\n' "${label}" "${http_code}" "${path}" >&2
  if [[ -s "${response_file}" ]]; then
    echo "      Response: $(head -c 300 "${response_file}" | tr '\n' ' ')" >&2
  fi
  rm -f "${response_file}"
  return 1
}

echo "Checking public frontend reachability and every backend through the frontend proxy"
failed=0

check_endpoint "Frontend application" "/" html || failed=1
check_endpoint "Frontend health" "/health" health || failed=1

# Container App parking APIs.
check_endpoint "Lisbon API (Container App)" "/api/lisbon/parking" api || failed=1
check_endpoint "Lisbon metrics (Container App)" "/api/lisbon/parking/metrics" api || failed=1
check_endpoint "Lisbon levels (Container App)" "/api/lisbon/parking/levels" api || failed=1
check_endpoint "Berlin API (Container App)" "/api/berlin/parking" api || failed=1
check_endpoint "Berlin metrics (Container App)" "/api/berlin/parking/metrics" api || failed=1
check_endpoint "Berlin levels (Container App)" "/api/berlin/parking/levels" api || failed=1

# Private VM parking APIs. Success proves App Service VNet integration and NSG access.
check_endpoint "Madrid API (Windows VM)" "/api/madrid/parking" api || failed=1
check_endpoint "Madrid metrics (Windows VM)" "/api/madrid/parking/metrics" api || failed=1
check_endpoint "Madrid levels (Windows VM)" "/api/madrid/parking/levels" api || failed=1
check_endpoint "Paris API (Linux VM)" "/api/paris/parking" api || failed=1
check_endpoint "Paris metrics (Linux VM)" "/api/paris/parking/metrics" api || failed=1
check_endpoint "Paris levels (Linux VM)" "/api/paris/parking/levels" api || failed=1
check_endpoint "Paris dependency (Linux VM)" "/api/paris/parking/dependency" api || failed=1

# Supporting Container Apps consumed by the frontend.
check_endpoint "Chaos Control (Container App)" "/api/chaos-control/state" api || failed=1
check_endpoint "VM Health Control (Container App)" "/api/vm-health-control/state" api || failed=1

if [[ "${failed}" -ne 0 ]]; then
  echo "Parking Manager validation failed: the public frontend or one or more backends are not reachable through its proxy." >&2
  exit 1
fi

echo "Parking Manager validation complete: frontend and all proxied backends are reachable."
