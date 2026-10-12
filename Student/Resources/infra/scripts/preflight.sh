#!/usr/bin/env bash
set -uo pipefail

track=operations
local_only=false
failures=0
warnings=0
while (($#)); do
  case "$1" in
    --local) local_only=true ;;
    --track)
      shift
      track="${1:-}"
      ;;
    *) printf 'Unknown option: %s\n' "$1" >&2; exit 2 ;;
  esac
  shift
done
case "$track" in operations|sql-dba) ;; *) echo 'Use --track operations or --track sql-dba.' >&2; exit 2 ;; esac

pass() { printf 'PASS %s\n' "$*"; }
fail() { printf 'FAIL %s\n' "$*" >&2; failures=$((failures + 1)); }
warn() { printf 'WARN %s\n' "$*"; warnings=$((warnings + 1)); }
available() { command -v "$1" >/dev/null 2>&1; }
summary() {
  printf '\nPre-flight: %s failure(s), %s warning(s).\n' "$failures" "$warnings"
  if ((warnings)); then echo 'Review unresolved warnings with your coach before deploying.'; fi
  ((failures == 0))
}

echo "Workshop pre-flight ($track; local-only=$local_only)"
if ((BASH_VERSINFO[0] < 4)); then
  fail 'Bash 4+ is required.'
  summary; exit $?
fi
if [[ "$(uname -s)" != Linux ]]; then
  fail 'Run inside Linux Bash: Codespaces, WSL2/Ubuntu, or a Linux Dev Container; not PowerShell/CMD/Git Bash.'
fi
kernel="$(uname -r)"
if [[ "${kernel,,}" == *microsoft* && "${kernel,,}" != *wsl2* ]]; then
  fail 'WSL1 is not the supported Windows environment. Convert your Ubuntu distribution to WSL2.'
fi
for tool in git make az terraform jq curl envsubst timeout find sed grep sort base64 python3; do
  if available "$tool"; then pass "$tool is available"; else fail "Missing $tool. Follow README Requirements or rebuild the Dev Container."; fi
done
for tool in make timeout find; do
  if available "$tool" && ! "$tool" --version 2>/dev/null | grep -Eq 'GNU|coreutils'; then
    fail "$tool must be the GNU implementation."
  fi
done
if available terraform && available jq; then
  if version="$(terraform version -json 2>/dev/null | jq -er '.terraform_version')"; then
    IFS=. read -r major minor patch <<< "$version"
    if [[ "$major" =~ ^[0-9]+$ && "$minor" =~ ^[0-9]+$ ]] && ((major > 1 || (major == 1 && minor >= 5))); then
      pass "Terraform $version (minimum 1.5)"
    else fail 'Terraform 1.5+ is required.'; fi
  else fail 'Cannot read Terraform version; check the Linux installation.'; fi
fi
if available python3 && python3 -c 'import yaml; assert yaml.safe_load("ready: true") == {"ready": True}' >/dev/null 2>&1; then
  pass 'Python 3 / PyYAML parser works'
elif available yq && [[ "$(printf 'ready: true\n' | yq -o=json '.' - 2>/dev/null)" == *'"ready": true'* ]]; then
  pass 'Compatible yq JSON conversion works'
else
  fail 'Install Python 3 with PyYAML (Ubuntu: python3-yaml) or Mike Farah yq with -o=json support.'
fi
if [[ "$track" == sql-dba ]]; then
  if available sqlcmd; then pass 'sqlcmd is available (verify Entra authentication with your approved database)'; else fail 'Missing sqlcmd. Install the Microsoft SQL client or rebuild the Dev Container.'; fi
  if available az; then
    if available jq && cli_version="$(az version --output json 2>/dev/null | jq -er '."azure-cli"')"; then
      IFS=. read -r cli_major cli_minor cli_patch <<< "$cli_version"
      if [[ "$cli_major" =~ ^[0-9]+$ && "$cli_minor" =~ ^[0-9]+$ ]] && ((cli_major > 2 || (cli_major == 2 && cli_minor >= 62))); then pass "Azure CLI $cli_version"
      else fail 'The DBA deployment guide requires Azure CLI 2.62+.'; fi
    else fail 'Cannot verify Azure CLI version for the DBA track.'; fi
    if az extension show --name containerapp --output none >/dev/null 2>&1; then pass 'Container Apps extension is installed'
    else fail 'Install the Container Apps extension explicitly: az extension add --name containerapp'; fi
  fi
