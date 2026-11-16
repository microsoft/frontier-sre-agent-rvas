#!/usr/bin/env bash
set -euo pipefail

for command_name in az jq; do
  if ! command -v "${command_name}" >/dev/null 2>&1; then
    echo "Missing required command: ${command_name}" >&2
    exit 1
  fi
done

readonly COST_QUERY_BODY='{
  "type": "ActualCost",
  "timeframe": "MonthToDate",
  "dataset": {
    "granularity": "None",
    "aggregation": {
      "totalCost": { "name": "PreTaxCost", "function": "Sum" }
    }
  }
}'

query_cost_management() {
  local subscription_id="$1"

  az rest --method post \
    --url "https://management.azure.com/subscriptions/${subscription_id}/providers/Microsoft.CostManagement/query?api-version=2025-03-01" \
    --headers "Content-Type=application/json" \
    --body "${COST_QUERY_BODY}" \
    --output json
}

main() {
  local subscription_id
  local cost_response=""
  local query_succeeded=false
  local retry_delay

  subscription_id="$(az account show --query id --output tsv)"

  for retry_delay in 0 30 60 120; do
    if (( retry_delay > 0 )); then
      echo "Cost Management throttled the request; retrying in ${retry_delay}s..." >&2
      sleep "${retry_delay}"
    fi

    if cost_response="$(query_cost_management "${subscription_id}" 2>&1)"; then
      jq -r '.properties as $properties | ([$properties.columns[].name], $properties.rows[]) | @tsv' \
        <<<"${cost_response}"
      query_succeeded=true
      break
    fi

    if ! grep -Eq '"code"[[:space:]]*:[[:space:]]*"429"' <<<"${cost_response}"; then
      printf '%s\n' "${cost_response}" >&2
      exit 1
    fi
  done

  if [[ "${query_succeeded}" != true ]]; then
    printf '%s\nCost Management remained throttled after four attempts. Try again later.\n' \
      "${cost_response}" >&2
    exit 1
  fi
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  main "$@"
fi