#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

rg="$(data_resource_group_name)"
data_nsg="$(vm_name data_nsg)"
client="$(vm_ip client)"
db="$(vm_ip db)"

az network nsg rule create \
  --resource-group "${rg}" \
  --nsg-name "${data_nsg}" \
  --name Demo-Deny-App-To-Db-5432 \
  --priority 102 \
  --direction Inbound \
  --access Deny \
  --protocol Tcp \
  --source-address-prefixes 10.20.0.0/16 \
  --source-port-ranges '*' \
  --destination-address-prefixes 10.30.2.10 \
  --destination-port-ranges 5432 \
  --output none

run_on_client "
for i in \$(seq 1 25); do
  timeout 2 bash -c '</dev/tcp/${db}/5432' || true
done
echo denied-db-traffic-generated-from-${client}-to-${db}
"

cat <<EOF
NSG deny rule created and denied traffic generated.
Expected evidence after Traffic Analytics ingestion:
- NTANetAnalytics FlowStatus == "Denied" (full word; the field is not the single letter "D")
- AclRule contains Demo-Deny-App-To-Db-5432
- SrcIp around ${client} and DestIp ${db} / DestPort 5432
Restore with: make restore-nsg-block
EOF