fi
if "$local_only"; then summary; exit $?; fi
if ! available az || ! available jq || ! available python3; then
  warn 'Azure checks skipped because required local tools are missing.'
  summary; exit $?
fi
if ! account="$(az account show --output json 2>/dev/null)"; then
  fail 'Azure login is missing/expired. Run az login (or az login --use-device-code) inside this Linux environment.'
  summary; exit $?
fi
if ! subscription="$(jq -er '.id' <<< "$account")" || ! tenant="$(jq -er '.tenantId' <<< "$account")"; then
  fail 'Azure CLI returned an invalid account response.'; summary; exit $?
fi
printf 'Azure subscription: %s; tenant: %s\n' "$subscription" "$tenant"
if [[ "$(jq -r '.state' <<< "$account")" != Enabled ]]; then fail 'The selected Azure subscription is not Enabled.'; fi
if [[ -n "${ARM_SUBSCRIPTION_ID:-}" && "$ARM_SUBSCRIPTION_ID" != "$subscription" ]]; then
  fail 'ARM_SUBSCRIPTION_ID differs from az account show. Align Terraform and Azure CLI before continuing.'
fi
if [[ -n "${ARM_TENANT_ID:-}" && "$ARM_TENANT_ID" != "$tenant" ]]; then
  fail 'ARM_TENANT_ID differs from az account show. Align Terraform and Azure CLI before continuing.'
fi
warn 'Effective deployment/RBAC permissions and Azure Policy are not certified by this check. Coach must confirm resource creation and role-assignment rights.'

providers=(Microsoft.App Microsoft.Network Microsoft.Compute Microsoft.OperationalInsights Microsoft.Insights Microsoft.Storage Microsoft.Web Microsoft.ManagedIdentity)
if [[ "$track" == sql-dba ]]; then providers=(Microsoft.App Microsoft.Sql Microsoft.ContainerRegistry Microsoft.ManagedIdentity Microsoft.OperationalInsights); fi
for provider in "${providers[@]}"; do
  if state="$(az provider show --namespace "$provider" --query registrationState --output tsv 2>/dev/null)"; then
    if [[ "$state" == Registered ]]; then pass "$provider is registered"
    else fail "$provider is not Registered. Ask the subscription administrator to register it before deployment."; fi
  else warn "Cannot inspect $provider. Ask your coach to verify registration."; fi
done

if [[ "$track" == operations ]]; then
  # Parse Terraform arguments as data, never as shell code. Unknown override sources
  # cannot be certified and must not be checked against the default region/profile.
  if profile="$(python3 - <<'PY'
import glob, json, os, re, shlex
root = os.environ.get("PREFLIGHT_TF_DIR", "")
if root and any(glob.glob(os.path.join(root, pattern)) for pattern in ("terraform.tfvars", "terraform.tfvars.json", "*.auto.tfvars", "*.auto.tfvars.json")):
    raise ValueError("Auto-loaded variable file requires manual profile review")
if os.environ.get("TF_CLI_ARGS") or os.environ.get("TF_CLI_ARGS_apply"):
    raise ValueError("Additional CLI arguments require manual profile review")
values = {"location": os.environ.get("TF_VAR_location", "swedencentral"),
          "deploy_madrid_vm": os.environ.get("TF_VAR_deploy_madrid_vm", "true"),
          "deploy_paris_vm": os.environ.get("TF_VAR_deploy_paris_vm", "true")}
