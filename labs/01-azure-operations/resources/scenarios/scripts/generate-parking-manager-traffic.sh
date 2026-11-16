#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require_command curl

frontend_url="${1:-}"
iterations="${2:-20}"

if [[ -z "${frontend_url}" ]]; then
  frontend_url="$(tf_output parking_frontend_url 2>/dev/null || true)"
fi

if [[ -z "${frontend_url}" || "${frontend_url}" == "null" ]]; then
  echo "Could not determine the Parking Manager frontend URL. Usage: $0 [frontend-url] [iterations]" >&2
  exit 1
fi

frontend_url="${frontend_url%/}"

echo "Generating Parking Manager traffic through ${frontend_url}"

for iteration in $(seq 1 "${iterations}"); do
  curl -m 10 -s -o /dev/null "${frontend_url}/" || true

  for city in lisbon madrid paris berlin; do
    curl -m 10 -s -o /dev/null "${frontend_url}/api/${city}/parking" || true
    curl -m 10 -s -o /dev/null "${frontend_url}/api/${city}/parking/metrics" || true
    curl -m 10 -s -o /dev/null "${frontend_url}/api/${city}/parking/levels" || true
  done

  curl -m 10 -s -o /dev/null "${frontend_url}/api/chaos-control/state" || true
  curl -m 10 -s -o /dev/null "${frontend_url}/api/vm-health-control/state" || true
  echo "Generated iteration ${iteration}/${iterations}"
done
