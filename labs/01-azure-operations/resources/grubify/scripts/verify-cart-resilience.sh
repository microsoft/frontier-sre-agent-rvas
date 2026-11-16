#!/usr/bin/env bash
set -euo pipefail

API_URL="${1:-}"
REQUEST_COUNT="${2:-200}"
SLEEP_INTERVAL="${3:-0.05}"
TEST_USER="resilience-${GITHUB_RUN_ID:-manual}-${GITHUB_RUN_ATTEMPT:-1}"

if [[ -z "${API_URL}" ]]; then
  echo "Usage: $0 <api-url> [request-count] [sleep-seconds]" >&2
  exit 1
fi

if [[ ! "${REQUEST_COUNT}" =~ ^[1-9][0-9]*$ ]]; then
  echo "Request count must be a positive integer: ${REQUEST_COUNT}" >&2
  exit 1
fi

if ! command -v curl >/dev/null 2>&1; then
  echo "Missing required command: curl" >&2
  exit 1
fi

API_URL="${API_URL%/}"
success_count=0
error_count=0

check_endpoint() {
  local path="$1"
  local expected_code="$2"
  local actual_code

  actual_code="$(curl --max-time 10 --silent --output /dev/null --write-out '%{http_code}' "${API_URL}${path}" || true)"
  if [[ "${actual_code}" != "${expected_code}" ]]; then
    echo "Endpoint ${path} returned HTTP ${actual_code:-000}; expected ${expected_code}." >&2
    return 1
  fi

  echo "Endpoint ${path}: HTTP ${actual_code}"
}

check_endpoint "/WeatherForecast" "200"
check_endpoint "/api/FoodItems" "200"
check_endpoint "/api/Restaurants" "200"

echo "Running ${REQUEST_COUNT} cart writes against ${API_URL}"
for request_number in $(seq 1 "${REQUEST_COUNT}"); do
  http_code="$(curl --max-time 10 --silent --output /dev/null --write-out '%{http_code}' \
    --request POST "${API_URL}/api/cart/${TEST_USER}/items" \
    --header "Content-Type: application/json" \
    --data '{"foodItemId":1,"quantity":1}' || true)"

  if [[ "${http_code}" == "200" || "${http_code}" == "201" ]]; then
    success_count=$((success_count + 1))
  else
    error_count=$((error_count + 1))
    echo "Cart request ${request_number} returned HTTP ${http_code:-000}." >&2
  fi

  if [[ $((request_number % 25)) -eq 0 ]]; then
    echo "Sent ${request_number}/${REQUEST_COUNT} requests (${success_count} successful, ${error_count} failed)"
  fi

  if [[ "${SLEEP_INTERVAL}" != "0" ]]; then
    sleep "${SLEEP_INTERVAL}"
  fi
done

check_endpoint "/WeatherForecast" "200"
check_endpoint "/api/FoodItems" "200"
check_endpoint "/api/Restaurants" "200"

curl --max-time 10 --silent --output /dev/null \
  --request DELETE "${API_URL}/api/cart/${TEST_USER}" || true

if [[ "${error_count}" -ne 0 ]]; then
  echo "Cart resilience validation failed: ${error_count}/${REQUEST_COUNT} requests failed." >&2
  exit 1
fi

echo "Cart resilience validation passed: ${success_count}/${REQUEST_COUNT} writes succeeded and the API remained healthy."
