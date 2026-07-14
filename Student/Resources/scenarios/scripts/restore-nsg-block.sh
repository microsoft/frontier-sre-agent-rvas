#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

az network nsg rule delete \
  --resource-group "$(data_resource_group_name)" \
  --nsg-name "$(vm_name data_nsg)" \
  --name Demo-Deny-App-To-Db-5432 \
  --output none || true

echo "NSG deny scenario restored."