#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TERRAFORM_DIR="${TERRAFORM_DIR:-$(cd "${SCRIPT_DIR}/../../infra" && pwd)}"
source "${SCRIPT_DIR}/common.sh"

require_command curl

chaos_control_url="$(tf_output parking_chaos_control_url 2>/dev/null || true)"

if [[ -z "${chaos_control_url}" || "${chaos_control_url}" == "null" ]]; then
  echo "Could not determine parking_chaos_control_url from ${TERRAFORM_DIR}." >&2
  exit 1
fi

curl -m 10 -sfS \
  -X PUT \
  "${chaos_control_url}/api/chaos/state" \
  -H "Content-Type: application/json" \
  -d '{
    "globalEnabled": true,
    "services": {
      "lisbon": {
        "enabled": true,
        "faultType": "latency",
        "probability": 0.8,
        "delayMs": 3000
      }
    }
  }' >/dev/null

echo "Parking Manager Lisbon chaos latency fault enabled."
echo "Restore with: make restore-parking-chaos"
