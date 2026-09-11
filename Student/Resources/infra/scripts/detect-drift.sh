#!/usr/bin/env bash
set -euo pipefail

infra_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

canonicalize_import_id() {
  local terraform_type="$1"
  local resource_id="$2"

  # ARM treats resource IDs case-insensitively, but some AzureRM import parsers
  # require exact casing for literal path segments.
  resource_id="$(sed -E \
    -e 's#/resourcegroups/#/resourceGroups/#I' \
    -e 's#/providers/#/providers/#I' \
    <<<"${resource_id}")"

  case "${terraform_type}" in
    azurerm_monitor_metric_alert)
      resource_id="$(sed -E \
        -e 's#/providers/microsoft\.insights/#/providers/Microsoft.Insights/#I' \
        -e 's#/metricalerts/#/metricAlerts/#I' \
        <<<"${resource_id}")"
      ;;
  esac

  printf '%s\n' "${resource_id}"
}

for command in az jq terraform; do
  if ! command -v "${command}" >/dev/null 2>&1; then
    echo "Required command not found: ${command}" >&2
    exit 1
  fi
done

if ! az account show --output none 2>/dev/null; then
  echo "Azure CLI is not authenticated. Run 'az login' and select the deployment subscription first." >&2
  exit 1
fi

subscription_id="$(az account show --query id --output tsv)"
tmp_dir="$(mktemp -d)"
trap 'rm -rf "${tmp_dir}"' EXIT

state_json="${tmp_dir}/state.json"
state_inventory="${tmp_dir}/state.tsv"
azure_inventory="${tmp_dir}/azure.txt"
azure_id_map="${tmp_dir}/azure-ids.tsv"
state_ids="${tmp_dir}/state-ids.txt"
resource_groups="${tmp_dir}/resource-groups.txt"
planned_imports="${tmp_dir}/planned-imports.tsv"

terraform -chdir="${infra_dir}" state pull >"${state_json}"

# A refresh-free plan exposes the Terraform addresses and configured names of
# resources Terraform intends to create, without modifying state or Azure.
plan_file="${tmp_dir}/drift.tfplan"
plan_log="${tmp_dir}/plan.log"
if terraform -chdir="${infra_dir}" plan \
  -refresh=false \
  -input=false \
  -lock=false \
  -out="${plan_file}" \
  "$@" >"${plan_log}" 2>&1; then
  terraform -chdir="${infra_dir}" show -json "${plan_file}" \
    | jq -r '
        .resource_changes[]?
        | select(.mode == "managed")
        | select(.change.actions == ["create"] or .change.actions == ["delete", "create"])
        | select(.change.after.name? | type == "string")
        | select(.change.after.resource_group_name? | type == "string")
        | [
            (.change.after.resource_group_name | ascii_downcase),
            (.change.after.name | ascii_downcase),
            .address,
            .type
          ]
        | @tsv
      ' | sort -u >"${planned_imports}"
else
  : >"${planned_imports}"
  echo "Warning: Terraform could not produce a refresh-free plan, so automatic import commands may be incomplete." >&2
  tail -n 12 "${plan_log}" >&2
  echo >&2
fi

# Build a normalized ARM-ID-to-Terraform-address inventory from local state.
jq -r '
  .resources[]
  | select(.mode == "managed")
  | . as $resource
  | .instances[]?
  | select(.attributes.id? | type == "string" and startswith("/subscriptions/"))
  | [
      (.attributes.id | ascii_downcase | sub("/+$"; "")),
      (if $resource.module then $resource.module + "." else "" end)
        + $resource.type + "." + $resource.name
        + (if .index_key == null then "" elif (.index_key | type) == "number" then "[" + (.index_key | tostring) + "]" else "[\"" + (.index_key | tostring) + "\"]" end)
    ]
  | @tsv
' "${state_json}" | sort -u >"${state_inventory}"
cut -f1 "${state_inventory}" | sort -u >"${state_ids}"

# Resource groups already known to state define the workshop deployment boundary.
# Also extract RG names from every tracked ARM ID so partially tracked groups are included.
{
  jq -r '.resources[] | select(.mode == "managed" and .type == "azurerm_resource_group") | .instances[]?.attributes.name // empty' "${state_json}"
  cut -f1 "${state_inventory}" | sed -nE 's#^/subscriptions/[^/]+/resourcegroups/([^/]+)(/.*)?$#\1#p'
} | awk 'NF { print tolower($0) }' | sort -u >"${resource_groups}"

if [[ ! -s "${resource_groups}" ]]; then
  echo "No Azure resource groups were found in local Terraform state; there is no deployment boundary to compare." >&2
  exit 1
