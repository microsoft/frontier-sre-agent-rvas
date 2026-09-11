#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

echo "web_api_resource_group_name=$(web_api_resource_group_name)"
echo "web1_vm=$(tf_output_json demo_lab_vm_names | jq -r '.web_1')"
echo "web2_vm=$(tf_output_json demo_lab_vm_names | jq -r '.web_2')"
echo "web1_ip=$(vm_ip web_1)"
echo "web2_ip=$(vm_ip web_2)"
echo "lb_ip=$(vm_ip ilb)"
echo "client_vm=$(vm_name client_vm)"
echo "data_resource_group_name=$(data_resource_group_name)"
echo "data_nsg=$(vm_name data_nsg)"
echo "client_ip=$(vm_ip client)"
echo "db_ip=$(vm_ip db)"
