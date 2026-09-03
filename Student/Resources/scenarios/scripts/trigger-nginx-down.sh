#!/usr/bin/env bash
set -euo pipefail

# Demo scenario: NGINX Service Down (Load-Balancer-visible outage).
# The two web VMs (web_1 and web_2) sit behind one internal Standard Load Balancer
# (frontend 10.20.2.100). Stopping nginx on a single VM is NOT a real outage: the
# LB keeps serving from the other healthy backend. To make the outage impactful we
# stop nginx on BOTH web VMs, so every HTTP health probe fails and the LB sends no
# new flows to the backend pool. Azure Monitor Agent ships the systemd
# "Stopped nginx" events into the Syslog table, the scheduled query alert
# "alert-nginx-down" (Sev2) fires, and the SRE Agent iaas-vm-incident-handler
# subagent investigates and restarts nginx on both VMs autonomously.
# Restore manually with: make restore-nginx
#
# LB probe-down behavior (certified):
# https://learn.microsoft.com/en-us/azure/load-balancer/load-balancer-custom-probe-overview#probe-down-behavior

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

rg="$(web_api_resource_group_name)"
web1_vm="$(tf_output_json demo_lab_vm_names | jq -r '.web_1')"
web2_vm="$(tf_output_json demo_lab_vm_names | jq -r '.web_2')"
web1_ip="$(vm_ip web_1)"
web2_ip="$(vm_ip web_2)"
lb_ip="$(vm_ip ilb)"

echo "Baseline check from the client VM (expect HTTP 200 on the LB and both web VMs) ..."
run_on_client "curl -sS -m 5 -o /dev/null -w 'baseline LB    ${lb_ip}:80 -> HTTP %{http_code}\n' http://${lb_ip}/ || echo 'baseline LB request failed'
curl -sS -m 5 -o /dev/null -w 'baseline web_1 ${web1_ip}:80 -> HTTP %{http_code}\n' http://${web1_ip}/ || echo 'baseline web_1 request failed'
curl -sS -m 5 -o /dev/null -w 'baseline web_2 ${web2_ip}:80 -> HTTP %{http_code}\n' http://${web2_ip}/ || echo 'baseline web_2 request failed'"

echo "Stopping nginx on ${web1_vm} ..."
az vm run-command invoke \
  --resource-group "${rg}" \
  --name "${web1_vm}" \
  --command-id RunShellScript \
  --scripts "systemctl stop nginx; systemctl is-active nginx || true" \
  --query "value[0].message" \
  --output tsv

echo "Stopping nginx on ${web2_vm} ..."
az vm run-command invoke \
  --resource-group "${rg}" \
  --name "${web2_vm}" \
  --command-id RunShellScript \
  --scripts "systemctl stop nginx; systemctl is-active nginx || true" \
  --query "value[0].message" \
  --output tsv

cat <<EOF

NGINX stopped on BOTH ${web1_vm} and ${web2_vm}.
Both backends now fail the Load Balancer HTTP health probe (port 80, path '/'),
so the internal LB frontend ${lb_ip} stops serving new connections
('all instances probe down -> no new flows are sent to the backend pool').
Expected detection and remediation path:
- AMA collects the systemd 'Stopped nginx' events from both web VMs into Syslog (LAW).
- Scheduled query alert 'alert-nginx-down' (Sev2) fires (PT1M evaluation).
- The alert is routed to the SRE Agent iaas-vm-incident-handler subagent (Autonomous),
  which must restart nginx on BOTH web VMs via Run Command and verify recovery.
Watch ingestion with KQL:
  Syslog
  | where TimeGenerated > ago(15m)
  | where SyslogMessage has "nginx"
  | order by TimeGenerated desc
Manual restore (if needed): make restore-nginx
EOF