fi

: >"${azure_id_map}"
while IFS= read -r resource_group; do
  if ! group_id="$(az group show --name "${resource_group}" --query id --output tsv 2>/dev/null)"; then
    echo "Warning: resource group in state does not exist in Azure: ${resource_group}" >&2
    continue
  fi

  printf '%s\t%s\n' "${group_id,,}" "${group_id}" >>"${azure_id_map}"
  while IFS= read -r azure_id; do
    [[ -n "${azure_id}" ]] || continue
    printf '%s\t%s\n' "${azure_id,,}" "${azure_id}" >>"${azure_id_map}"
  done < <(az resource list --resource-group "${resource_group}" --query '[].id' --output tsv)
done <"${resource_groups}"
sort -t $'\t' -k1,1 -u -o "${azure_id_map}" "${azure_id_map}"
cut -f1 "${azure_id_map}" >"${azure_inventory}"

missing_from_state="${tmp_dir}/missing-from-state.txt"
missing_from_azure="${tmp_dir}/missing-from-azure.txt"
comm -23 "${azure_inventory}" "${state_ids}" >"${missing_from_state}"
comm -13 "${azure_inventory}" "${state_ids}" >"${missing_from_azure}"

printf 'Subscription: %s\n' "${subscription_id}"
printf 'Resource groups checked: %s\n' "$(wc -l <"${resource_groups}" | tr -d ' ')"
printf 'Azure resources found: %s\n' "$(wc -l <"${azure_inventory}" | tr -d ' ')"
printf 'Terraform-managed ARM resources: %s\n\n' "$(wc -l <"${state_ids}" | tr -d ' ')"

if [[ -s "${missing_from_state}" ]]; then
  echo "DEPLOYED IN AZURE BUT MISSING FROM TERRAFORM STATE"
  echo "These resources are candidates for terraform import; verify ownership before importing:"
  sed 's/^/  /' "${missing_from_state}"
  echo

  echo "SUGGESTED IMPORT COMMANDS"
  echo "Run these commands from the Student directory only after verifying each resource belongs to this deployment:"
  generated_imports=0
  unresolved_imports=0
  while IFS= read -r id; do
    canonical_id="$(awk -F '\t' -v wanted="${id}" '$1 == wanted { print $2; exit }' "${azure_id_map}")"
    resource_group="$(sed -nE 's#^/subscriptions/[^/]+/resourcegroups/([^/]+)/.*$#\1#p' <<<"${id}")"
    resource_name="${id##*/}"
    matches="$(awk -F '\t' -v rg="${resource_group}" -v name="${resource_name}" '$1 == rg && $2 == name { print $3 }' "${planned_imports}" | sort -u)"
    match_count="$(grep -c . <<<"${matches}" || true)"

    if [[ "${match_count}" -eq 1 ]]; then
      terraform_type="$(awk -F '\t' -v rg="${resource_group}" -v name="${resource_name}" -v address="${matches}" '$1 == rg && $2 == name && $3 == address { print $4; exit }' "${planned_imports}")"
      canonical_id="$(canonicalize_import_id "${terraform_type}" "${canonical_id}")"
      printf "  terraform -chdir=\"Resources/infra\" import '%s' '%s'\n" "${matches}" "${canonical_id}"
      generated_imports=$((generated_imports + 1))
    else
      printf '  # No unique Terraform address found for %s\n' "${id}"
      unresolved_imports=$((unresolved_imports + 1))
    fi
  done <"${missing_from_state}"
  echo
  printf 'Generated %d import command(s); %d resource(s) require manual address resolution.\n\n' "${generated_imports}" "${unresolved_imports}"
else
  echo "No deployed resources are missing from local Terraform state."
  echo
fi

if [[ -s "${missing_from_azure}" ]]; then
  echo "TRACKED IN TERRAFORM STATE BUT NOT RETURNED BY AZURE INVENTORY"
  echo "These may have been deleted, may be child resources omitted by generic Azure inventory, or may require a state refresh:"
  while IFS= read -r id; do
    address="$(awk -F '\t' -v wanted="${id}" '$1 == wanted { print $2; exit }' "${state_inventory}")"
    printf '  %s\n    %s\n' "${address}" "${id}"
  done <"${missing_from_azure}"
  echo
else
  echo "No Terraform-tracked ARM resources are absent from Azure inventory."
  echo
fi

if [[ -s "${missing_from_state}" || -s "${missing_from_azure}" ]]; then
  echo "Inventory drift detected. This command is read-only and did not modify Terraform state or Azure."
  exit 2
fi

echo "No inventory drift detected."