args = iter(shlex.split(os.environ.get("TF_VARS", "")))
for arg in args:
    if arg == "-var":
        value = next(args)
    elif arg.startswith("-var="):
        value = arg[5:]
    else:
        raise ValueError("Unrecognized override source")
    key, value = value.split("=", 1)
    if key in values:
        values[key] = value.strip('"')
if any(values[k] not in ("true", "false") for k in ("deploy_madrid_vm", "deploy_paris_vm")):
    raise ValueError("Invalid VM flag")
if not re.fullmatch(r"[a-z0-9]+", values["location"]):
    raise ValueError("Invalid region")
print(json.dumps({"location": values["location"],
                  "vcpus": 12 + 2 * (values["deploy_madrid_vm"] == "true") + 2 * (values["deploy_paris_vm"] == "true")}))
PY
  )" 2>/dev/null; then
    location="$(jq -r '.location' <<< "$profile")"
    required="$(jq -r '.vcpus' <<< "$profile")"
    printf 'Workload region: %s; new-lab vCPU requirement: %s\n' "$location" "$required"
    if watcher="$(az network watcher list --output json 2>/dev/null)"; then
      if jq -e --arg name "NetworkWatcher_$location" --arg region "$location" \
        'any(.[]; .name == $name and .location == $region and (.resourceGroup | ascii_downcase) == "networkwatcherrg")' <<< "$watcher" >/dev/null; then pass 'Regional Network Watcher exists in NetworkWatcherRG'
      else fail "Missing NetworkWatcher_$location. Coach/admin must enable Network Watcher in NetworkWatcherRG."; fi
    else warn 'Cannot inspect Network Watcher; coach must verify its regional name and resource group.'; fi
    existing=false
    if [[ -n "${PREFLIGHT_TF_DIR:-}" ]] && available terraform; then
      if state="$(terraform -chdir="$PREFLIGHT_TF_DIR" state list 2>/dev/null)" && [[ -n "$state" ]]; then existing=true; fi
    fi
    printf 'Checking vCPU availability in region %s...\n' "$location"
    if skus="$(az vm list-skus --location "$location" --resource-type virtualMachines --size Standard_B2s_v2 --all --output json 2>/dev/null)" &&
       family="$(jq -er '[.[] | select(.name=="Standard_B2s_v2")][0].family' <<< "$skus")" &&
       usage="$(az vm list-usage --location "$location" --output json 2>/dev/null)"; then
      if jq -e '[.[] | select(.name=="Standard_B2s_v2") | .restrictions[]? | select(.type=="Location")] | length > 0' <<< "$skus" >/dev/null; then
        warn 'Standard_B2s_v2 has a regional restriction; coach must confirm deployability for this subscription.'
      fi
      for quota in cores "$family"; do
        if remaining="$(jq -er --arg quota "$quota" '[.[] | select((.name.value | ascii_downcase)==($quota | ascii_downcase))][0] | (.limit | tonumber) - (.currentValue | tonumber)' <<< "$usage")" && [[ "$remaining" =~ ^-?[0-9]+$ ]]; then
          if ((remaining >= required)); then pass "$quota: $remaining vCPUs available"
          elif "$existing"; then warn "$quota: $remaining vCPUs free; existing state detected. Coach must verify capacity for only the planned additions."
          else fail "$quota: $remaining vCPUs free; a new lab needs $required. Request quota or choose an approved region."; fi
        else warn "Cannot resolve $quota quota; coach must verify available vCPUs."; fi
      done
    else warn 'Cannot verify VM SKU/family quota. Coach must check Standard_B2s_v2 availability and regional/family capacity.'; fi
  else warn 'Cannot safely resolve TF_VARS (for example -var-file). Regional checks skipped; coach must verify the actual Terraform region/profile.'; fi
else
  warn 'SQL administrator, Entra user mapping, MCP caller role, DNS/TLS and database connectivity require the DBA track validation; no database login is attempted.'
fi
summary
