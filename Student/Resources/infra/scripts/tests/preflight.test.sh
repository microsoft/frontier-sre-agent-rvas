#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../../.." && pwd)"
script="$root/Student/Resources/infra/scripts/preflight.sh"
temp="$(mktemp -d)"
trap 'rm -rf "$temp"' EXIT
mkdir "$temp/bin"
for tool in bash git make jq curl timeout find sed grep sort base64 uname ln rm cat mkdir touch chmod; do
  ln -s "$(command -v "$tool")" "$temp/bin/$tool"
done
real_python="$(command -v python3)"
real_jq="$(command -v jq)"
export REAL_PYTHON="$real_python"
cat > "$temp/bin/mock" <<'MOCK'
#!/usr/bin/env bash
set -eu
name="${0##*/}"
printf '%s %s\n' "$name" "$*" >> "$MOCK_LOG"
case "$name" in
  python3)
    if [[ "${1:-}" == -c ]]; then
      [[ "${MOCK_CASE:-}" != parser && "${MOCK_CASE:-}" != wrongparser ]]
    else "$REAL_PYTHON" "$@"; fi ;;
  envsubst) cat ;;
  sqlcmd) echo 'Microsoft SQL client test fixture' ;;
  yq) [[ "${MOCK_CASE:-}" != wrongparser ]] || exit 2; echo '{"ready": true}' ;;
  uname)
    if [[ "${1:-}" == -r && "${MOCK_CASE:-}" == wsl1 ]]; then echo '4.4.0-Microsoft'
    elif [[ "${MOCK_CASE:-}" == windows ]]; then echo MINGW64_NT
    else echo Linux; fi ;;
  terraform)
    if [[ "$*" == *"version -json"* ]]; then
      if [[ "${MOCK_CASE:-}" == oldterraform ]]; then echo '{"terraform_version":"1.4.9"}'
      else echo '{"terraform_version":"1.5.0"}'; fi
    elif [[ "$*" == *"state list"* ]]; then
      [[ "${MOCK_CASE:-}" != existing ]] || echo 'module.workload.azurerm_linux_virtual_machine.client'
    elif [[ "$*" == *"output -raw"* ]]; then
      exit 0
    else echo terraform-operation >> "$MOCK_LOG"; fi ;;
  az)
    case "$*" in
      "version "*) if [[ "${MOCK_CASE:-}" == oldcli ]]; then echo '{"azure-cli":"2.61.0"}'; else echo '{"azure-cli":"2.62.0"}'; fi ;;
      "extension show "*) [[ "${MOCK_CASE:-}" != extension ]] ;;
      "account show "*)
        [[ "${MOCK_CASE:-}" != login ]] || exit 1
        state=Enabled
        [[ "${MOCK_CASE:-}" != disabled ]] || state=Disabled
        printf '{"id":"test-sub","tenantId":"test-tenant","state":"%s"}\n' "$state" ;;
      "provider show "*)
        [[ "${MOCK_CASE:-}" != denied ]] || exit 1
        if [[ "${MOCK_CASE:-}" == provider ]]; then echo NotRegistered; else echo Registered; fi ;;
      "network watcher list "*)
        [[ "${MOCK_CASE:-}" != denied ]] || exit 1
        if [[ "${MOCK_CASE:-}" == watcher ]]; then echo '[]'
        elif [[ "${MOCK_CASE:-}" == wrongwatcherrg ]]; then echo '[{"name":"NetworkWatcher_swedencentral","location":"swedencentral","resourceGroup":"other"}]'
        else printf '[{"name":"NetworkWatcher_%s","location":"%s","resourceGroup":"NetworkWatcherRG"}]\n' "${MOCK_REGION:-swedencentral}" "${MOCK_REGION:-swedencentral}"; fi ;;
      "vm list-skus "*)
        [[ "${MOCK_CASE:-}" != denied ]] || exit 1
        echo '[{"name":"Standard_B2s_v2","family":"standardBSv2Family","restrictions":[]}]' ;;
      "vm list-usage "*)
        limit="${MOCK_LIMIT:-32}"
        [[ "${MOCK_CASE:-}" != quota && "${MOCK_CASE:-}" != existing ]] || limit=8
        if [[ "${MOCK_CASE:-}" == stringquota ]]; then
          printf '[{"name":{"value":"cores"},"limit":"%s","currentValue":"0"},{"name":{"value":"standardBSv2Family"},"limit":"%s","currentValue":"0"}]\n' "$limit" "$limit"
        else
          printf '[{"name":{"value":"cores"},"limit":%s,"currentValue":0},{"name":{"value":"standardBSv2Family"},"limit":%s,"currentValue":0}]\n' "$limit" "$limit"
        fi ;;
      *) echo "Unexpected or mutating Azure command: $*" >&2; exit 99 ;;
    esac ;;
