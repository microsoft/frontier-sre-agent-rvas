#!/usr/bin/env bash
set -euo pipefail

# ── 1. Global state ───────────────────────────────────────────────────────────

ARM_API_VERSION="${SRE_AGENT_ARM_API_VERSION:-2025-05-01-preview}"
DATA_PLANE_AUDIENCE="${SRE_AGENT_DATA_PLANE_AUDIENCE:-https://azuresre.dev}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
LAYOUT_FILE="${REPO_ROOT}/.sre-agent-layout.env"
CONFIG_DIR=""
CONFIG_DIR_EXPLICIT="false"

COMMAND=""
SUBSCRIPTION_ID=""
RESOURCE_GROUP=""
AGENT_NAME=""
ENDPOINT=""
ENV_FILE=""
TARGET=""
RESOURCE_NAME=""
RESOURCE_FILE=""
YES="false"
APPLY_FAILURES=()

# Token cache: written once in the main shell by _ensure_token; exported so
# subshells created by $() command substitution can read the cached file path.
export _TOKEN_FILE=""

# ── 1b. Output formatting ─────────────────────────────────────────────────────

# Auto-detect color support; suppressed when stdout is not a tty or NO_COLOR is set.
if [[ -t 1 && -z "${NO_COLOR:-}" ]]; then
  C_GREEN='\033[0;32m'; C_RED='\033[0;31m'; C_YELLOW='\033[1;33m'
  C_CYAN='\033[0;36m';  C_BOLD='\033[1m';   C_DIM='\033[2m'; C_RESET='\033[0m'
else
  C_GREEN=''; C_RED=''; C_YELLOW=''; C_CYAN=''; C_BOLD=''; C_DIM=''; C_RESET=''
fi

_PASS_COUNT=0
_FAIL_COUNT=0
_WARN_COUNT=0

_hr() { printf '%s\n' "$(printf '─%.0s' $(seq 1 62))"; }

print_header() {
  printf "\n${C_BOLD}%s${C_RESET}\n" "$*"
  _hr
}

# print_check <ok|warn|fail> <label> [detail]
print_check() {
  local status="$1" label="$2" detail="${3:-}"
  case "${status}" in
    ok)
      _PASS_COUNT=$((_PASS_COUNT + 1))
      printf "  ${C_GREEN}✓${C_RESET}  %-32s ${C_DIM}%s${C_RESET}\n" "${label}" "${detail}"
      ;;
    warn)
      _WARN_COUNT=$((_WARN_COUNT + 1))
      printf "  ${C_YELLOW}⚠${C_RESET}  %-32s ${C_DIM}%s${C_RESET}\n" "${label}" "${detail}"
      ;;
    fail)
      _FAIL_COUNT=$((_FAIL_COUNT + 1))
      printf "  ${C_RED}✗${C_RESET}  %-32s %s\n" "${label}" "${detail}"
      ;;
  esac
}

print_summary() {
  local total=$((_PASS_COUNT + _FAIL_COUNT + _WARN_COUNT))
  printf '\n'
  _hr
  if [[ "${_FAIL_COUNT}" -eq 0 ]]; then
    printf "${C_GREEN}${C_BOLD}  ✓  All checks passed${_WARN_COUNT:+ (${_WARN_COUNT} warning(s))}.${C_RESET}\n"
  else
    printf "${C_RED}${C_BOLD}  ✗  %d of %d check(s) failed.${C_RESET}\n" "${_FAIL_COUNT}" "${total}" >&2
  fi
  _hr
  [[ "${_FAIL_COUNT}" -eq 0 ]]
}

# ── 2. Config resolution ──────────────────────────────────────────────────────

usage() {
  cat <<'USAGE'
Usage: sre-agent-config.sh <command> [options]

Commands:
  validate   Validate local YAML/Markdown configuration.
  plan       Show the API operations that would be executed.
  apply      Apply local configuration to the live Azure SRE Agent.
  verify     Query the live Azure SRE Agent and list configured surfaces.
  delete     Delete local desired-state resources from the live agent. Requires --yes.
  prune      Reserved for explicit drift pruning. Always blocked in this v1 scaffold.

Options:
  --subscription ID       Azure subscription ID.
  --resource-group NAME   Resource group that contains the Azure SRE Agent.
  --agent NAME            Azure SRE Agent resource name.
  --endpoint URL          Data-plane endpoint. If omitted, the script reads it from ARM.
  --config PATH           Configuration directory. Overrides layout auto-discovery.
  --target TARGET         Limit validate, plan, apply, verify, or delete to one configuration target.
  --name NAME             Limit the selected target to one manifest name.
  --file PATH             Limit the selected target to one YAML manifest or knowledge file.
  --env-file PATH         Optional .env file loaded before placeholder substitution.
  --yes                   Confirm destructive delete operations.
  -h, --help              Show help.

Examples:
  ./Infra/scripts/sre-agent-config.sh validate
  ./Infra/scripts/sre-agent-config.sh plan --subscription <sub> --resource-group <rg> --agent <agent>
  ./Infra/scripts/sre-agent-config.sh apply --subscription <sub> --resource-group <rg> --agent <agent>
  ./Infra/scripts/sre-agent-config.sh plan --target skills --name sre-diagnostics-baseline --subscription <sub> --resource-group <rg> --agent <agent>
  ./Infra/scripts/sre-agent-config.sh verify --target skills --name sre-diagnostics-baseline --subscription <sub> --resource-group <rg> --agent <agent>
  ./Infra/scripts/sre-agent-config.sh delete --target skills --name sre-diagnostics-baseline --subscription <sub> --resource-group <rg> --agent <agent> --yes
USAGE
}

