#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require_command curl

api_url="${1:-}"
iterations="${2:-20}"

if [[ -z "${api_url}" ]]; then
  api_url="$(tf_output sample_food_api_url 2>/dev/null || true)"
fi

if [[ -z "${api_url}" || "${api_url}" == "null" ]]; then
  echo "Could not determine Sample Food Ordering API URL. Usage: $0 [api-url] [iterations]" >&2
  exit 1
fi

echo "Generating Sample Food Ordering App HTTP traffic against ${api_url}"
echo "Note: Azure Container Apps workload traffic is not supported by VNet Flow Logs; use Container Apps logs and App Insights for this traffic."

for iteration in $(seq 1 "${iterations}"); do
  curl -m 10 -s -o /dev/null "${api_url}/WeatherForecast" || true
  curl -m 10 -s -o /dev/null "${api_url}/api/FoodItems" || true
  curl -m 10 -s -o /dev/null "${api_url}/api/Restaurants" || true
  echo "Generated iteration ${iteration}/${iterations}"
done