esac
MOCK
chmod +x "$temp/bin/mock"
for tool in az terraform python3 envsubst sqlcmd; do ln -s mock "$temp/bin/$tool"; done
rm "$temp/bin/uname"
ln -s mock "$temp/bin/uname"
export MOCK_LOG="$temp/log"
export PREFLIGHT_TF_DIR="$temp/state"
mkdir "$PREFLIGHT_TF_DIR"
export PATH="$temp/bin"
passed=0
check() {
  local label="$1" expected="$2" pattern="$3"
  shift 3
  : > "$MOCK_LOG"
  local status=0
  bash "$script" "$@" > "$temp/output" 2>&1 || status=$?
  if [[ "$status" != "$expected" ]] || ! grep -q "$pattern" "$temp/output"; then
    /bin/cat "$temp/output"
    echo "FAILED $label (exit $status, expected $expected)" >&2
    exit 1
  fi
  if grep -Eq 'az .* (create|register|invoke|add|set|delete)|terraform-operation' "$MOCK_LOG"; then
    echo "FAILED $label: mutating command invoked" >&2; exit 1
  fi
  echo "PASS test: $label"
  passed=$((passed + 1))
}
check 'local ready' 0 '0 failure(s)' --local
if grep -q 'az account' "$MOCK_LOG"; then echo 'Local checks accessed Azure' >&2; exit 1; fi
check 'new lab ready before state' 0 'Checking vCPU availability in region swedencentral'
grep -q 'cores: 32' "$temp/output"
grep -q '1 warning(s)' "$temp/output"
if grep -q 'Regional service capacity' "$temp/output"; then
  echo 'FAILED new lab ready before state: obsolete manual confirmation warning was emitted' >&2
  exit 1
