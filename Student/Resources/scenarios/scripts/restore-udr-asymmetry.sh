#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

az network route-table route delete \
  --resource-group "$(data_resource_group_name)" \
  --route-table-name "$(vm_name data_route_table)" \
  --name Demo-Break-Return-To-App-Client \
  --output none || true

echo "UDR asymmetry scenario restored. Terraform-managed centralized routes remain in place."