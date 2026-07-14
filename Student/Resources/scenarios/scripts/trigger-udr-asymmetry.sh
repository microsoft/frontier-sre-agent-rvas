#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

rg="$(data_resource_group_name)"
route_table="$(vm_name data_route_table)"
firewall_ip="$(vm_ip firewall)"
db_ip="$(vm_ip db)"

az network route-table route create \
  --resource-group "${rg}" \
  --route-table-name "${route_table}" \
  --name Demo-Break-Return-To-App-Client \
  --address-prefix 10.20.1.0/24 \
  --next-hop-type None \
  --output none || \
az network route-table route update \
  --resource-group "${rg}" \
  --route-table-name "${route_table}" \
  --name Demo-Break-Return-To-App-Client \
  --address-prefix 10.20.1.0/24 \
  --next-hop-type None \
  --output none

run_on_client "
i=1
while [ \"\$i\" -le 20 ]; do
  timeout 2 bash -c '</dev/tcp/${db_ip}/5432' || true
  i=\$((i + 1))
done
echo udr-asymmetry-traffic-generated-baseline-next-hop-${firewall_ip}
"

cat <<EOF
UDR asymmetry scenario activated.
Expected demo path:
1. Baseline Next Hop from client VM to ${db_ip} should still show VirtualAppliance / ${firewall_ip}.
2. Effective routes on data subnets now contain a more specific 10.20.1.0/24 route to None.
3. Use Traffic Analytics to inspect FlowDirection, BytesSrcToDest/BytesDestToSrc, and missing or imbalanced return flow.
Restore with: ./Infra/scripts/restore-udr-asymmetry.sh
EOF