fi
MOCK_CASE=stringquota check 'string quota values' 0 'cores: 32'
MOCK_CASE=windows check 'Windows shell' 1 'Run inside Linux' --local
MOCK_CASE=wsl1 check 'WSL1 unsupported' 1 'Convert your Ubuntu distribution to WSL2' --local
MOCK_CASE=oldterraform check 'Terraform minimum' 1 'Terraform 1.5+' --local
MOCK_CASE=parser check 'missing YAML parser' 1 'Install Python 3' --local
ln -s mock "$temp/bin/yq"
MOCK_CASE=parser check 'compatible yq fallback' 0 'Compatible yq' --local
MOCK_CASE=wrongparser check 'incompatible yq variant' 1 'Mike Farah yq' --local
rm "$temp/bin/yq"
MOCK_CASE=login check 'Azure login' 1 'Azure login is missing'
MOCK_CASE=disabled check 'disabled subscription' 1 'not Enabled'
ARM_SUBSCRIPTION_ID=other check 'subscription mismatch' 1 'ARM_SUBSCRIPTION_ID differs'
ARM_TENANT_ID=other check 'tenant mismatch' 1 'ARM_TENANT_ID differs'
MOCK_CASE=provider check 'provider registration' 1 'not Registered'
MOCK_CASE=watcher check 'missing watcher' 1 'Missing NetworkWatcher'
MOCK_CASE=wrongwatcherrg check 'watcher in wrong resource group' 1 'Missing NetworkWatcher'
MOCK_CASE=quota check 'insufficient quota' 1 'a new lab needs 16'
MOCK_LIMIT=16 check 'exact quota threshold' 0 '0 failure(s)'
MOCK_LIMIT=15 check 'one vCPU short' 1 'a new lab needs 16'
MOCK_CASE=existing check 'existing state quota warning' 0 'existing state detected'
MOCK_CASE=denied check 'unverifiable Azure checks' 0 'Cannot inspect'
TF_VARS='-var="location=uksouth"' MOCK_REGION=uksouth check 'same region override' 0 'Workload region: uksouth'
TF_VAR_location=uksouth MOCK_REGION=uksouth check 'environment region override' 0 'Workload region: uksouth'
TF_VARS='-var="deploy_madrid_vm=false" -var="deploy_paris_vm=false"' MOCK_LIMIT=12 check 'VM opt-outs' 0 'vCPU requirement: 12'
TF_VARS='-var-file=private.tfvars' check 'unknown override warning' 0 'Regional checks skipped'
TF_VARS='$(touch should-not-exist)' check 'override never evaluated' 0 'Regional checks skipped'
touch "$PREFLIGHT_TF_DIR/terraform.tfvars"
check 'auto-loaded variables warning' 0 'Regional checks skipped'
rm "$PREFLIGHT_TF_DIR/terraform.tfvars"
check 'DBA ready' 0 'SQL administrator' --track sql-dba
rm "$temp/bin/sqlcmd"
check 'missing DBA SQL client' 1 'Missing sqlcmd' --local --track sql-dba
ln -s mock "$temp/bin/sqlcmd"
MOCK_CASE=oldcli check 'DBA CLI minimum' 1 'requires Azure CLI 2.62' --local --track sql-dba
MOCK_CASE=extension check 'missing DBA extension' 1 'Install the Container Apps extension' --local --track sql-dba
check 'missing track argument' 2 'Use --track' --track
check 'unknown option' 2 'Unknown option' --unknown
rm "$temp/bin/git"
check 'missing local tool' 1 'Missing git' --local
ln -s "$(PATH=/usr/bin:/bin command -v git)" "$temp/bin/git"
rm "$temp/bin/jq" "$temp/bin/envsubst"
check 'aggregate independent failures' 1 '2 failure(s)' --local
ln -s "$real_jq" "$temp/bin/jq"
ln -s mock "$temp/bin/envsubst"

for role in Student Coach; do
  : > "$MOCK_LOG"
  if MOCK_CASE=login make -C "$root/$role" infra > "$temp/output" 2>&1; then
    echo "FAILED $role deployment gate" >&2; exit 1
  fi
  if grep -q 'terraform-operation' "$MOCK_LOG"; then echo "FAILED $role: Terraform ran past failed gate" >&2; exit 1; fi
  : > "$MOCK_LOG"
  if MOCK_CASE=login make -j4 -C "$root/$role" deploy > "$temp/output" 2>&1; then
    echo "FAILED $role parallel deployment gate" >&2; exit 1
  fi
  if grep -q 'config-sre-agent\\|sre-agent-apply-all\\|terraform-operation' "$MOCK_LOG" "$temp/output"; then
    echo "FAILED $role: configuration/deployment ran past failed gate" >&2; exit 1
  fi
  : > "$MOCK_LOG"
  make -C "$root/$role" infra > "$temp/output" 2>&1
  grep -q 'terraform-operation' "$MOCK_LOG"
  grep -q -- "-chdir=$( [[ "$role" == Student ]] && echo Resources/infra || echo Solutions/infra) init" "$MOCK_LOG"
  echo "PASS test: $role deployment gate/root"
  passed=$((passed + 1))
done
echo "$passed pre-flight tests passed."