trim_space() {
  local value="$1"
  value="${value#"${value%%[![:space:]]*}"}"
  value="${value%"${value##*[![:space:]]}"}"
  printf '%s\n' "${value}"
}

strip_optional_quotes() {
  local value="$1"
  if [[ "${value}" == \"*\" && "${value}" == *\" ]]; then
    value="${value#\"}"
    value="${value%\"}"
  elif [[ "${value}" == \'*\' && "${value}" == *\' ]]; then
    value="${value#\'}"
    value="${value%\'}"
  fi
  printf '%s\n' "${value}"
}

layout_value() {
  local key="$1"
  local line candidate

  [[ -f "${LAYOUT_FILE}" ]] || return 0

  while IFS= read -r line || [[ -n "${line}" ]]; do
    line="${line%%#*}"
    line="$(trim_space "${line}")"
    [[ -z "${line}" ]] && continue
    [[ "${line}" == "${key}="* ]] || continue
    candidate="${line#*=}"
    candidate="$(trim_space "${candidate}")"
    strip_optional_quotes "${candidate}"
    return 0
  done < "${LAYOUT_FILE}"
}

repo_path() {
  local value="$1"
  if [[ "${value}" = /* ]]; then
    printf '%s\n' "${value}"
  else
    printf '%s/%s\n' "${REPO_ROOT}" "${value}"
  fi
}

canonical_dir() {
  local directory="$1"
  [[ -d "${directory}" ]] || return 1
  (cd "${directory}" && pwd)
}

config_dir_has_expected_shape() {
  local directory="$1"
  [[ -d "${directory}/skills" || -d "${directory}/subagents" || -d "${directory}/knowledge/files" ]]
}

resolve_config_dir() {
  local candidate="" layout_config_dir="" discovered source="auto-discovery"
  local checked=()

  if [[ "${CONFIG_DIR_EXPLICIT}" == "true" ]]; then
    candidate="${CONFIG_DIR}"
    source="--config"
  elif [[ -n "${SRE_AGENT_CONFIG_DIR:-}" ]]; then
    candidate="$(repo_path "${SRE_AGENT_CONFIG_DIR}")"
    source="SRE_AGENT_CONFIG_DIR"
  else
    layout_config_dir="$(layout_value SRE_AGENT_CONFIG_DIR)"
    if [[ -n "${layout_config_dir}" ]]; then
      candidate="$(repo_path "${layout_config_dir}")"
      source="${LAYOUT_FILE}:SRE_AGENT_CONFIG_DIR"
    fi
  fi

  if [[ -n "${candidate}" ]]; then
    checked+=("${candidate}")
    if discovered="$(canonical_dir "${candidate}")" && config_dir_has_expected_shape "${discovered}"; then
      CONFIG_DIR="${discovered}"
      return 0
    fi

    if [[ "${source}" != "auto-discovery" ]]; then
      printf 'ERROR: Invalid Azure SRE Agent configuration directory from %s: %s\n' "${source}" "${candidate}" >&2
      printf 'Expected an existing directory containing SRE Agent configuration, for example skills/, subagents/, or knowledge/files/.\n' >&2
      exit 1
    fi
  fi

  for candidate in \
    "${SCRIPT_DIR}/../../AZ-SRE-Agent-Configuration" \
    "${REPO_ROOT}/AZ-SRE-Agent-Configuration" \
    "${REPO_ROOT}/06-sre-agent-configuration" \
    "${REPO_ROOT}/configuration"; do
    checked+=("${candidate}")
    if discovered="$(canonical_dir "${candidate}")" && config_dir_has_expected_shape "${discovered}"; then
      CONFIG_DIR="${discovered}"
      return 0
    fi
  done

  printf 'ERROR: Could not resolve Azure SRE Agent configuration directory.\n' >&2
  printf 'Checked:\n' >&2
  printf '  - %s\n' "${checked[@]}" >&2
  printf 'Set --config, SRE_AGENT_CONFIG_DIR, or SRE_AGENT_CONFIG_DIR in %s.\n' "${LAYOUT_FILE}" >&2
  exit 1
}

# ── 3. Utilities ──────────────────────────────────────────────────────────────

log()  { printf "  ${C_CYAN}→${C_RESET}  %s\n" "$*"; }

die() { printf "${C_RED}ERROR:${C_RESET} %s\n" "$*" >&2; exit 1; }

record_apply_failure() {
  local label="$1" exit_code="$2"
  APPLY_FAILURES+=("${label} (exit ${exit_code})")
  printf "  ${C_RED}✗${C_RESET}  %s failed (exit %s) — continuing.\n" "${label}" "${exit_code}" >&2
}

run_apply_step() {
  local label="$1"
  local exit_code
  shift
  if ( "$@" ); then
    return 0
  else
    exit_code="$?"
    record_apply_failure "${label}" "${exit_code}"
    return 0
  fi
}

finish_full_apply() {
  local failure
  printf '\n'
  _hr
  if [[ "${#APPLY_FAILURES[@]}" -eq 0 ]]; then
    printf "${C_GREEN}${C_BOLD}  ✓  Apply completed — all steps succeeded.${C_RESET}\n"
    _hr
    return 0
  fi
  printf "${C_RED}${C_BOLD}  ✗  Apply completed with %d failure(s):${C_RESET}\n" "${#APPLY_FAILURES[@]}" >&2
  for failure in "${APPLY_FAILURES[@]}"; do
    printf "       ${C_RED}•${C_RESET}  %s\n" "${failure}" >&2
  done
  _hr
  return 1
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || die "Required command not found: $1"
}

require_yaml_parser() {
  if command -v python3 >/dev/null 2>&1 && python3 -c 'import yaml, json' >/dev/null 2>&1; then
    return 0
  fi
  if command -v yq >/dev/null 2>&1; then
    return 0
  fi
  die "Required YAML parser not found: install yq or Python 3 with PyYAML"
}

load_env_file() {
  [[ -z "${ENV_FILE}" ]] && return 0
  [[ -f "${ENV_FILE}" ]] || die "Environment file not found: ${ENV_FILE}"
  set -a
  # shellcheck disable=SC1090
  source "${ENV_FILE}"
  set +a
}

require_local_dependencies() {
  require_command jq
  require_yaml_parser
}

require_azure_dependencies() {
  require_command az
  require_command curl
  require_command jq
  require_yaml_parser
}

# ── 4. Argument parsing ───────────────────────────────────────────────────────

parse_args() {
  [[ $# -eq 0 ]] && { usage; exit 1; }
  COMMAND="$1"
  shift

  while [[ $# -gt 0 ]]; do
    case "$1" in
      --subscription)   SUBSCRIPTION_ID="${2:-}"; shift 2 ;;
      --resource-group) RESOURCE_GROUP="${2:-}";  shift 2 ;;
      --agent)          AGENT_NAME="${2:-}";       shift 2 ;;
      --endpoint)       ENDPOINT="${2:-}";         shift 2 ;;
      --config)
        [[ -n "${2:-}" ]] || die "--config requires a path"
        CONFIG_DIR="$(repo_path "${2}")"
        CONFIG_DIR_EXPLICIT="true"
        shift 2
        ;;
      --target)   TARGET="${2:-}";   shift 2 ;;
      --name)     RESOURCE_NAME="${2:-}"; shift 2 ;;
      --file)
        [[ -n "${2:-}" ]] || die "--file requires a path"
        if [[ "${2}" = /* ]]; then
          RESOURCE_FILE="${2}"
        else
          RESOURCE_FILE="$(cd "$(dirname "${2}")" && pwd)/$(basename "${2}")"
        fi
        shift 2
        ;;
      --env-file) ENV_FILE="${2:-}"; shift 2 ;;
      --yes)      YES="true";        shift ;;
      -h|--help)  usage; exit 0 ;;
      *)          die "Unknown option: $1" ;;
    esac
  done
}

# ── 5. File discovery ─────────────────────────────────────────────────────────

find_yaml_files() {
  local directory="$1"
  [[ -d "${directory}" ]] || return 0
  # example-* manifests are kept in Git as templates but never deployed.
  find "${directory}" -maxdepth 1 -type f \( -name '*.yaml' -o -name '*.yml' \) ! -name 'example-*' | sort
}

find_all_yaml_files() {
  [[ -d "${CONFIG_DIR}" ]] || die "Configuration directory not found: ${CONFIG_DIR}"
  find "${CONFIG_DIR}" -type f \( -name '*.yaml' -o -name '*.yml' \) ! -name 'example-*' | sort
}

find_knowledge_files() {
  local directory="$1"
  [[ -d "${directory}" ]] || return 0
  # Recurse into subdirectories so grouped knowledge bases are discovered.
  # Basenames are unique across groups, so recursion cannot cause collisions.
  find "${directory}" -type f ! -name 'example-*' | sort
}

# Emit the YAML files for the current selection (TARGET/RESOURCE_NAME/RESOURCE_FILE).
# Falls back to all files in dir when no name/file selection is active.
selected_or_all_yaml_files() {
  local dir="$1"
  local file name

  if [[ -n "${RESOURCE_FILE}" ]]; then
    printf '%s\n' "${RESOURCE_FILE}"
    return 0
  fi

  while IFS= read -r file; do
    [[ -z "${file}" ]] && continue
    if [[ -n "${RESOURCE_NAME}" ]]; then
      name="$(manifest_raw_name "${file}")"
      [[ "${name}" == "${RESOURCE_NAME}" ]] || continue
    fi
    printf '%s\n' "${file}"
  done < <(find_yaml_files "${CONFIG_DIR}/${dir}")
}

# Emit the knowledge files for the current RESOURCE_NAME/RESOURCE_FILE selection.
selected_or_all_knowledge_files() {
  local directory="${CONFIG_DIR}/knowledge/files"
  local file base stem

  if [[ -n "${RESOURCE_FILE}" ]]; then
    printf '%s\n' "${RESOURCE_FILE}"
    return 0
  fi

  [[ -d "${directory}" ]] || return 0
  while IFS= read -r file; do
    [[ -z "${file}" ]] && continue
    if [[ -n "${RESOURCE_NAME}" ]]; then
      base="$(basename "${file}")"
      stem="${base%.*}"
      [[ "${base}" == "${RESOURCE_NAME}" || "${stem}" == "${RESOURCE_NAME}" ]] || continue
    fi
    printf '%s\n' "${file}"
  done < <(find_knowledge_files "${directory}")
}

selection_requested() {
  [[ -n "${TARGET}" || -n "${RESOURCE_NAME}" || -n "${RESOURCE_FILE}" ]]
}

# ── 6. Resource-type dispatch tables ─────────────────────────────────────────
#
# Each entry maps a --target name to the components needed to apply, delete,
# and verify it without scattered case statements.
#
# T_DIR    - config subdirectory, relative to CONFIG_DIR
# T_PUT    - function invoked to apply (plan or apply) one YAML file
# T_DEL    - function invoked to delete one YAML file ("none" = unsupported)
# T_VFY_EP - data-plane endpoint used to verify
# T_VFY_MD - verify mode: "item" (GET /ep/name) or "list" (collection scan)
#
# Special targets NOT in this table (handled with dedicated code):
#   incident-platforms  - ARM PATCH, not data-plane
#   knowledge-files     - multipart upload, not JSON PUT

declare -A T_DIR=(
  [skills]="skills"
  [subagents]="subagents"
  [tools]="tools"
  [common-prompts]="common-prompts"
  [scheduled-tasks]="automations/scheduled-tasks"
  [incident-filters]="automations/incident-filters"
  [connectors]="connectors"
  [repos]="repos"
  [hooks]="hooks"
  [plugin-configs]="plugin-configs"
  [http-triggers]="automations/http-triggers"
  [plugin-marketplaces]="plugins/marketplaces"
  [plugin-installations]="plugins/installations"
)

declare -A T_PUT=(
  [skills]="data_put_skill"
  [subagents]="data_put_subagent"
  [tools]="data_put_tool"
  [common-prompts]="data_put_common_prompt"
  [scheduled-tasks]="data_put_scheduled_task"
  [incident-filters]="data_put_incident_filter"
  [connectors]="data_put_connector"
  [repos]="data_put_repo"
  [hooks]="data_put_hook"
  [plugin-configs]="data_put_plugin_config"
  [http-triggers]="data_post_http_trigger"
  [plugin-marketplaces]="data_post_plugin_marketplace"
  [plugin-installations]="data_post_plugin_installation"
)

declare -A T_DEL=(
  [skills]="data_delete_skill"
  [subagents]="data_delete_subagent"
  [tools]="data_delete_tool"
  [common-prompts]="data_delete_common_prompt"
  [scheduled-tasks]="data_delete_scheduled_task"
  [incident-filters]="data_delete_incident_filter"
  [connectors]="data_delete_connector"
  [repos]="data_delete_repo"
  [hooks]="data_delete_hook"
  [plugin-configs]="data_delete_plugin_config"
  [http-triggers]="none"
  [plugin-marketplaces]="none"
  [plugin-installations]="none"
)

declare -A T_VFY_EP=(
  [skills]="/api/v2/extendedAgent/skills"
  [subagents]="/api/v2/extendedAgent/agents"
  [tools]="/api/v2/extendedAgent/tools"
  [common-prompts]="/api/v2/extendedAgent/commonprompts"
  [scheduled-tasks]="/api/v2/extendedAgent/scheduledtasks"
  [incident-filters]="/api/v2/extendedAgent/incidentFilters"
  [connectors]="/api/v2/extendedAgent/connectors"
  [repos]="/api/v2/repos"
  [hooks]="/api/v2/extendedAgent/hooks"
  [plugin-configs]="/api/v2/extendedAgent/plugins"
  [http-triggers]="/api/v1/httptriggers"
  [plugin-marketplaces]="/api/v2/plugins/marketplaces"
  [plugin-installations]="/api/v2/plugins/installations"
)

# "item" = verify by name via GET /endpoint/name
# "list" = verify by scanning a collection endpoint
declare -A T_VFY_MD=(
  [skills]="item"          [subagents]="item"
  [tools]="item"           [common-prompts]="item"
  [scheduled-tasks]="item" [incident-filters]="item"
  [connectors]="item"      [repos]="item"
  [hooks]="item"           [plugin-configs]="item"
  [http-triggers]="list"   [plugin-marketplaces]="list"
  [plugin-installations]="list"
)

validate_target() {
  # incident-platforms and knowledge-files are valid but handled specially.
  case "$1" in
    incident-platforms|knowledge-files) ;;
    *) [[ -n "${T_DIR[$1]:-}" ]] || die "Unknown target: $1" ;;
  esac
}

infer_target_from_file() {
  local file="$1" relative_path="" target dir

  [[ "${file}" = "${CONFIG_DIR}/"* ]] || return 0
  relative_path="${file#"${CONFIG_DIR}/"}"

  [[ "${relative_path}" == knowledge/files/* ]] && { printf 'knowledge-files\n'; return 0; }
  [[ "${relative_path}" == incident-platforms/*.yaml || "${relative_path}" == incident-platforms/*.yml ]] \
    && { printf 'incident-platforms\n'; return 0; }

  for target in "${!T_DIR[@]}"; do
    dir="${T_DIR[$target]}"
    if [[ "${relative_path}" == "${dir}/"*.yaml || "${relative_path}" == "${dir}/"*.yml ]]; then
      printf '%s\n' "${target}"
      return 0
    fi
  done
}

normalize_selection() {
  local inferred_target="" file_name=""

  selection_requested || return 0

  [[ -n "${RESOURCE_NAME}" && -z "${TARGET}" && -z "${RESOURCE_FILE}" ]] \
    && die "--name requires --target or --file"

  if [[ -n "${RESOURCE_FILE}" ]]; then
    [[ -f "${RESOURCE_FILE}" ]] || die "File not found: ${RESOURCE_FILE}"
    inferred_target="$(infer_target_from_file "${RESOURCE_FILE}")"

    if [[ -z "${TARGET}" ]]; then
      [[ -n "${inferred_target}" ]] || die "Could not infer --target from --file. Pass --target explicitly."
      TARGET="${inferred_target}"
    elif [[ -n "${inferred_target}" && "${TARGET}" != "${inferred_target}" ]]; then
      die "--file target ${inferred_target} does not match --target ${TARGET}"
    fi
  fi

  [[ -n "${TARGET}" ]] || die "--target is required for selective operations"
  validate_target "${TARGET}"

  if [[ -n "${RESOURCE_FILE}" && -n "${RESOURCE_NAME}" ]]; then
    if [[ "${TARGET}" == "knowledge-files" ]]; then
      file_name="$(basename "${RESOURCE_FILE}")"
      [[ "${file_name}" == "${RESOURCE_NAME}" || "${file_name%.*}" == "${RESOURCE_NAME}" ]] \
        || die "--file ${RESOURCE_FILE} does not match --name ${RESOURCE_NAME}"
    else
      file_name="$(manifest_name "${RESOURCE_FILE}")"
      [[ "${file_name}" == "${RESOURCE_NAME}" ]] \
        || die "--file manifest name ${file_name} does not match --name ${RESOURCE_NAME}"
    fi
  fi
}

# ── 7. Manifest helpers ───────────────────────────────────────────────────────

yaml_to_json() {
  if command -v python3 >/dev/null 2>&1 && python3 -c 'import yaml, json' >/dev/null 2>&1; then
    python3 -c 'import json, sys, yaml; print(json.dumps(yaml.safe_load(sys.stdin.read())))'
  else
    yq -o=json '.' -
  fi
}

require_arm_args() {
  [[ -n "${SUBSCRIPTION_ID}" ]] || die "--subscription is required"
  [[ -n "${RESOURCE_GROUP}" ]]  || die "--resource-group is required"
  [[ -n "${AGENT_NAME}" ]]      || die "--agent is required"
}

placeholders_in_file() {
  grep -Eo '\$\{[A-Za-z_][A-Za-z0-9_]*\}' "${1}" 2>/dev/null | sort -u || true
}

validate_placeholders() {
  local file="$1" placeholder variable
  while IFS= read -r placeholder; do
    [[ -z "${placeholder}" ]] && continue
    variable="${placeholder#\$\{}"
    variable="${variable%\}}"
    [[ -n "${!variable:-}" ]] || die "${file} references ${placeholder}, but ${variable} is not set"
  done < <(placeholders_in_file "${file}")
}

render_text_file() {
  local file="$1"
  validate_placeholders "${file}"
  if [[ -n "$(placeholders_in_file "${file}")" ]]; then
    require_command envsubst
    envsubst < "${file}"
  else
    sed -n '1,$p' "${file}"
  fi
}

render_yaml_to_json() {
  local file="$1"
  validate_placeholders "${file}"
  if [[ -n "$(placeholders_in_file "${file}")" ]]; then
    require_command envsubst
    envsubst < "${file}" | yaml_to_json
  else
    yaml_to_json < "${file}"
  fi
}

manifest_json() {
  local file="$1"
  local json content_file content_path content_json
  json="$(render_yaml_to_json "${file}")" || return $?
  content_file="$(jq -r '.spec.content_file // empty' <<< "${json}")"
  [[ -z "${content_file}" ]] && { printf '%s\n' "${json}"; return 0; }

  if [[ "${content_file}" = /* ]]; then
    content_path="${content_file}"
  else
    content_path="$(cd "$(dirname "${file}")" && pwd)/${content_file}"
  fi

  [[ -f "${content_path}" ]] || die "Content file not found: ${content_path}"
  content_json="$(render_text_file "${content_path}" | jq -Rs '.')" || return $?
  jq --argjson content "${content_json}" '.spec.content = $content | del(.spec.content_file)' <<< "${json}"
}

manifest_raw_name() {
  local file="$1" json name
  json="$(yaml_to_json < "${file}")" || return $?
  name="$(jq -r '.metadata.name // .spec.name // .name // empty' <<< "${json}")"
  [[ -n "${name}" ]] || die "Manifest has no metadata.name, spec.name, or name: ${file}"
  printf '%s\n' "${name}"
}

manifest_name() {
  local file="$1" json name
  json="$(manifest_json "${file}")" || return $?
  name="$(jq -r '.metadata.name // .spec.name // .name // empty' <<< "${json}")"
  [[ -n "${name}" ]] || die "Manifest has no metadata.name, spec.name, or name: ${file}"
  printf '%s\n' "${name}"
}

manifest_deployment_status() {
  manifest_json "${1}" | jq -r '.spec.deployment.status // .deployment.status // empty'
}

is_manifest_api_preview_blocked() {
  [[ "$(manifest_deployment_status "${1}")" == "api-preview-blocked" ]]
}

validate_manifest() {
  local file="$1" json raw_json content_file content_path name kind
  validate_placeholders "${file}"
  json="$(manifest_json "${file}")" || return $?
  name="$(jq -r '.metadata.name // .spec.name // .name // empty' <<< "${json}")"
  kind="$(jq -r '.kind // empty' <<< "${json}")"
  [[ -n "${name}" ]] || die "Missing manifest name in ${file}"
  [[ -n "${kind}" ]] || die "Missing kind in ${file}"

  raw_json="$(render_yaml_to_json "${file}")" || return $?
  content_file="$(jq -r '.spec.content_file // empty' <<< "${raw_json}")"
  [[ -z "${content_file}" ]] && return 0
  content_path="$(cd "$(dirname "${file}")" && pwd)/${content_file}"
  [[ "${content_file}" = /* ]] && content_path="${content_file}"
  [[ -f "${content_path}" ]] || die "Missing content file ${content_path} referenced by ${file}"
}

# ── 8. Azure API primitives ───────────────────────────────────────────────────

arm_agent_base_url() {
  printf 'https://management.azure.com/subscriptions/%s/resourceGroups/%s/providers/Microsoft.App/agents/%s' \
    "${SUBSCRIPTION_ID}" "${RESOURCE_GROUP}" "${AGENT_NAME}"
}

get_endpoint_from_arm() {
  require_arm_args
  az rest --method GET \
    --url "$(arm_agent_base_url)?api-version=${ARM_API_VERSION}" \
    --query properties.agentEndpoint \
    --output tsv
}

ensure_endpoint() {
  [[ -n "${ENDPOINT}" ]] || ENDPOINT="$(get_endpoint_from_arm)"
  [[ -n "${ENDPOINT}" ]] || die "Could not resolve agent endpoint"
  ENDPOINT="${ENDPOINT%/}"
}

# Fetch the data-plane access token once and write it to a temp file. This
# function MUST be called in the main shell (not inside $()) so that the
# exported _TOKEN_FILE path is visible to all subsequent subshells.
_ensure_token() {
  [[ -n "${_TOKEN_FILE}" && -f "${_TOKEN_FILE}" ]] && return 0
  _TOKEN_FILE="$(mktemp)"
  export _TOKEN_FILE
  trap 'rm -f "${_TOKEN_FILE}"' EXIT
  az account get-access-token \
    --resource "${DATA_PLANE_AUDIENCE}" \
    --query accessToken --output tsv > "${_TOKEN_FILE}"
}

# Return the cached bearer token. Falls back to a live fetch when called
# before _ensure_token (e.g. verify, selective apply).
data_plane_token() {
  if [[ -n "${_TOKEN_FILE}" && -f "${_TOKEN_FILE}" ]]; then
    cat "${_TOKEN_FILE}"
  else
    az account get-access-token \
      --resource "${DATA_PLANE_AUDIENCE}" \
      --query accessToken --output tsv
  fi
}

data_put_manifest() {
  local endpoint_path="$1" file="$2"
  local name json body token url
  validate_manifest "${file}"
  name="$(manifest_name "${file}")"
  json="$(manifest_json "${file}")"
  body="$(jq --arg name "${name}" \
    'if (.api_version? or .metadata? or .spec? or .kind?) then
       {name:$name,type:(.kind // "Configuration"),tags:(.tags // []),
        properties:(.spec.properties // .spec // .properties // {})}
     else . end' <<< "${json}")"

  if [[ "${COMMAND}" == "plan" ]]; then
    log "PUT data-plane ${endpoint_path}/${name} from ${file}"
  else
    token="$(data_plane_token)"
    url="${ENDPOINT}${endpoint_path}/${name}"
    curl -fsS -X PUT \
      -H "Authorization: Bearer ${token}" \
      -H 'Content-Type: application/json' \
      --data "${body}" \
      "${url}" >/dev/null
    log "Applied data-plane ${endpoint_path}/${name}"
  fi
}

data_put_extended() {
  local endpoint_kind="$1" resource_type="$2" file="$3" props="$4"
  # max_attempts and retry_sleep are optional; defaults preserve fail-fast
  # behavior for every caller except incident-filters (which races an async
  # AzMonitor PATCH and needs up to 5 retries).
  local max_attempts="${5:-1}" retry_sleep="${6:-10}"
  local name body token url attempt http_code

  validate_manifest "${file}"
  name="$(manifest_name "${file}")"
  body="$(jq -n \
    --arg name "${name}" --arg type "${resource_type}" --argjson props "${props}" \
    '{name:$name,type:$type,tags:[],properties:$props}')"

  if [[ "${COMMAND}" == "plan" ]]; then
    log "PUT data-plane /api/v2/extendedAgent/${endpoint_kind}/${name} from ${file}"
    return 0
  fi

  url="${ENDPOINT}/api/v2/extendedAgent/${endpoint_kind}/${name}"
  attempt=1
  while true; do
    token="$(data_plane_token)"
    http_code="$(curl -sS -o /dev/null -w '%{http_code}' -X PUT \
      -H "Authorization: Bearer ${token}" \
      -H 'Content-Type: application/json' \
      --data "${body}" \
      "${url}" || true)"
    if [[ "${http_code}" == 2* ]]; then
      log "Applied data-plane /api/v2/extendedAgent/${endpoint_kind}/${name}"
      return 0
    fi
    if [[ "${attempt}" -ge "${max_attempts}" ]]; then
      die "PUT /api/v2/extendedAgent/${endpoint_kind}/${name} failed with HTTP ${http_code} after ${attempt} attempt(s)"
    fi
    log "PUT /api/v2/extendedAgent/${endpoint_kind}/${name} returned HTTP ${http_code}; retrying in ${retry_sleep}s (attempt ${attempt}/${max_attempts})"
    sleep "${retry_sleep}"
    attempt=$((attempt + 1))
  done
}

data_post_manifest() {
  local endpoint_path="$1" file="$2"
  local name json body token url
  validate_manifest "${file}"
  name="$(manifest_name "${file}")"
  json="$(manifest_json "${file}")"
  if [[ "${endpoint_path}" == "/api/v1/httptriggers/create" ]]; then
    body="$(jq -c --arg name "${name}" \
      'if (.api_version? or .metadata? or .spec? or .kind?) then ({name:$name} + (.spec // .properties // {})) else . end' \
      <<< "${json}")"
  else
    body="$(jq -c --arg name "${name}" \
      'if (.api_version? or .metadata? or .spec? or .kind?) then {metadata:{name:$name},spec:(.spec // .properties // {})} else . end' \
      <<< "${json}")"
  fi

  if [[ "${COMMAND}" == "plan" ]]; then
    log "POST data-plane ${endpoint_path} for ${name} from ${file}"
  else
    token="$(data_plane_token)"
    url="${ENDPOINT}${endpoint_path}"
    if [[ "${endpoint_path}" == "/api/v1/httptriggers/create" ]]; then
      if curl -fsS -H "Authorization: Bearer ${token}" "${ENDPOINT}/api/v1/httptriggers" \
        | jq -e --arg name "${name}" \
            '(if type == "array" then . else (.value // []) end) | any(.[]?; .name == $name)' >/dev/null; then
        log "Skipped existing HTTP trigger ${name}"
        return 0
      fi
    fi
    curl -fsS -X POST \
      -H "Authorization: Bearer ${token}" \
      -H 'Content-Type: application/json' \
      --data "${body}" \
      "${url}" >/dev/null
    log "Applied data-plane POST ${endpoint_path} for ${name}"
  fi
}

data_delete_manifest() {
  local endpoint_path="$1" file="$2"
  local name token url
  name="$(manifest_name "${file}")"
  token="$(data_plane_token)"
  url="${ENDPOINT}${endpoint_path}/${name}"
  curl -fsS -X DELETE -H "Authorization: Bearer ${token}" "${url}" >/dev/null
  log "Deleted data-plane ${endpoint_path}/${name}"
}

# ── 9. Resource-type property builders ───────────────────────────────────────

skill_properties() {
  local json name
  json="$(manifest_json "${1}")"
  name="$(manifest_name "${1}")"
  jq -c --arg name "${name}" '{
    name: $name,
    description: (.metadata.description // .spec.description // ""),
    tools: (.metadata.spec.tools // .spec.tools // []),
    skillContent: (.skillContent // .spec.skillContent // .spec.content // ""),
    additionalFiles: (.additionalFiles // .spec.additionalFiles // [])
  }' <<< "${json}"
}

subagent_properties() {
  manifest_json "${1}" | jq -c '
    .spec as $spec | {
      description:        ($spec.description // ""),
      instructions:       ($spec.instructions // $spec.system_prompt // $spec.content // ""),
      handoffDescription: ($spec.handoffDescription // $spec.handoff_description // ""),
      handoffs:           ($spec.handoffs // []),
      tools:              ($spec.tools // []),
      agentType:          ($spec.agentType // $spec.agent_type // "Review"),
      temperature:        ($spec.temperature // 0.2),
      enableSkills:       ($spec.enableSkills // $spec.enable_skills // false),
      allowedSkills:      ($spec.allowedSkills // $spec.allowed_skills // []),
      mcpTools:           ($spec.mcpTools // $spec.mcp_tools // [])
    }'
}

tool_properties() {
  manifest_json "${1}" | jq -c '.spec // .properties // {}'
}

common_prompt_properties() {
  manifest_json "${1}" | jq -c '.spec as $spec | {
    description: ($spec.description // ""),
    prompt:      ($spec.prompt // $spec.content // "")
  }'
}

scheduled_task_properties() {
  local json name
  json="$(manifest_json "${1}")"
  name="$(manifest_name "${1}")"
  jq -c --arg name "${name}" '
    .spec as $spec |
    {
      name:            ($spec.name // $name),
      description:     ($spec.description // ""),
      cronExpression:  ($spec.cronExpression // $spec.schedule // ""),
      agentPrompt:     ($spec.agentPrompt // $spec.prompt // ""),
      agentMode:       ($spec.agentMode // $spec.mode // "Review"),
      isEnabled:       (if ($spec|has("isEnabled")) then $spec.isEnabled
                        elif ($spec|has("enabled")) then $spec.enabled
                        else true end),
      timeZone:        ($spec.timeZone // $spec.time_zone // "UTC")
    }
    | if (($spec.agent // "") == "") then . else . + {agent: $spec.agent} end
  ' <<< "${json}"
}

incident_filter_properties() {
  manifest_json "${1}" | jq -c '
    .spec as $spec |
    $spec + {
      incidentPlatform: ($spec.incidentPlatform // $spec.platformType // "AzMonitor"),
      handlingAgent:    ($spec.handlingAgent // $spec.action.run_skill // "default"),
      isEnabled:        (if ($spec|has("isEnabled")) then $spec.isEnabled
                         elif ($spec|has("enabled")) then $spec.enabled
                         else false end)
    }'
}

hook_properties() {
  manifest_json "${1}" | jq -c '.spec // .properties // {}'
}

# ── 10. Resource-type put / delete wrappers ───────────────────────────────────
#
# One put wrapper and one delete wrapper per resource type. These are the
# function names stored in the T_PUT and T_DEL dispatch tables. Adding a new
# resource type only requires adding wrappers here and a row in each table.

data_put_skill()          { data_put_extended "skills"         "Skill"         "$1" "$(skill_properties         "$1")"; }
data_put_subagent()       { data_put_extended "agents"         "ExtendedAgent" "$1" "$(subagent_properties      "$1")"; }
data_put_common_prompt()  { data_put_extended "commonprompts"  "CommonPrompt"  "$1" "$(common_prompt_properties "$1")"; }
data_put_scheduled_task() { data_put_extended "scheduledtasks" "ScheduledTask" "$1" "$(scheduled_task_properties "$1")"; }
data_put_hook()           { data_put_extended "hooks"          "GlobalHook"    "$1" "$(hook_properties           "$1")"; }

data_put_tool() {
  is_manifest_api_preview_blocked "${1}" \
    && { log "Skipped API-preview-blocked tool $(manifest_name "${1}")"; return 0; }
  data_put_extended "tools" "Tool" "${1}" "$(tool_properties "${1}")"
}

# The AzMonitor incident platform PATCH is asynchronous; a freshly enabled
# platform may not be ready for the first filter PUT (returns HTTP 400). Retry.
data_put_incident_filter() {
  data_put_extended "incidentFilters" "IncidentFilter" "$1" "$(incident_filter_properties "$1")" \
    "${SRE_AGENT_INCIDENT_FILTER_MAX_ATTEMPTS:-5}" "${SRE_AGENT_INCIDENT_FILTER_RETRY_SLEEP:-10}"
}

data_put_connector()           { data_put_manifest "/api/v2/extendedAgent/connectors" "$1"; }
data_put_plugin_config()       { data_put_manifest "/api/v2/extendedAgent/plugins"    "$1"; }
data_post_http_trigger()       { data_post_manifest "/api/v1/httptriggers/create"      "$1"; }
data_post_plugin_marketplace() { data_post_manifest "/api/v2/plugins/marketplaces"    "$1"; }
data_post_plugin_installation(){ data_post_manifest "/api/v2/plugins/installations"   "$1"; }

data_delete_skill()          { data_delete_manifest "/api/v2/extendedAgent/skills"          "$1"; }
data_delete_subagent()       { data_delete_manifest "/api/v2/extendedAgent/agents"          "$1"; }
data_delete_common_prompt()  { data_delete_manifest "/api/v2/extendedAgent/commonprompts"   "$1"; }
data_delete_scheduled_task() { data_delete_manifest "/api/v2/extendedAgent/scheduledtasks"  "$1"; }
data_delete_incident_filter(){ data_delete_manifest "/api/v2/extendedAgent/incidentFilters" "$1"; }
data_delete_connector()      { data_delete_manifest "/api/v2/extendedAgent/connectors"      "$1"; }
data_delete_hook()           { data_delete_manifest "/api/v2/extendedAgent/hooks"           "$1"; }
data_delete_plugin_config()  { data_delete_manifest "/api/v2/extendedAgent/plugins"         "$1"; }

data_delete_tool() {
  is_manifest_api_preview_blocked "${1}" \
    && { log "Skipped API-preview-blocked tool $(manifest_name "${1}")"; return 0; }
  data_delete_manifest "/api/v2/extendedAgent/tools" "${1}"
}

data_put_repo() {
  local file="$1" name json body token url
  validate_manifest "${file}"
  name="$(manifest_name "${file}")"
  json="$(manifest_json "${file}")"
  body="$(jq -c --arg name "${name}" '
    .spec as $spec |
    ($spec.type // "GitHub" | ascii_downcase) as $repo_type |
    {
      name: $name, type: "CodeRepo",
      properties: {
        url:  $spec.url,
        type: (if $repo_type == "ado" or $repo_type == "azuredevops" or $repo_type == "azure-devops"
               then "AzureDevOps" else "GitHub" end)
      }
    }
    | if (($spec.description     // "") == "") then . else .properties.description     = $spec.description     end
    | if (($spec.authConnectorName // "") == "") then . else .properties.authConnectorName = $spec.authConnectorName end
  ' <<< "${json}")"

  if [[ "${COMMAND}" == "plan" ]]; then
    log "PUT data-plane repo ${name} from ${file}"
  else
    token="$(data_plane_token)"
    url="${ENDPOINT}/api/v2/repos/${name}"
    curl -fsS -X PUT \
      -H "Authorization: Bearer ${token}" \
      -H 'Content-Type: application/json' \
      --data "${body}" \
      "${url}" >/dev/null
    log "Applied data-plane repo ${name}"
  fi
}

data_delete_repo() {
  local name token url
  name="$(manifest_name "${1}")"
  token="$(data_plane_token)"
  url="${ENDPOINT}/api/v2/repos/${name}"
  curl -fsS -X DELETE -H "Authorization: Bearer ${token}" "${url}" >/dev/null
  log "Deleted data-plane repo ${name}"
}

upload_knowledge_file() {
  local file="$1" token
  if [[ "${COMMAND}" == "plan" ]]; then
    log "POST knowledge upload ${file}"
  else
    token="$(data_plane_token)"
    curl -fsS -X POST \
      -H "Authorization: Bearer ${token}" \
      -F "files=@${file}" \
      "${ENDPOINT}/api/v1/agentmemory/upload" >/dev/null
    log "Uploaded knowledge file ${file}"
  fi
}

delete_knowledge_file() {
  local file="$1" filename encoded_name token url
  filename="$(basename "${file}")"
  encoded_name="$(printf '%s' "${filename}" | jq -sRr @uri)"
  token="$(data_plane_token)"
  url="${ENDPOINT}/api/v1/agentmemory/document/${encoded_name}"
  curl -fsS -X DELETE -H "Authorization: Bearer ${token}" "${url}" >/dev/null
  log "Deleted knowledge file ${filename}"
}

apply_incident_platform_file() {
  local file="$1" name json platform_type connection_key body

  validate_manifest "${file}"
  name="$(manifest_name "${file}")"
  json="$(manifest_json "${file}")"
  platform_type="$(jq -r '.spec.platformType // .spec.incidentPlatform // empty' <<< "${json}")"
  connection_key="$(jq -r '.spec.connectionKey // empty' <<< "${json}")"
  [[ -n "${platform_type}" ]] || die "Incident platform ${file} must define spec.platformType"

  if [[ "${COMMAND}" == "plan" ]]; then
    log "PATCH ARM incident platform ${name} (${platform_type}) from ${file}"
    return 0
  fi

  if [[ -n "${connection_key}" ]]; then
    body="$(jq -n --arg type "${platform_type}" --arg connectionName "${name}" --arg connectionKey "${connection_key}" \
      '{properties:{incidentManagementConfiguration:{type:$type,connectionName:$connectionName,connectionKey:$connectionKey}}}')"
  else
    body="$(jq -n --arg type "${platform_type}" --arg connectionName "${name}" \
      '{properties:{incidentManagementConfiguration:{type:$type,connectionName:$connectionName}}}')"
  fi

  az rest --method PATCH \
    --url "$(arm_agent_base_url)?api-version=${ARM_API_VERSION}" \
    --body "${body}" \
    --output none
  log "Applied incident platform ${name} (${platform_type})"
}

delete_incident_platform() {
  az rest --method PATCH \
    --url "$(arm_agent_base_url)?api-version=${ARM_API_VERSION}" \
    --body '{"properties":{"incidentManagementConfiguration":{"type":"None"}}}' \
    --output none
  log "Cleared incident platform configuration"
}

# ── 11. Generic apply / delete / verify loops ────────────────────────────────
#
# These three functions replace ~15 near-identical loop variants from the
# original (apply_extension_directory, apply_extension_directory_best_effort,
# apply_extension_directory_selected, apply_data_directory_*, etc.).

# Apply (plan or apply) every YAML file in dir. In apply mode, failures are
# recorded best-effort via run_apply_step; in plan mode, errors are fatal.
# Pass assert_match=true to require at least one file match (selected ops).
apply_directory() {
  local put_fn="$1" dir="$2" label="$3" assert_match="${4:-false}"
  local file count=0

  while IFS= read -r file; do
    [[ -z "${file}" ]] && continue
    count=$((count + 1))
    if [[ "${COMMAND}" == "apply" ]]; then
      run_apply_step "${label}: ${file}" "${put_fn}" "${file}"
    else
      "${put_fn}" "${file}"
    fi
  done < <(selected_or_all_yaml_files "${dir}")

  [[ "${assert_match}" != "true" || "${count}" -gt 0 ]] \
    || die "No manifest matched target ${TARGET} name ${RESOURCE_NAME:-<all>}"
}

# Delete every YAML file in dir. Pass assert_match=true for selective ops.
delete_directory() {
  local del_fn="$1" dir="$2" assert_match="${3:-false}"
  local file count=0

  while IFS= read -r file; do
    [[ -z "${file}" ]] && continue
    count=$((count + 1))
    "${del_fn}" "${file}"
  done < <(selected_or_all_yaml_files "${dir}")

  [[ "${assert_match}" != "true" || "${count}" -gt 0 ]] \
    || die "No manifest matched target ${TARGET} name ${RESOURCE_NAME:-<all>}"
}

# Apply or plan knowledge files with the same semantics as apply_directory.
apply_knowledge_files() {
  local assert_match="${1:-false}" directory="${CONFIG_DIR}/knowledge/files"
  local file count=0

  if [[ ! -d "${directory}" && -z "${RESOURCE_FILE}" ]]; then
    [[ "${assert_match}" != "true" ]] || die "Knowledge directory not found: ${directory}"
    return 0
  fi

  while IFS= read -r file; do
    [[ -z "${file}" ]] && continue
    count=$((count + 1))
    if [[ "${COMMAND}" == "apply" ]]; then
      run_apply_step "knowledge-files: ${file}" upload_knowledge_file "${file}"
    else
      upload_knowledge_file "${file}"
    fi
  done < <(selected_or_all_knowledge_files)

  [[ "${assert_match}" != "true" || "${count}" -gt 0 ]] \
    || die "No knowledge file matched target ${TARGET} name ${RESOURCE_NAME:-<all>}"
}

# Delete knowledge files, optionally asserting at least one match.
delete_knowledge_files() {
  local assert_match="${1:-false}" directory="${CONFIG_DIR}/knowledge/files"
  local file count=0

  [[ -d "${directory}" || -n "${RESOURCE_FILE}" ]] || return 0

  while IFS= read -r file; do
    [[ -z "${file}" ]] && continue
    count=$((count + 1))
    delete_knowledge_file "${file}"
  done < <(selected_or_all_knowledge_files)

  [[ "${assert_match}" != "true" || "${count}" -gt 0 ]] \
    || die "No knowledge file matched target ${TARGET} name ${RESOURCE_NAME:-<all>}"
}

# ── 12. Command implementations ───────────────────────────────────────────────

validate_config() {
  local file count=0
  require_local_dependencies
  load_env_file
  [[ -d "${CONFIG_DIR}" ]] || die "Configuration directory not found: ${CONFIG_DIR}"
  normalize_selection

  if selection_requested; then
    if [[ "${TARGET}" == "knowledge-files" ]]; then
      [[ -n "${RESOURCE_FILE}" && -f "${RESOURCE_FILE}" ]] \
        && { print_check ok "$(basename "${RESOURCE_FILE}")" ""; print_summary; return; }
      while IFS= read -r file; do
        [[ -z "${file}" ]] && continue
        count=$((count + 1))
      done < <(selected_or_all_knowledge_files)
      [[ "${count}" -gt 0 ]] || die "No knowledge file matched target ${TARGET} name ${RESOURCE_NAME:-<all>}"
      print_check ok "${TARGET}${RESOURCE_NAME:+/${RESOURCE_NAME}}" "${count} file(s)"
      print_summary
      return 0
    fi

    local dir="${T_DIR[${TARGET}]:-incident-platforms}"
    while IFS= read -r file; do
      [[ -z "${file}" ]] && continue
      count=$((count + 1))
      validate_manifest "${file}"
      print_check ok "$(basename "${file}")" ""
    done < <(selected_or_all_yaml_files "${dir}")
    [[ "${count}" -gt 0 ]] || die "No manifest matched target ${TARGET} name ${RESOURCE_NAME:-<all>}"
    print_summary
    return 0
  fi

  print_header "Validating: ${CONFIG_DIR}"
  while IFS= read -r file; do
    [[ -z "${file}" ]] && continue
    count=$((count + 1))
    validate_manifest "${file}"
    print_check ok "${file#"${CONFIG_DIR}/"}" ""
  done < <(find_all_yaml_files)

  if [[ "${count}" -eq 0 ]]; then
    print_check warn "No YAML files found" ""
  fi
  print_summary
}

apply_all_config() {
  [[ "${COMMAND}" == "plan" ]] || ensure_endpoint
  # Pre-fetch the token once in the main shell; all subshells will inherit
  # the _TOKEN_FILE path and avoid repeated az account get-access-token calls.
  [[ "${COMMAND}" == "plan" ]] || _ensure_token

  [[ "${COMMAND}" != "apply" ]] || APPLY_FAILURES=()

  local target
  for target in skills subagents tools common-prompts scheduled-tasks incident-filters \
                connectors repos hooks plugin-configs http-triggers \
                plugin-marketplaces plugin-installations; do
    apply_directory "${T_PUT[$target]}" "${T_DIR[$target]}" "${target}"
  done

  # incident-platforms: ARM PATCH (not in T_PUT — uses a dedicated function).
  apply_directory apply_incident_platform_file "incident-platforms" "incident-platforms"

  # knowledge-files: multipart upload (not a standard YAML PUT).
  apply_knowledge_files

  [[ "${COMMAND}" != "apply" ]] || finish_full_apply
}

apply_selected_config() {
  [[ "${COMMAND}" == "plan" ]] || ensure_endpoint
  [[ "${COMMAND}" == "plan" ]] || _ensure_token

  case "${TARGET}" in
    knowledge-files)    apply_knowledge_files "true" ;;
    incident-platforms) apply_directory apply_incident_platform_file "incident-platforms" "incident-platforms" "true" ;;
    *)                  apply_directory "${T_PUT[$TARGET]}" "${T_DIR[$TARGET]}" "${TARGET}" "true" ;;
  esac
}

apply_config() {
  if [[ "${COMMAND}" == "plan" ]]; then
    require_local_dependencies
  else
    require_azure_dependencies
    require_arm_args
  fi

  load_env_file
  normalize_selection

  if selection_requested; then
    apply_selected_config
  else
    apply_all_config
  fi
}

delete_all_config() {
  ensure_endpoint
  _ensure_token

  # Delete in dependency order: infrastructure types first, then filter/task
  # types that may reference them, and core types (skills, subagents) last.
  local target
  for target in plugin-configs hooks connectors repos; do
    delete_directory "${T_DEL[$target]}" "${T_DIR[$target]}"
  done

  delete_knowledge_files

  # Clear incident platform before removing filters (filters depend on platform).
  local file
  while IFS= read -r file; do
    [[ -z "${file}" ]] && continue
    delete_incident_platform
    break
  done < <(find_yaml_files "${CONFIG_DIR}/incident-platforms")

  for target in incident-filters scheduled-tasks common-prompts tools subagents skills; do
    delete_directory "${T_DEL[$target]}" "${T_DIR[$target]}"
  done
}

delete_selected_config() {
  ensure_endpoint
  _ensure_token

  case "${TARGET}" in
    knowledge-files)    delete_knowledge_files "true" ;;
    incident-platforms)
      # Verify at least one manifest matches, then clear via ARM PATCH.
      local file count=0
      while IFS= read -r file; do
        [[ -z "${file}" ]] && continue
        count=$((count + 1))
      done < <(selected_or_all_yaml_files "incident-platforms")
      [[ "${count}" -gt 0 ]] || die "No manifest matched target ${TARGET} name ${RESOURCE_NAME:-<all>}"
      delete_incident_platform
      ;;
    http-triggers|plugin-marketplaces|plugin-installations)
      die "delete is not implemented for target ${TARGET}; no stable DELETE route is documented in this script."
      ;;
    *)
      delete_directory "${T_DEL[$TARGET]}" "${T_DIR[$TARGET]}" "true"
      ;;
  esac
}

delete_config() {
  [[ "${YES}" == "true" ]] || die "delete requires --yes"
  require_azure_dependencies
  load_env_file
  require_arm_args
  normalize_selection

  if selection_requested; then
    delete_selected_config
  else
    delete_all_config
  fi
}

selected_manifest_name() {
  if [[ -n "${RESOURCE_NAME}" ]]; then
    printf '%s\n' "${RESOURCE_NAME}"
  elif [[ -n "${RESOURCE_FILE}" && "${TARGET}" != "knowledge-files" ]]; then
    manifest_name "${RESOURCE_FILE}"
  else
    printf '\n'
  fi
}

verify_data_target() {
  local endpoint_path="$1" name token
  name="$(selected_manifest_name)"
  token="$(data_plane_token)"

  if [[ -n "${name}" ]]; then
    curl -fsS -H "Authorization: Bearer ${token}" "${ENDPOINT}${endpoint_path}/${name}" | jq '.'
  else
    curl -fsS -H "Authorization: Bearer ${token}" "${ENDPOINT}${endpoint_path}" \
      | jq -r '(.value // . // []) | if type == "array" then .[]?.name // .[]?.metadata?.name // empty else empty end'
  fi
}

verify_data_collection_target() {
  local endpoint_path="$1" name token
  name="$(selected_manifest_name)"
  token="$(data_plane_token)"

  if [[ -n "${name}" ]]; then
    curl -fsS -H "Authorization: Bearer ${token}" "${ENDPOINT}${endpoint_path}" \
      | jq -r --arg name "${name}" \
          '(if type == "object" and has("value") then .value elif type == "array" then . else [] end)
           | .[]? | (.name // .metadata.name // empty) | select(. == $name)'
  else
    curl -fsS -H "Authorization: Bearer ${token}" "${ENDPOINT}${endpoint_path}" \
      | jq -r '(if type == "object" and has("value") then .value elif type == "array" then . else [] end)
               | .[]? | (.name // .metadata.name // empty)'
  fi
}

verify_selected_target() {
  case "${TARGET}" in
    incident-platforms)
      az rest --method GET \
        --url "$(arm_agent_base_url)?api-version=${ARM_API_VERSION}" \
        --query 'properties.incidentManagementConfiguration' \
        --output json | jq '.'
      ;;
    knowledge-files)
      curl -fsS -H "Authorization: Bearer $(data_plane_token)" \
        "${ENDPOINT}/api/v1/agentmemory/status" | jq '.'
      ;;
    tools)
      if [[ -n "${RESOURCE_NAME}" || -n "${RESOURCE_FILE}" ]]; then
        local file
        while IFS= read -r file; do
          [[ -z "${file}" ]] && continue
          if is_manifest_api_preview_blocked "${file}"; then
            log "Skipped API-preview-blocked tool $(manifest_name "${file}")"
            return 0
          fi
        done < <(selected_or_all_yaml_files "tools")
      fi
      verify_data_target "${T_VFY_EP[tools]}"
      ;;
    *)
      case "${T_VFY_MD[$TARGET]:-}" in
        item) verify_data_target             "${T_VFY_EP[$TARGET]}" ;;
        list) verify_data_collection_target  "${T_VFY_EP[$TARGET]}" ;;
        *)    die "No verify implementation for target ${TARGET}" ;;
      esac
      ;;
  esac
}

verify_live() {
  require_azure_dependencies
  require_arm_args
  normalize_selection
  ensure_endpoint

  if selection_requested; then
    verify_selected_target
    return 0
  fi

  _PASS_COUNT=0; _FAIL_COUNT=0; _WARN_COUNT=0

  print_header "Azure SRE Agent — Live Configuration"
  printf "  ${C_DIM}%s  /  %s  /  %s${C_RESET}\n" \
    "${SUBSCRIPTION_ID}" "${RESOURCE_GROUP}" "${AGENT_NAME}"

  # ── ARM: agent state ────────────────────────────────────────────────────────
  print_header "ARM State"
  local arm_json provisioning_state power_state endpoint_val
  if arm_json="$(az rest --method GET \
    --url "$(arm_agent_base_url)?api-version=${ARM_API_VERSION}" \
    --query '{p:properties.provisioningState,s:properties.powerState,e:properties.agentEndpoint}' \
    --output json 2>/dev/null)"; then
    provisioning_state="$(jq -r '.p // "unknown"' <<< "${arm_json}")"
    power_state="$(jq  -r '.s // "unknown"' <<< "${arm_json}")"
    endpoint_val="$(jq  -r '.e // "unknown"' <<< "${arm_json}")"
    [[ "${provisioning_state}" == "Succeeded" ]] \
      && print_check ok   "Provisioning state" "${provisioning_state}" \
      || print_check fail "Provisioning state" "${provisioning_state}"
    [[ "${power_state}" == "Running" ]] \
      && print_check ok   "Power state" "${power_state}" \
      || print_check warn "Power state" "${power_state}"
    print_check ok "Endpoint" "${endpoint_val}"
  else
    print_check fail "ARM GET" "failed — verify --subscription / --resource-group / --agent"
  fi

  local connectors_json connector_names
  if connectors_json="$(az rest --method GET \
    --url "$(arm_agent_base_url)/DataConnectors?api-version=${ARM_API_VERSION}" \
    --output json 2>/dev/null)"; then
    connector_names="$(jq -r '[.value[].name] | join(", ")' <<< "${connectors_json}")"
    [[ -n "${connector_names}" ]] \
      && print_check ok   "DataConnectors" "${connector_names}" \
      || print_check warn "DataConnectors" "(none configured)"
  else
    print_check fail "DataConnectors" "query failed"
  fi

  # ── Data-plane: extended configuration ──────────────────────────────────────
  print_header "Data-Plane Configuration"
  local token
  token="$(data_plane_token)"

  _dp_check() {
    local label="$1" path="$2" names
    if names="$(curl -fsS -H "Authorization: Bearer ${token}" "${ENDPOINT}${path}" 2>/dev/null \
      | jq -r '
          (if type=="object" and has("value") then .value elif type=="array" then . else [] end)
          | map(.name // .metadata.name // empty)
          | map(select(length > 0))
          | if length > 0 then join(", ") else "" end' 2>/dev/null)"; then
      [[ -n "${names}" ]] \
        && print_check ok   "${label}" "${names}" \
        || print_check warn "${label}" "(none)"
    else
      print_check fail "${label}" "request failed"
    fi
  }

  _dp_check "Skills"               /api/v2/extendedAgent/skills
  _dp_check "Subagents"            /api/v2/extendedAgent/agents
  _dp_check "Tools"                /api/v2/extendedAgent/tools
  _dp_check "Common prompts"       /api/v2/extendedAgent/commonprompts
  _dp_check "Scheduled tasks"      /api/v2/extendedAgent/scheduledtasks
  _dp_check "Incident filters"     /api/v2/extendedAgent/incidentFilters
  _dp_check "Connectors"           /api/v2/extendedAgent/connectors
  _dp_check "Hooks"                /api/v2/extendedAgent/hooks
  _dp_check "Plugin configs"       /api/v2/extendedAgent/plugins
  _dp_check "Repos"                /api/v2/repos
  _dp_check "Plugin marketplaces"  /api/v2/plugins/marketplaces
  _dp_check "Plugin installations" /api/v2/plugins/installations
  _dp_check "HTTP triggers"        /api/v1/httptriggers

  # ── Knowledge base ───────────────────────────────────────────────────────────
  print_header "Knowledge Base"
  local kb_json kb_status
  if kb_json="$(curl -fsS -H "Authorization: Bearer ${token}" \
    "${ENDPOINT}/api/v1/agentmemory/status" 2>/dev/null)"; then
    kb_status="$(jq -r '.status // .indexingStatus // "unknown"' <<< "${kb_json}" 2>/dev/null \
      || printf 'unknown')"
    [[ "${kb_status}" =~ ^(Ready|Indexed|Completed)$ ]] \
      && print_check ok   "Status" "${kb_status}" \
      || print_check warn "Status" "${kb_status}"
  else
    print_check warn "Status" "endpoint not available"
  fi

  print_summary
}


# ── 13. Entry point ───────────────────────────────────────────────────────────

main() {
  parse_args "$@"
  resolve_config_dir

  case "${COMMAND}" in
    validate)       validate_config ;;
    plan|apply)     apply_config ;;
    verify)         verify_live ;;
    delete)         delete_config ;;
    prune)          die "prune is intentionally blocked in v1. Export, diff, and explicitly delete reviewed resources instead." ;;
    *)              usage; die "Unknown command: ${COMMAND}" ;;
  esac
}

main "$@"
