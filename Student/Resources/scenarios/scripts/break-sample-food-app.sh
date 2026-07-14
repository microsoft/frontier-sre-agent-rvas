#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require_command curl

api_url="${1:-}"
request_count="${2:-200}"
sleep_interval="${3:-0.2}"

if [[ -z "${api_url}" ]]; then
  api_url="$(tf_output sample_food_api_url 2>/dev/null || true)"
fi

if [[ -z "${api_url}" || "${api_url}" == "null" ]]; then
  echo "Could not determine Sample Food Ordering API URL. Usage: $0 [api-url] [request-count] [sleep-seconds]" >&2
  exit 1
fi

echo "Triggering controlled Sample Food Ordering App cart load"
echo "Target:   ${api_url}"
echo "Requests: ${request_count}"

weather_code="$(curl -s -o /dev/null -w "%{http_code}" "${api_url}/WeatherForecast" || echo "000")"
echo "Initial WeatherForecast API: HTTP ${weather_code}"

success_count=0
error_count=0
for request_number in $(seq 1 "${request_count}"); do
  http_code="$(curl -s -o /dev/null -w "%{http_code}" \
    -X POST "${api_url}/api/cart/demo-user/items" \
    -H "Content-Type: application/json" \
    -d '{"foodItemId":1,"quantity":1}' || echo "000")"

  if [[ "${http_code}" == "200" || "${http_code}" == "201" ]]; then
    success_count=$((success_count + 1))
  else
    error_count=$((error_count + 1))
  fi

  if [[ $((request_number % 25)) -eq 0 ]]; then
    echo "Sent ${request_number}/${request_count} requests (${success_count} ok, ${error_count} errors)"
  fi

  if [[ "${sleep_interval}" != "0" ]]; then
    sleep "${sleep_interval}"
  fi
done

final_weather_code="$(curl -s -o /dev/null -w "%{http_code}" "${api_url}/WeatherForecast" || echo "000")"
food_items_code="$(curl -s -o /dev/null -w "%{http_code}" "${api_url}/api/FoodItems" || echo "000")"

echo "Results: ${success_count} successes, ${error_count} errors"
echo "Final WeatherForecast API: HTTP ${final_weather_code}"
echo "FoodItems API:             HTTP ${food_items_code}"
echo "Check ContainerAppHTTPLogs and Application Insights for impact evidence."