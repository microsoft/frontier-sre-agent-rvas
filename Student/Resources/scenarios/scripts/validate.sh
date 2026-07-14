#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

hub_rg="$(hub_resource_group_name)"
web_api_rg="$(web_api_resource_group_name)"
data_rg="$(data_resource_group_name)"
storage_account="$(tf_output demo_lab_storage_account_name)"
workspace_id="$(tf_output demo_lab_log_analytics_workspace_id)"
network_watcher_rg="$(tf_output demo_lab_network_watcher_resource_group_name)"
bastion_name="$(tf_output demo_lab_bastion_host_name)"

echo "Hub connectivity RG: ${hub_rg}"
echo "Web-API spoke RG:    ${web_api_rg}"
echo "Data spoke RG:       ${data_rg}"
echo "Storage account: ${storage_account}"
echo "Log Analytics workspace: ${workspace_id}"
echo "Azure Bastion: ${bastion_name}"

printf '\nFlow log resources:\n'
az resource list \
  --resource-group "${network_watcher_rg}" \
  --resource-type Microsoft.Network/networkWatchers/flowLogs \
  --query "[?contains(name, 'vflta')].{name:name, location:location}" \
  --output table || true

printf '\nRaw flow log container check:\n'
az storage container exists \
  --name insights-logs-flowlogflowevent \
  --account-name "${storage_account}" \
  --auth-mode login \
  --query exists \
  --output tsv || true

printf '\nVM private IPs:\n'
tf_output_json demo_lab_vm_private_ips | jq .

printf '\nAzure Bastion check:\n'
az network bastion show \
  --resource-group "${hub_rg}" \
  --name "${bastion_name}" \
  --query "{name:name, sku:sku.name, provisioningState:provisioningState, dnsName:dnsName}" \
  --output table || true

printf '\nVM public IP exposure check:\n'
tf_output_json demo_lab_vm_names | jq -r 'to_entries[] | [.key, .value] | @tsv' | while IFS=$'\t' read -r role vm; do
  public_ips="$(az vm list-ip-addresses --resource-group "$(vm_resource_group "${role}")" --name "${vm}" --query "[].virtualMachine.network.publicIpAddresses[].ipAddress" --output tsv || true)"
  if [[ -n "${public_ips}" ]]; then
    echo "WARN: ${role} (${vm}) has public IP(s): ${public_ips}"
  else
    echo "OK: ${role} (${vm}) has no public IP"
  fi
done

printf '\nBoot diagnostics check:\n'
tf_output_json demo_lab_vm_names | jq -r 'to_entries[] | [.key, .value] | @tsv' | while IFS=$'\t' read -r role vm; do
  enabled="$(az vm show --resource-group "$(vm_resource_group "${role}")" --name "${vm}" --query "diagnosticsProfile.bootDiagnostics.enabled" --output tsv 2>/dev/null || true)"
  if [[ "${enabled}" == "true" ]]; then
    echo "OK: ${role} (${vm}) boot diagnostics enabled"
  else
    echo "WARN: ${role} (${vm}) boot diagnostics not reported as enabled"
  fi
done