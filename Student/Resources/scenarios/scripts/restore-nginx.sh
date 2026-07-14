#!/usr/bin/env bash
set -euo pipefail

# Restore for the NGINX Service Down scenario.
# Starts the nginx service on BOTH web-tier VMs (web_1 and web_2) and confirms each
# is active, so the internal Load Balancer HTTP health probes pass again and the LB
# frontend (10.20.2.100) resumes serving. Use this in interactive/manual mode, or
# to reset the lab after the SRE Agent has remediated.

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

rg="$(web_api_resource_group_name)"
web1_vm="$(tf_output_json demo_lab_vm_names | jq -r '.web_1')"
web2_vm="$(tf_output_json demo_lab_vm_names | jq -r '.web_2')"
web1_ip="$(vm_ip web_1)"
web2_ip="$(vm_ip web_2)"
lb_ip="$(vm_ip ilb)"

echo "Starting nginx on ${web1_vm} ..."
az vm run-command invoke \
  --resource-group "${rg}" \
  --name "${web1_vm}" \
  --command-id RunShellScript \
  --scripts "systemctl start nginx; systemctl is-active nginx" \
  --query "value[0].message" \
  --output tsv

echo "Starting nginx on ${web2_vm} ..."
az vm run-command invoke \
  --resource-group "${rg}" \
  --name "${web2_vm}" \
  --command-id RunShellScript \
  --scripts "systemctl start nginx; systemctl is-active nginx" \
  --query "value[0].message" \
  --output tsv

echo "Post-restore check from the client VM (expect HTTP 200 on the LB and both web VMs) ..."
run_on_client "curl -sS -m 5 -o /dev/null -w 'LB    ${lb_ip}:80 -> HTTP %{http_code}\n' http://${lb_ip}/ || echo 'LB request failed'
curl -sS -m 5 -o /dev/null -w 'web_1 ${web1_ip}:80 -> HTTP %{http_code}\n' http://${web1_ip}/ || echo 'web_1 request failed'
curl -sS -m 5 -o /dev/null -w 'web_2 ${web2_ip}:80 -> HTTP %{http_code}\n' http://${web2_ip}/ || echo 'web_2 request failed'"

echo "nginx restore complete on ${web1_vm} and ${web2_vm}."
