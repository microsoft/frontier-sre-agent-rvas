#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

web_1="$(vm_ip web_1)"
web_2="$(vm_ip web_2)"
api="$(vm_ip api)"
db="$(vm_ip db)"
ilb="$(vm_ip ilb)"

run_on_client "
set -e
i=1
while [ \"\$i\" -le 30 ]; do
  curl -m 3 -s http://${web_1}/ >/dev/null || true
  curl -m 3 -s http://${web_2}/ >/dev/null || true
  curl -m 3 -s http://${ilb}/ >/dev/null || true
  curl -m 3 -s http://${api}:8080/ >/dev/null || true
  timeout 2 bash -c '</dev/tcp/${db}/5432' || true
  curl -m 3 -s https://www.microsoft.com/ >/dev/null || true
  i=\$((i + 1))
done
echo baseline-traffic-generated
"

cat <<EOF
Baseline traffic generated.
Traffic Analytics processes data every configured interval, typically 10 or 60 minutes.
Use docs/demo-lab/kql-catalog.md after ingestion to show top talkers and flow types.
EOF