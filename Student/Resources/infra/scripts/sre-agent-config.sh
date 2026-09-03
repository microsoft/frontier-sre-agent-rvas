#!/usr/bin/env bash
set -euo pipefail

ARM_API_VERSION="${SRE_AGENT_ARM_API_VERSION:-2026-01-01}"
DATA_PLANE_AUDIENCE="${SRE_AGENT_DATA_PLANE_AUDIENCE:-https://azuresre.dev}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# This script lives at Student/Resources/infra/scripts/, so the Student folder is three
# levels up. The Student Makefile exports the layout contract; direct script execution uses
# the deterministic Student defaults below. Nothing outside the Student folder is read.
STUDENT_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
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

usage() {
  cat <<'USAGE'
Usage: sre-agent-config.sh <command> [options]

Commands:
  validate   Validate local YAML/Markdown configuration.
  plan       Show the API operations that would be executed.
  apply      Apply local configuration to the live Azure SRE Agent.
  verify     Query the live Azure SRE Agent and list configured surfaces.
  delete     Delete local desired-state resources from the live agent. Requires --yes.

Options:
  --subscription ID       Azure subscription ID.
  --resource-group NAME   Resource group that contains the Azure SRE Agent.
  --agent NAME            Azure SRE Agent resource name.
  --endpoint URL          Data-plane endpoint. If omitted, the script reads it from ARM.
  --config PATH           Configuration directory. Overrides layout auto-discovery.
  --target TARGET         Limit validate, plan, apply, verify, or delete to one configuration target.
  --name NAME             Limit the selected target to one manifest name.
  --file PATH             Limit the selected target to one YAML manifest or knowledge file.
  --env-file PATH         Override the default root .env file used for placeholder substitution.
  --yes                   Confirm destructive delete operations.
  -h, --help              Show help.

Examples:
  make config-sre-agent
  make config-sre-agent CONFIG_TARGET=skills CONFIG_NAME=source-fix-delivery

The same operations, driving this script directly:
  Resources/infra/scripts/sre-agent-config.sh validate
  Resources/infra/scripts/sre-agent-config.sh plan --subscription <sub> --resource-group <rg> --agent <agent>
  Resources/infra/scripts/sre-agent-config.sh apply --subscription <sub> --resource-group <rg> --agent <agent>
  Resources/infra/scripts/sre-agent-config.sh verify --target skills --name source-fix-delivery --subscription <sub> --resource-group <rg> --agent <agent>
  Resources/infra/scripts/sre-agent-config.sh delete --target skills --name source-fix-delivery --subscription <sub> --resource-group <rg> --agent <agent> --yes
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

repo_path() {
  local value="$1"
  if [[ "${value}" = /* ]]; then
    printf '%s\n' "${value}"
  else
    printf '%s/%s\n' "${STUDENT_ROOT}" "${value}"
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
  local candidate=""
  local discovered
  local source="auto-discovery"
  local checked=()

  if [[ "${CONFIG_DIR_EXPLICIT}" == "true" ]]; then
    candidate="${CONFIG_DIR}"
    source="--config"
  elif [[ -n "${SRE_AGENT_CONFIG_DIR:-}" ]]; then
    candidate="$(repo_path "${SRE_AGENT_CONFIG_DIR}")"
    source="SRE_AGENT_CONFIG_DIR"
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
    "${STUDENT_ROOT}/Resources/azure-sre-agent-config" \
    "${STUDENT_ROOT}/configuration"; do
    checked+=("${candidate}")
    if discovered="$(canonical_dir "${candidate}")" && config_dir_has_expected_shape "${discovered}"; then
      CONFIG_DIR="${discovered}"
      return 0
    fi
  done

  printf 'ERROR: Could not resolve Azure SRE Agent configuration directory.\n' >&2
  printf 'Checked:\n' >&2
  printf '  - %s\n' "${checked[@]}" >&2
  printf 'Set --config or SRE_AGENT_CONFIG_DIR.\n' >&2
  exit 1
}

log() {
  printf '%s\n' "$*"
}

die() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

record_apply_failure() {
  local label="$1"
  local exit_code="$2"
  APPLY_FAILURES+=("${label} (exit ${exit_code})")
  printf 'ERROR: %s failed with exit code %s; continuing full apply.\n' "${label}" "${exit_code}" >&2
}

run_apply_step() {
  local label="$1"
  local exit_code
  shift

  set +e
  ( set -e; "$@" )
  exit_code="$?"
  set -e

  if [[ "${exit_code}" -eq 0 ]]; then
    return 0
  fi

  record_apply_failure "${label}" "${exit_code}"
  return 0
}

finish_full_apply() {
  local failure

  [[ "${#APPLY_FAILURES[@]}" -eq 0 ]] && return 0

  printf '\nERROR: Full desired-state apply completed with %s failure(s):\n' "${#APPLY_FAILURES[@]}" >&2
  for failure in "${APPLY_FAILURES[@]}"; do
    printf '  - %s\n' "${failure}" >&2
  done

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
  local line key value env_file_mode

  if [[ -z "${ENV_FILE}" && -f "${STUDENT_ROOT}/.env" ]]; then
    ENV_FILE="${STUDENT_ROOT}/.env"
  fi

  [[ -z "${ENV_FILE}" ]] && return 0
  [[ -f "${ENV_FILE}" ]] || die "Environment file not found: ${ENV_FILE}"

  env_file_mode="$(stat -c '%a' "${ENV_FILE}")"
  [[ "${env_file_mode}" =~ ^[0-7]?00$ ]] || die "Environment file ${ENV_FILE} has mode ${env_file_mode}; run: chmod 600 ${ENV_FILE}"

  while IFS= read -r line || [[ -n "${line}" ]]; do
    line="${line%$'\r'}"
    line="$(trim_space "${line}")"
    [[ -z "${line}" || "${line}" == \#* ]] && continue

    if [[ "${line}" == export[[:space:]]* ]]; then
      line="$(trim_space "${line#export}")"
    fi

    [[ "${line}" =~ ^[A-Za-z_][A-Za-z0-9_]*= ]] || die "Invalid environment assignment in ${ENV_FILE}"
    key="${line%%=*}"
    value="$(trim_space "${line#*=}")"
    value="$(strip_optional_quotes "${value}")"
    printf -v "${key}" '%s' "${value}"
    export "${key?}"
  done < "${ENV_FILE}"
}

parse_args() {
  [[ $# -eq 0 ]] && { usage; exit 1; }
  # Asking for help must never require a resolvable configuration directory or Azure
  # credentials, so the help flag is handled before any other argument is interpreted.
  [[ "$1" == "-h" || "$1" == "--help" ]] && { usage; exit 0; }
  COMMAND="$1"
  shift

  while [[ $# -gt 0 ]]; do
    case "$1" in
      --subscription)
        SUBSCRIPTION_ID="${2:-}"
        shift 2
        ;;
      --resource-group)
        RESOURCE_GROUP="${2:-}"
        shift 2
        ;;
      --agent)
        AGENT_NAME="${2:-}"
        shift 2
        ;;
      --endpoint)
        ENDPOINT="${2:-}"
        shift 2
        ;;
      --config)
        [[ -n "${2:-}" ]] || die "--config requires a path"
        CONFIG_DIR="$(repo_path "${2}")"
        CONFIG_DIR_EXPLICIT="true"
        shift 2
        ;;
      --target)
        TARGET="${2:-}"
        shift 2
        ;;
      --name)
        RESOURCE_NAME="${2:-}"
        shift 2
        ;;
      --file)
        [[ -n "${2:-}" ]] || die "--file requires a path"
        if [[ "${2}" = /* ]]; then
          RESOURCE_FILE="${2}"
        else
          RESOURCE_FILE="$(cd "$(dirname "${2}")" && pwd)/$(basename "${2}")"
        fi
        shift 2
        ;;
      --env-file)
        ENV_FILE="${2:-}"
        shift 2
        ;;
      --yes)
        YES="true"
        shift
        ;;
      -h|--help)
        usage
        exit 0
        ;;
      *)
        die "Unknown option: $1"
        ;;
    esac
  done
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

yaml_to_json() {
  if command -v python3 >/dev/null 2>&1 && python3 -c 'import yaml, json' >/dev/null 2>&1; then
    python3 -c 'import json, sys, yaml; print(json.dumps(yaml.safe_load(sys.stdin.read())))'
  else
    yq -o=json '.' -
  fi
}

require_arm_args() {
  [[ -n "${SUBSCRIPTION_ID}" ]] || die "--subscription is required"
  [[ -n "${RESOURCE_GROUP}" ]] || die "--resource-group is required"
  [[ -n "${AGENT_NAME}" ]] || die "--agent is required"
}

find_yaml_files() {
  local directory="$1"
  [[ -d "${directory}" ]] || return 0
  # example-* manifests are kept in Git as templates but never deployed.
  find "${directory}" -maxdepth 1 -type f \( -name '*.yaml' -o -name '*.yml' \) ! -name 'example-*' | sort
}

find_all_yaml_files() {
  [[ -d "${CONFIG_DIR}" ]] || die "Configuration directory not found: ${CONFIG_DIR}"
  # example-* manifests are kept in Git as templates but never deployed.
  find "${CONFIG_DIR}" -type f \( -name '*.yaml' -o -name '*.yml' \) ! -name 'example-*' | sort
}

find_knowledge_files() {
  local directory="$1"
  local ignore_file="${CONFIG_DIR}/knowledge/.knowledgeignore"
  local file relative_path
  [[ -d "${directory}" ]] || return 0
  while IFS= read -r file; do
    relative_path="${file#${directory}/}"
    if [[ -f "${ignore_file}" ]] && grep -Fqx "${relative_path}" "${ignore_file}"; then
      continue
    fi
    printf '%s\n' "${file}"
  done < <(find "${directory}" -type f ! -name 'example-*' | sort)
}

validate_knowledge_exclusions() {
  local directory="${CONFIG_DIR}/knowledge/files"
  local ignore_file="${CONFIG_DIR}/knowledge/.knowledgeignore"
  local line

  [[ -f "${ignore_file}" ]] || return 0
  while IFS= read -r line || [[ -n "${line}" ]]; do
    line="${line%$'\r'}"
    line="$(trim_space "${line}")"
    [[ -z "${line}" || "${line}" == \#* ]] && continue
    [[ -f "${directory}/${line}" ]] || die "Knowledge exclusion references a missing file: ${line}"
  done < "${ignore_file}"
}

selection_requested() {
  [[ -n "${TARGET}" || -n "${RESOURCE_NAME}" || -n "${RESOURCE_FILE}" ]]
}

validate_target() {
  case "$1" in
    skills|subagents|tools|common-prompts|scheduled-tasks|incident-filters|connectors|repos|hooks|plugin-configs|http-triggers|plugin-marketplaces|plugin-installations|knowledge-files|custom-instructions)
      ;;
    *)
      die "Unknown target: $1"
      ;;
  esac
}

infer_target_from_file() {
  local file="$1"
  local relative_path=""

  if [[ "${file}" = "${CONFIG_DIR}/"* ]]; then
    relative_path="${file#"${CONFIG_DIR}/"}"
  fi

  [[ -n "${relative_path}" ]] || return 0

  case "${relative_path}" in
    skills/*.yaml|skills/*.yml)
      printf 'skills\n'
      ;;
    subagents/*.yaml|subagents/*.yml)
      printf 'subagents\n'
      ;;
    tools/*.yaml|tools/*.yml)
      printf 'tools\n'
      ;;
    common-prompts/*.yaml|common-prompts/*.yml)
      printf 'common-prompts\n'
      ;;
    automations/scheduled-tasks/*.yaml|automations/scheduled-tasks/*.yml)
      printf 'scheduled-tasks\n'
      ;;
    automations/incident-filters/*.yaml|automations/incident-filters/*.yml)
      printf 'incident-filters\n'
      ;;
    connectors/*.yaml|connectors/*.yml)
      printf 'connectors\n'
      ;;
    repos/*.yaml|repos/*.yml)
      printf 'repos\n'
      ;;
    hooks/*.yaml|hooks/*.yml)
      printf 'hooks\n'
      ;;
    plugin-configs/*.yaml|plugin-configs/*.yml)
      printf 'plugin-configs\n'
      ;;
    automations/http-triggers/*.yaml|automations/http-triggers/*.yml)
      printf 'http-triggers\n'
      ;;
    plugins/marketplaces/*.yaml|plugins/marketplaces/*.yml)
      printf 'plugin-marketplaces\n'
      ;;
    plugins/installations/*.yaml|plugins/installations/*.yml)
      printf 'plugin-installations\n'
      ;;
    knowledge/files/*)
      printf 'knowledge-files\n'
      ;;
    custom-instructions.md)
      printf 'custom-instructions\n'
      ;;
  esac
}

normalize_selection() {
  local inferred_target=""
  local file_name=""

  selection_requested || return 0

  [[ -n "${RESOURCE_NAME}" || -n "${TARGET}" || -n "${RESOURCE_FILE}" ]] || return 0
  [[ -n "${RESOURCE_NAME}" && -z "${TARGET}" && -z "${RESOURCE_FILE}" ]] && die "--name requires --target or --file"

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
      [[ "${file_name}" == "${RESOURCE_NAME}" || "${file_name%.*}" == "${RESOURCE_NAME}" ]] || die "--file ${RESOURCE_FILE} does not match --name ${RESOURCE_NAME}"
    else
      file_name="$(manifest_name "${RESOURCE_FILE}")"
      [[ "${file_name}" == "${RESOURCE_NAME}" ]] || die "--file manifest name ${file_name} does not match --name ${RESOURCE_NAME}"
    fi
  fi
}

placeholders_in_file() {
  local file="$1"
  grep -Eo '\$\{[A-Za-z_][A-Za-z0-9_]*\}' "${file}" 2>/dev/null | sort -u || true
}

validate_placeholders() {
  local file="$1"
  local placeholder variable
  while IFS= read -r placeholder; do
    [[ -z "${placeholder}" ]] && continue
    variable="${placeholder#\$\{}"
    variable="${variable%\}}"
    # A variable that is exported but deliberately empty is a valid configuration choice:
    # the Berlin parking MCP connector, for example, documents an empty authorisation token
    # as the way to keep authentication disabled in the lab. Only a variable that was never
    # declared at all is an operator mistake, so only that case fails the validation.
    [[ -n "${!variable+declared}" ]] || die "${file} references ${placeholder}, but ${variable} is not set"
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
  local json content_file content_path content_json base_dir
  json="$(render_yaml_to_json "${file}")" || return $?
  base_dir="$(cd "$(dirname "${file}")" && pwd)"

  # Official authoring shape (sre.azure.com/docs/concepts/skills): `files:` is a list whose
  # first entry is the SKILL.md body and whose remaining entries are supporting files.
  if [[ "$(jq -r '(.spec.files // empty) | type' <<< "${json}")" == "array" ]]; then
    local entries first extra_json entry entry_path
    mapfile -t entries < <(jq -r '.spec.files[]' <<< "${json}")
    [[ "${#entries[@]}" -gt 0 ]] || die "spec.files is empty in ${file}; declare the SKILL.md body as the first entry."
    first="${entries[0]}"
    [[ "${first}" = /* ]] && content_path="${first}" || content_path="${base_dir}/${first}"
    [[ -f "${content_path}" ]] || die "Skill body file not found: ${content_path}"
    content_json="$(render_text_file "${content_path}" | jq -Rs '.')" || return $?
    extra_json='[]'
    for entry in "${entries[@]:1}"; do
      [[ "${entry}" = /* ]] && entry_path="${entry}" || entry_path="${base_dir}/${entry}"
      [[ -f "${entry_path}" ]] || die "Skill supporting file not found: ${entry_path}"
      # The service keys supporting files by filePath and preserves subdirectories.
      extra_json="$(jq -c --arg p "${entry#./}" \
        --rawfile body "${entry_path}" '. + [{filePath: $p, content: $body}]' <<< "${extra_json}")"
    done
    jq --argjson content "${content_json}" --argjson extra "${extra_json}" \
      '.spec.content = $content | .spec.additionalFiles = $extra | del(.spec.files)' <<< "${json}"
    return 0
  fi

  content_file="$(jq -r '.spec.content_file // empty' <<< "${json}")"
  [[ -z "${content_file}" ]] && { printf '%s\n' "${json}"; return 0; }

  if [[ "${content_file}" = /* ]]; then
    content_path="${content_file}"
  else
    content_path="${base_dir}/${content_file}"
  fi

  [[ -f "${content_path}" ]] || die "Content file not found: ${content_path}"
  content_json="$(render_text_file "${content_path}" | jq -Rs '.')" || return $?
  jq --argjson content "${content_json}" '.spec.content = $content | del(.spec.content_file)' <<< "${json}"
}

manifest_raw_name() {
  local file="$1"
  local json name
  json="$(yaml_to_json < "${file}")" || return $?
  name="$(jq -r '.metadata.name // .spec.name // .name // empty' <<< "${json}")"
  [[ -n "${name}" ]] || die "Manifest has no metadata.name, spec.name, or name: ${file}"
  printf '%s\n' "${name}"
}

manifest_raw_kind() {
  local file="$1"
  local kind
  kind="$(yaml_to_json < "${file}" | jq -r '.kind // empty')"
  [[ -n "${kind}" ]] || die "Manifest has no kind: ${file}"
  printf '%s\n' "${kind}"
}

manifest_name() {
  local file="$1"
  local json name
  json="$(manifest_json "${file}")" || return $?
  name="$(jq -r '.metadata.name // .spec.name // .name // empty' <<< "${json}")"
  [[ -n "${name}" ]] || die "Manifest has no metadata.name, spec.name, or name: ${file}"
  printf '%s\n' "${name}"
}

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

data_plane_token() {
  az account get-access-token --resource "${DATA_PLANE_AUDIENCE}" --query accessToken --output tsv
}

connector_properties() {
  local file="$1"
  local properties
  properties="$(manifest_json "${file}" | jq -c '.spec.properties // .properties // {}')"

  jq -c '
    (.extendedProperties.headers.Authorization? // "") as $authorization
    | if ($authorization | test("^Bearer[[:space:]]*$"; "i")) then
        del(.extendedProperties.headers.Authorization)
        | if ((.extendedProperties.headers // {}) | length) == 0 then
            del(.extendedProperties.headers, .extendedProperties.authType)
          else . end
      else . end
  ' <<< "${properties}"
}

arm_put_connector() {
  local file="$1"
  local name properties body body_file response request_status
  local expected_endpoint stored_endpoint provisioning_state
  validate_manifest "${file}"
  name="$(manifest_name "${file}")"
  properties="$(connector_properties "${file}")"
  body="$(jq -c '{properties:.}' <<< "${properties}")"

  if [[ "${COMMAND}" == "plan" ]]; then
    log "PUT ARM connector ${name} from ${file}"
    return 0
  fi

  body_file="$(mktemp)"
  chmod 600 "${body_file}"
  printf '%s' "${body}" > "${body_file}"
  if response="$(az rest --method PUT \
    --url "$(arm_agent_base_url)/connectors/${name}?api-version=${ARM_API_VERSION}" \
    --headers 'Content-Type=application/json' \
    --body "@${body_file}" \
    --output json)"; then
    rm -f "${body_file}"
  else
    request_status="$?"
    rm -f "${body_file}"
    return "${request_status}"
  fi
  expected_endpoint="$(jq -r '.endpoint // empty' <<< "${properties}")"
  stored_endpoint="$(jq -r '.properties.endpoint // empty' <<< "${response}")"
  provisioning_state="$(jq -r '.properties.provisioningState // empty' <<< "${response}")"

  [[ "${provisioning_state}" != "Failed" ]] || die "ARM connector ${name} provisioning failed"
  [[ -z "${expected_endpoint}" || "${stored_endpoint}" == "${expected_endpoint}" ]] || \
    die "ARM connector ${name} did not persist the requested endpoint"
  log "Applied ARM connector ${name}"
}

data_put_connector_v2() {
  local file="$1" name json api_name display_name connection_name description
  local approval_tools token connection_url server_url connection_json server_json
  local connection_status server_state connection_body server_body

  validate_manifest "${file}"
  name="$(manifest_name "${file}")"
  json="$(manifest_json "${file}")"
  api_name="$(jq -r '.spec.apiName // empty' <<< "${json}")"
  display_name="$(jq -r '.spec.displayName // .metadata.name' <<< "${json}")"
  connection_name="$(jq -r '.spec.connectionName // .metadata.name' <<< "${json}")"
  description="$(jq -r '.spec.description // ""' <<< "${json}")"
  approval_tools="$(jq -c '.spec.requireApprovalTools // []' <<< "${json}")"
  [[ -n "${api_name}" ]] || die "ConnectorV2 ${name} is missing spec.apiName"

  if [[ "${COMMAND}" == "plan" ]]; then
    log "ENSURE connectorV2 connection ${connection_name} (${api_name}) from ${file}"
    log "ENSURE connectorV2 MCP server ${name} from ${file}"
    return 0
  fi

  token="$(data_plane_token)"
  connection_url="${ENDPOINT}/api/v2/connectorV2/connections/${connection_name}"
  server_url="${ENDPOINT}/api/v2/connectorV2/mcpservers/${name}"
  connection_json="$(curl -sS -H "Authorization: Bearer ${token}" "${connection_url}" || true)"
  server_json="$(curl -sS -H "Authorization: Bearer ${token}" "${server_url}" || true)"
  connection_status="$(jq -r '.properties.overallStatus // empty' <<< "${connection_json}" 2>/dev/null || true)"
  server_state="$(jq -r '.properties.state // empty' <<< "${server_json}" 2>/dev/null || true)"

  if [[ "${connection_status}" == "Connected" && "${server_state}" == "Enabled" ]]; then
    log "Preserved connected connectorV2 ${name}"
    return 0
  fi

  if [[ -n "${connection_status}" || -n "${server_state}" ]]; then
    log "Preserved connectorV2 ${name}; current connection status is ${connection_status:-NotFound} and OAuth consent or reauthorization is required"
  fi

  connection_body="$(jq -nc --arg displayName "${display_name}" --arg connectorName "${api_name}" \
    '{displayName:$displayName,connectorName:$connectorName}')"
  server_body="$(jq -nc --arg description "${description}" --arg connectionName "${connection_name}" \
    --arg apiName "${api_name}" --argjson approvalTools "${approval_tools}" '
      {properties:{description:$description,connectors:[{name:$apiName,connectionName:$connectionName}]}}
      + if ($approvalTools | length) > 0
        then {runtimeMcpConfiguration:{requireApprovalTools:$approvalTools}}
        else {}
        end')"

  if [[ -z "${connection_status}" ]]; then
    curl -fsS -X PUT -H "Authorization: Bearer ${token}" -H 'Content-Type: application/json' \
      --data "${connection_body}" "${connection_url}" >/dev/null
    log "Created connectorV2 connection ${connection_name}; OAuth consent is required"
  fi

  if [[ -z "${server_state}" ]]; then
    curl -fsS -X PUT -H "Authorization: Bearer ${token}" -H 'Content-Type: application/json' \
      --data "${server_body}" "${server_url}" >/dev/null
    log "Created connectorV2 MCP server ${name}"
  fi
}

connector_v2_status_json() {
  local file="$1" name json connection_name token
  name="$(manifest_raw_name "${file}")"
  json="$(yaml_to_json < "${file}")"
  connection_name="$(jq -r '.spec.connectionName // .metadata.name' <<< "${json}")"
  token="$(data_plane_token)"
  jq -nc \
    --arg name "${name}" \
    --argjson connection "$(curl -sS -H "Authorization: Bearer ${token}" \
      "${ENDPOINT}/api/v2/connectorV2/connections/${connection_name}" 2>/dev/null || printf '{}')" \
    --argjson server "$(curl -sS -H "Authorization: Bearer ${token}" \
      "${ENDPOINT}/api/v2/connectorV2/mcpservers/${name}" 2>/dev/null || printf '{}')" \
    '{name:$name,
      connectionStatus:($connection.properties.overallStatus // "NotFound"),
      mcpServerState:($server.properties.state // "NotFound")}'
}

verify_connector_v2_manifests() {
  local file kind status failures=0
  [[ -d "${CONFIG_DIR}/connectors" ]] || return 0
  log "ConnectorV2 OAuth status:"
  while IFS= read -r file; do
    [[ -z "${file}" ]] && continue
    kind="$(manifest_raw_kind "${file}")"
    [[ "${kind}" == "ConnectorV2" ]] || continue
    status="$(connector_v2_status_json "${file}")"
    jq -c '.' <<< "${status}"
    if [[ "$(jq -r '.connectionStatus' <<< "${status}")" != "Connected" ]] || \
      [[ "$(jq -r '.mcpServerState' <<< "${status}")" != "Enabled" ]]; then
      printf 'ERROR: ConnectorV2 %s requires OAuth consent or reauthorization.\n' \
        "$(jq -r '.name' <<< "${status}")" >&2
      failures=$((failures + 1))
    fi
  done < <(if selection_requested; then selected_yaml_files "connectors"; else find_yaml_files "${CONFIG_DIR}/connectors"; fi)
  [[ "${failures}" -eq 0 ]] || return 1
}

verify_agent_connector_manifest() {
  local file="$1"
  local name connector token result
  name="$(manifest_raw_name "${file}")"
  connector="$(az rest --method POST \
    --url "$(arm_agent_base_url)/connectors/${name}/listSecrets?api-version=${ARM_API_VERSION}" \
    --output json)"
  token="$(data_plane_token)"
  result="$(printf '%s' "${connector}" | curl -fsS -X POST \
    -H "Authorization: Bearer ${token}" \
    -H 'Content-Type: application/json' \
    --data-binary @- \
    "${ENDPOINT}/api/v2/extendedAgent/connectors/${name}/testconnection")"

  jq -c '{connectorName,success,totalCount,errorMessage,responseTimeMs}' <<< "${result}"
  [[ "$(jq -r '.success // false' <<< "${result}")" == "true" ]] || \
    die "Connector ${name} failed its live connection test"
}

verify_agent_connector_manifests() {
  local file kind
  log "AgentConnector live connection tests:"

  if selection_requested; then
    while IFS= read -r file; do
      [[ -z "${file}" ]] && continue
      kind="$(manifest_raw_kind "${file}")"
      [[ "${kind}" == "AgentConnector" ]] || continue
      verify_agent_connector_manifest "${file}"
    done < <(selected_yaml_files "connectors")
    return 0
  fi

  while IFS= read -r file; do
    [[ -z "${file}" ]] && continue
    kind="$(manifest_raw_kind "${file}")"
    [[ "${kind}" == "AgentConnector" ]] || continue
    verify_agent_connector_manifest "${file}"
  done < <(find_yaml_files "${CONFIG_DIR}/connectors")
}

data_put_manifest() {
  local endpoint_path="$1"
  local file="$2"
  local name json body token url kind
  if [[ "${endpoint_path}" == "/api/v2/extendedAgent/connectors" ]]; then
    kind="$(manifest_json "${file}" | jq -r '.kind // empty')"
    if [[ "${kind}" == "ConnectorV2" ]]; then
      data_put_connector_v2 "${file}"
      return 0
    fi
    if [[ "${kind}" == "AgentConnector" ]]; then
      arm_put_connector "${file}"
      return 0
    fi
  fi
  validate_manifest "${file}"
  name="$(manifest_name "${file}")"
  json="$(manifest_json "${file}")"
  body="$(jq --arg name "${name}" 'if (.api_version? or .metadata? or .spec? or .kind?) then {name:$name,type:(.kind // "Configuration"),tags:(.tags // []),properties:(.spec.properties // .spec // .properties // {})} else . end' <<< "${json}")"

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
  local endpoint_kind="$1"
  local resource_type="$2"
  local file="$3"
  local props="$4"
  # Optional resilience: max_attempts defaults to 1 (single try, fail-fast) so
  # every existing caller keeps its current behavior. Callers that race an
  # asynchronous prerequisite (for example incidentFilters after the AzMonitor
  # platform PATCH) pass max_attempts>1 to retry transient non-2xx responses.
  local max_attempts="${5:-1}"
  local retry_sleep="${6:-10}"
  local name body token url attempt http_code
  validate_manifest "${file}"
  name="$(manifest_name "${file}")"
  body="$(jq -n \
    --arg name "${name}" \
    --arg type "${resource_type}" \
    --argjson props "${props}" \
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

skill_properties() {
  local file="$1"
  local json name
  json="$(manifest_json "${file}")"
  name="$(manifest_name "${file}")"
  jq -c --arg name "${name}" '
    {
      name: $name,
      description: (.metadata.description // .spec.description // ""),
      tools: (.metadata.spec.tools // .spec.tools // []),
      skillContent: (.skillContent // .spec.skillContent // .spec.content // ""),
      additionalFiles: (.additionalFiles // .spec.additionalFiles // [])
    }
  ' <<< "${json}"
}

subagent_properties() {
  local file="$1"
  local json
  json="$(manifest_json "${file}")"
  jq -c '
    .spec as $spec |
    {
      description: ($spec.description // ""),
      instructions: ($spec.instructions // $spec.system_prompt // $spec.content // ""),
      handoffDescription: ($spec.handoffDescription // $spec.handoff_description // ""),
      handoffs: ($spec.handoffs // []),
      tools: ($spec.tools // []),
      temperature: ($spec.temperature // 0.2),
      enableSkills: ($spec.enableSkills // $spec.enable_skills // false),
      allowedSkills: ($spec.allowedSkills // $spec.allowed_skills // []),
      mcpTools: ($spec.mcpTools // $spec.mcp_tools // [])
    }
  ' <<< "${json}"
}

tool_properties() {
  local file="$1"
  manifest_json "${file}" | jq -c '.spec // .properties // {}'
}

manifest_deployment_status() {
  local file="$1"
  manifest_json "${file}" | jq -r '.spec.deployment.status // .deployment.status // empty'
}

is_manifest_api_preview_blocked() {
  local file="$1"
  [[ "$(manifest_deployment_status "${file}")" == "api-preview-blocked" ]]
}

common_prompt_properties() {
  local file="$1"
  manifest_json "${file}" | jq -c '
    .spec as $spec |
    {
      description: ($spec.description // ""),
      prompt: ($spec.prompt // $spec.content // "")
    }
  '
}

scheduled_task_properties() {
  local file="$1"
  local json name
  json="$(manifest_json "${file}")"
  name="$(manifest_name "${file}")"
  jq -c --arg name "${name}" '
    .spec as $spec |
    {
      name: ($spec.name // $name),
      description: ($spec.description // ""),
      cronExpression: ($spec.cronExpression // $spec.schedule // ""),
      agentPrompt: ($spec.agentPrompt // $spec.prompt // ""),
      agentMode: ($spec.agentMode // $spec.mode // "Review"),
      isEnabled: (if ($spec|has("isEnabled")) then $spec.isEnabled elif ($spec|has("enabled")) then $spec.enabled else true end),
      timeZone: ($spec.timeZone // $spec.time_zone // "UTC")
    }
    | if (($spec.agent // "") == "") then . else . + {agent: $spec.agent} end
  ' <<< "${json}"
}

incident_filter_properties() {
  local file="$1"
  manifest_json "${file}" | jq -c '
    .spec as $spec |
    $spec + {
      incidentPlatform: ($spec.incidentPlatform // $spec.platformType // "AzMonitor"),
      handlingAgent: ($spec.handlingAgent // $spec.action.run_skill // "default"),
      isEnabled: (if ($spec|has("isEnabled")) then $spec.isEnabled elif ($spec|has("enabled")) then $spec.enabled else false end)
    }
  '
}

data_put_skill() {
  local file="$1"
  validate_manifest "${file}"
  data_put_extended "skills" "Skill" "${file}" "$(skill_properties "${file}")"
}

data_put_subagent() {
  local file="$1"
  validate_manifest "${file}"
  data_put_extended "agents" "ExtendedAgent" "${file}" "$(subagent_properties "${file}")"
}

data_put_tool() {
  local file="$1"
  if is_manifest_api_preview_blocked "${file}"; then
    log "Skipped API-preview-blocked tool $(manifest_name "${file}")"
    return 0
  fi
  validate_manifest "${file}"
  data_put_extended "tools" "Tool" "${file}" "$(tool_properties "${file}")"
}

delete_tools_selected() {
  local file count=0
  while IFS= read -r file; do
    [[ -z "${file}" ]] && continue
    count=$((count + 1))
    if is_manifest_api_preview_blocked "${file}"; then
      log "Skipped API-preview-blocked tool $(manifest_name "${file}")"
      continue
    fi
    data_delete_manifest "/api/v2/extendedAgent/tools" "${file}"
  done < <(selected_yaml_files "tools")

  [[ "${count}" -gt 0 ]] || die "No manifest matched target ${TARGET} name ${RESOURCE_NAME:-<all>}"
}

delete_tools() {
  local file
  while IFS= read -r file; do
    [[ -z "${file}" ]] && continue
    if is_manifest_api_preview_blocked "${file}"; then
      log "Skipped API-preview-blocked tool $(manifest_name "${file}")"
      continue
    fi
    data_delete_manifest "/api/v2/extendedAgent/tools" "${file}"
  done < <(find_yaml_files "${CONFIG_DIR}/tools")
}

data_put_common_prompt() {
  local file="$1"
  validate_manifest "${file}"
  data_put_extended "commonprompts" "CommonPrompt" "${file}" "$(common_prompt_properties "${file}")"
}

data_put_scheduled_task() {
  local file="$1"
  validate_manifest "${file}"
  data_put_extended "scheduledtasks" "ScheduledTask" "${file}" "$(scheduled_task_properties "${file}")"
}

data_put_incident_filter() {
  local file="$1"
  validate_manifest "${file}"
  # The Terraform-owned AzMonitor platform can still be reconciling when the first filter PUT
  # runs, returning HTTP 400. Retry with a wait to absorb that propagation delay.
  data_put_extended "incidentFilters" "IncidentFilter" "${file}" "$(incident_filter_properties "${file}")" \
    "${SRE_AGENT_INCIDENT_FILTER_MAX_ATTEMPTS:-5}" "${SRE_AGENT_INCIDENT_FILTER_RETRY_SLEEP:-10}"
}

hook_properties() {
  local file="$1"
  manifest_json "${file}" | jq -c '.spec // .properties // {}'
}

data_put_hook() {
  local file="$1"
  validate_manifest "${file}"
  data_put_extended "hooks" "GlobalHook" "${file}" "$(hook_properties "${file}")"
}

data_post_manifest() {
  local endpoint_path="$1"
  local file="$2"
  local name json body token url
  validate_manifest "${file}"
  name="$(manifest_name "${file}")"
  json="$(manifest_json "${file}")"
  if [[ "${endpoint_path}" == "/api/v1/httptriggers/create" ]]; then
    body="$(jq -c --arg name "${name}" 'if (.api_version? or .metadata? or .spec? or .kind?) then ({name:$name} + (.spec // .properties // {})) else . end' <<< "${json}")"
  else
    body="$(jq -c --arg name "${name}" 'if (.api_version? or .metadata? or .spec? or .kind?) then {metadata:{name:$name},spec:(.spec // .properties // {})} else . end' <<< "${json}")"
  fi

  if [[ "${COMMAND}" == "plan" ]]; then
    log "POST data-plane ${endpoint_path} for ${name} from ${file}"
  else
    token="$(data_plane_token)"
    url="${ENDPOINT}${endpoint_path}"
    if [[ "${endpoint_path}" == "/api/v1/httptriggers/create" ]]; then
      if curl -fsS -H "Authorization: Bearer ${token}" "${ENDPOINT}/api/v1/httptriggers" \
        | jq -e --arg name "${name}" '(if type == "array" then . else (.value // []) end) | any(.[]?; .name == $name)' >/dev/null; then
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

apply_post_directory() {
  local relative_dir="$1"
  local endpoint_path="$2"
  local file
  while IFS= read -r file; do
    [[ -z "${file}" ]] && continue
    data_post_manifest "${endpoint_path}" "${file}"
  done < <(find_yaml_files "${CONFIG_DIR}/${relative_dir}")
}

apply_post_directory_best_effort() {
  local relative_dir="$1"
  local endpoint_path="$2"
  local target_label="$3"
  local file

  while IFS= read -r file; do
    [[ -z "${file}" ]] && continue
    run_apply_step "${target_label}: ${file}" data_post_manifest "${endpoint_path}" "${file}"
  done < <(find_yaml_files "${CONFIG_DIR}/${relative_dir}")
}

selected_yaml_files() {
  local relative_dir="$1"
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
  done < <(find_yaml_files "${CONFIG_DIR}/${relative_dir}")
}

selected_knowledge_files() {
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

apply_post_directory_selected() {
  local relative_dir="$1"
  local endpoint_path="$2"
  local file count=0

  while IFS= read -r file; do
    [[ -z "${file}" ]] && continue
    count=$((count + 1))
    data_post_manifest "${endpoint_path}" "${file}"
  done < <(selected_yaml_files "${relative_dir}")

  [[ "${count}" -gt 0 ]] || die "No manifest matched target ${TARGET} name ${RESOURCE_NAME:-<all>}"
}

data_delete_manifest() {
  local endpoint_path="$1"
  local file="$2"
  local name token url kind
  name="$(manifest_name "${file}")"

  if [[ "${endpoint_path}" == "/api/v2/extendedAgent/connectors" ]]; then
    kind="$(manifest_json "${file}" | jq -r '.kind // empty')"
    if [[ "${kind}" == "AgentConnector" ]]; then
      az rest --method DELETE \
        --url "$(arm_agent_base_url)/connectors/${name}?api-version=${ARM_API_VERSION}" \
        --output none
      log "Deleted ARM connector ${name}"
      return 0
    fi
    if [[ "${kind}" == "ConnectorV2" ]]; then
      die "ConnectorV2 delete is not implemented; remove its MCP server and OAuth connection through the SRE Agent portal"
    fi
  fi

  token="$(data_plane_token)"
  url="${ENDPOINT}${endpoint_path}/${name}"
  curl -fsS -X DELETE -H "Authorization: Bearer ${token}" "${url}" >/dev/null
  log "Deleted data-plane ${endpoint_path}/${name}"
}

preflight_connector_delete() {
  local file kind

  if selection_requested && [[ "${TARGET}" == "connectors" ]]; then
    while IFS= read -r file; do
      [[ -z "${file}" ]] && continue
      kind="$(manifest_json "${file}" | jq -r '.kind // empty')"
      [[ "${kind}" != "ConnectorV2" ]] || \
        die "ConnectorV2 delete is not implemented; remove its MCP server and OAuth connection through the SRE Agent portal"
    done < <(selected_yaml_files "connectors")
    return 0
  fi

  if ! selection_requested; then
    while IFS= read -r file; do
      [[ -z "${file}" ]] && continue
      kind="$(manifest_json "${file}" | jq -r '.kind // empty')"
      [[ "${kind}" != "ConnectorV2" ]] || \
        die "Full delete includes ConnectorV2 resources and is refused before making changes; delete supported targets selectively"
    done < <(find_yaml_files "${CONFIG_DIR}/connectors")
  fi
}

configure_github_pat() {
  local token url body

  # GitHub authentication in this workshop is delivered by the OAuth-based ConnectorV2
  # manifest. The legacy PAT path remains available only when explicitly requested.
  if [[ -z "${GITHUB_PAT:-}" ]]; then
    log "Skipped GitHub Code Access PAT: no GITHUB_PAT exported, GitHub access is provided by the OAuth connector"
    return 0
  fi

  if [[ "${COMMAND}" == "plan" ]]; then
    log "PUT GitHub Code Access PAT from ${ENV_FILE:-${STUDENT_ROOT}/.env} (secret value hidden)"
    return 0
  fi

  token="$(data_plane_token)"
  url="${ENDPOINT}/api/v2/github/domains/github.com"
  body="$(jq -nc --arg pat "${GITHUB_PAT}" '{AuthType:"Pat",Pat:$pat}')"
  printf '%s' "${body}" | curl -fsS -X PUT \
    -H "Authorization: Bearer ${token}" \
    -H 'Content-Type: application/json' \
    --data-binary @- \
    "${url}" >/dev/null
  log "Configured GitHub Code Access PAT for github.com"
}

custom_instructions_file() {
  printf '%s/custom-instructions.md\n' "${CONFIG_DIR}"
}

validate_custom_instructions() {
  local file content
  file="$(custom_instructions_file)"
  [[ -f "${file}" ]] || die "Custom instructions file not found: ${file}"
  content="$(render_text_file "${file}")"
  [[ -n "$(trim_space "${content}")" ]] || die "Custom instructions file is empty: ${file}"
}

apply_custom_instructions() {
  local file content body token url
  file="$(custom_instructions_file)"
  validate_custom_instructions
  content="$(render_text_file "${file}")"

  if [[ "${COMMAND}" == "plan" ]]; then
    log "PUT agent-global custom instructions from ${file}"
    return 0
  fi

  token="$(data_plane_token)"
  url="${ENDPOINT}/api/v2/agent/customInstructions"
  body="$(jq -nc --arg instructions "${content}" '{instructions:$instructions}')"
  printf '%s' "${body}" | curl -fsS -X PUT \
    -H "Authorization: Bearer ${token}" \
    -H 'Content-Type: application/json' \
    --data-binary @- \
    "${url}" >/dev/null
  log "Applied agent-global custom instructions"
}

data_put_repo() {
  local file="$1"
  local name json body token url
  validate_manifest "${file}"
  name="$(manifest_name "${file}")"
  json="$(manifest_json "${file}")"
  body="$(jq -c --arg name "${name}" '
    .spec as $spec |
    ($spec.type // "GitHub" | ascii_downcase) as $repo_type |
    {
      name: $name,
      type: "CodeRepo",
      properties: {
        url: $spec.url,
        type: (if $repo_type == "ado" or $repo_type == "azuredevops" or $repo_type == "azure-devops" then "AzureDevOps" else "GitHub" end)
      }
    }
    | if (($spec.description // "") == "") then . else .properties.description = $spec.description end
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
  local file="$1"
  local name token url
  name="$(manifest_name "${file}")"
  token="$(data_plane_token)"
  url="${ENDPOINT}/api/v2/repos/${name}"
  curl -fsS -X DELETE -H "Authorization: Bearer ${token}" "${url}" >/dev/null
  log "Deleted data-plane repo ${name}"
}

upload_knowledge_files() {
  local directory="${CONFIG_DIR}/knowledge/files"
  local token file
  [[ -d "${directory}" ]] || return 0
  if [[ "${COMMAND}" != "plan" ]]; then
    token="$(data_plane_token)"
  fi

  while IFS= read -r file; do
    [[ -z "${file}" ]] && continue
    if [[ "${COMMAND}" == "plan" ]]; then
      log "POST knowledge upload ${file}"
    else
      curl -fsS -X POST \
        -H "Authorization: Bearer ${token}" \
        -F "files=@${file}" \
        "${ENDPOINT}/api/v1/agentmemory/upload" >/dev/null
      log "Uploaded knowledge file ${file}"
    fi
  done < <(find_knowledge_files "${directory}")
}

upload_knowledge_file_for_apply() {
  local file="$1"
  local token=""

  if [[ "${COMMAND}" != "plan" ]]; then
    token="$(data_plane_token)"
  fi

  upload_knowledge_file "${file}" "${token}"
}

upload_knowledge_files_best_effort() {
  local directory="${CONFIG_DIR}/knowledge/files"
  local file

  [[ -d "${directory}" ]] || return 0
  while IFS= read -r file; do
    [[ -z "${file}" ]] && continue
    run_apply_step "knowledge-files: ${file}" upload_knowledge_file_for_apply "${file}"
  done < <(find_knowledge_files "${directory}")
}

delete_data_plane_resource_with_retry() {
  local label="$1"
  local url="$2"
  local token="$3"
  local max_attempts="${4:-5}"
  local retry_sleep="${5:-5}"
  local attempt=1 http_code

  while true; do
    http_code="$(curl -sS -o /dev/null -w '%{http_code}' -X DELETE \
      -H "Authorization: Bearer ${token}" "${url}" || true)"
    if [[ "${http_code}" == "2"* || "${http_code}" == "404" ]]; then
      log "Removed ${label}"
      return 0
    fi
    if [[ "${attempt}" -ge "${max_attempts}" ]]; then
      die "DELETE ${label} failed with HTTP ${http_code} after ${attempt} attempt(s)"
    fi
    log "DELETE ${label} returned HTTP ${http_code}; retrying in ${retry_sleep}s (attempt ${attempt}/${max_attempts})"
    sleep "${retry_sleep}"
    attempt=$((attempt + 1))
  done
}

remove_excluded_knowledge_files() {
  local ignore_file="${CONFIG_DIR}/knowledge/.knowledgeignore"
  local token="" line filename encoded_name

  [[ -f "${ignore_file}" ]] || return 0
  if [[ "${COMMAND}" != "plan" ]]; then
    token="$(data_plane_token)"
  fi

  while IFS= read -r line || [[ -n "${line}" ]]; do
    line="${line%$'\r'}"
    line="$(trim_space "${line}")"
    [[ -z "${line}" || "${line}" == \#* ]] && continue
    filename="$(basename "${line}")"

    if [[ "${COMMAND}" == "plan" ]]; then
      log "DELETE excluded knowledge document ${filename}"
      continue
    fi

    encoded_name="$(printf '%s' "${filename}" | jq -sRr @uri)"
    delete_data_plane_resource_with_retry \
      "excluded knowledge document ${filename}" \
      "${ENDPOINT}/api/v1/agentmemory/document/${encoded_name}" \
      "${token}"
  done < "${ignore_file}"
  return 0
}

knowledge_file_matches_name() {
  local file="$1"
  local name="$2"
  local base
  base="$(basename "${file}")"
  [[ "${base}" == "${name}" || "${base%.*}" == "${name}" ]]
}

upload_knowledge_file() {
  local file="$1"
  local token="${2:-}"
  if [[ "${COMMAND}" == "plan" ]]; then
    log "POST knowledge upload ${file}"
  else
    curl -fsS -X POST \
      -H "Authorization: Bearer ${token}" \
      -F "files=@${file}" \
      "${ENDPOINT}/api/v1/agentmemory/upload" >/dev/null
    log "Uploaded knowledge file ${file}"
  fi
}

upload_knowledge_files_selected() {
  local directory="${CONFIG_DIR}/knowledge/files"
  local token file count=0
  [[ -d "${directory}" || -n "${RESOURCE_FILE}" ]] || die "Knowledge directory not found: ${directory}"
  if [[ "${COMMAND}" != "plan" ]]; then
    token="$(data_plane_token)"
  fi

  if [[ -n "${RESOURCE_FILE}" ]]; then
    count=1
    upload_knowledge_file "${RESOURCE_FILE}" "${token:-}"
  else
    while IFS= read -r file; do
      [[ -z "${file}" ]] && continue
      if [[ -n "${RESOURCE_NAME}" ]]; then
        knowledge_file_matches_name "${file}" "${RESOURCE_NAME}" || continue
      fi
      count=$((count + 1))
      upload_knowledge_file "${file}" "${token:-}"
    done < <(find_knowledge_files "${directory}")
  fi

  [[ "${count}" -gt 0 ]] || die "No knowledge file matched target ${TARGET} name ${RESOURCE_NAME:-<all>}"
}

apply_extension_directory() {
  local relative_dir="$1"
  local put_function="$2"
  local file
  while IFS= read -r file; do
    [[ -z "${file}" ]] && continue
    "${put_function}" "${file}"
  done < <(find_yaml_files "${CONFIG_DIR}/${relative_dir}")
}

apply_extension_directory_best_effort() {
  local relative_dir="$1"
  local put_function="$2"
  local target_label="$3"
  local file

  while IFS= read -r file; do
    [[ -z "${file}" ]] && continue
    run_apply_step "${target_label}: ${file}" "${put_function}" "${file}"
  done < <(find_yaml_files "${CONFIG_DIR}/${relative_dir}")
}

apply_extension_directory_selected() {
  local relative_dir="$1"
  local put_function="$2"
  local file count=0
  while IFS= read -r file; do
    [[ -z "${file}" ]] && continue
    count=$((count + 1))
    "${put_function}" "${file}"
  done < <(selected_yaml_files "${relative_dir}")

  [[ "${count}" -gt 0 ]] || die "No manifest matched target ${TARGET} name ${RESOURCE_NAME:-<all>}"
}

apply_data_directory() {
  local relative_dir="$1"
  local endpoint_path="$2"
  local file
  while IFS= read -r file; do
    [[ -z "${file}" ]] && continue
    data_put_manifest "${endpoint_path}" "${file}"
  done < <(find_yaml_files "${CONFIG_DIR}/${relative_dir}")
}

apply_data_directory_best_effort() {
  local relative_dir="$1"
  local endpoint_path="$2"
  local target_label="$3"
  local file

  while IFS= read -r file; do
    [[ -z "${file}" ]] && continue
    run_apply_step "${target_label}: ${file}" data_put_manifest "${endpoint_path}" "${file}"
  done < <(find_yaml_files "${CONFIG_DIR}/${relative_dir}")
}

apply_data_directory_selected() {
  local relative_dir="$1"
  local endpoint_path="$2"
  local file count=0
  while IFS= read -r file; do
    [[ -z "${file}" ]] && continue
    count=$((count + 1))
    data_put_manifest "${endpoint_path}" "${file}"
  done < <(selected_yaml_files "${relative_dir}")

  [[ "${count}" -gt 0 ]] || die "No manifest matched target ${TARGET} name ${RESOURCE_NAME:-<all>}"
}

delete_data_directory() {
  local relative_dir="$1"
  local endpoint_path="$2"
  local file
  while IFS= read -r file; do
    [[ -z "${file}" ]] && continue
    data_delete_manifest "${endpoint_path}" "${file}"
  done < <(find_yaml_files "${CONFIG_DIR}/${relative_dir}")
}

apply_repos() {
  local file
  configure_github_pat
  while IFS= read -r file; do
    [[ -z "${file}" ]] && continue
    data_put_repo "${file}"
  done < <(find_yaml_files "${CONFIG_DIR}/repos")
}

apply_repos_best_effort() {
  local file

  run_apply_step "github-code-access PAT" configure_github_pat
  while IFS= read -r file; do
    [[ -z "${file}" ]] && continue
    run_apply_step "repos: ${file}" data_put_repo "${file}"
  done < <(find_yaml_files "${CONFIG_DIR}/repos")
}

apply_repos_selected() {
  local file count=0
  configure_github_pat
  while IFS= read -r file; do
    [[ -z "${file}" ]] && continue
    count=$((count + 1))
    data_put_repo "${file}"
  done < <(selected_yaml_files "repos")

  [[ "${count}" -gt 0 ]] || die "No manifest matched target ${TARGET} name ${RESOURCE_NAME:-<all>}"
}

delete_repos() {
  local file
  while IFS= read -r file; do
    [[ -z "${file}" ]] && continue
    data_delete_repo "${file}"
  done < <(find_yaml_files "${CONFIG_DIR}/repos")
}

delete_data_directory_selected() {
  local relative_dir="$1"
  local endpoint_path="$2"
  local file count=0
  while IFS= read -r file; do
    [[ -z "${file}" ]] && continue
    count=$((count + 1))
    data_delete_manifest "${endpoint_path}" "${file}"
  done < <(selected_yaml_files "${relative_dir}")

  [[ "${count}" -gt 0 ]] || die "No manifest matched target ${TARGET} name ${RESOURCE_NAME:-<all>}"
}

delete_repos_selected() {
  local file count=0
  while IFS= read -r file; do
    [[ -z "${file}" ]] && continue
    count=$((count + 1))
    data_delete_repo "${file}"
  done < <(selected_yaml_files "repos")

  [[ "${count}" -gt 0 ]] || die "No manifest matched target ${TARGET} name ${RESOURCE_NAME:-<all>}"
}

delete_knowledge_files() {
  local directory="${CONFIG_DIR}/knowledge/files"
  local file token filename encoded_name url
  [[ -d "${directory}" ]] || return 0

  token="$(data_plane_token)"
  while IFS= read -r file; do
    [[ -z "${file}" ]] && continue
    filename="$(basename "${file}")"
    encoded_name="$(printf '%s' "${filename}" | jq -sRr @uri)"
    url="${ENDPOINT}/api/v1/agentmemory/document/${encoded_name}"
    curl -fsS -X DELETE -H "Authorization: Bearer ${token}" "${url}" >/dev/null
    log "Deleted knowledge file ${filename}"
  done < <(find_knowledge_files "${directory}")
}

delete_knowledge_files_selected() {
  local file count=0 token filename encoded_name url
  token="$(data_plane_token)"
  while IFS= read -r file; do
    [[ -z "${file}" ]] && continue
    count=$((count + 1))
    filename="$(basename "${file}")"
    encoded_name="$(printf '%s' "${filename}" | jq -sRr @uri)"
    url="${ENDPOINT}/api/v1/agentmemory/document/${encoded_name}"
    curl -fsS -X DELETE -H "Authorization: Bearer ${token}" "${url}" >/dev/null
    log "Deleted knowledge file ${filename}"
  done < <(selected_knowledge_files)

  [[ "${count}" -gt 0 ]] || die "No knowledge file matched target ${TARGET} name ${RESOURCE_NAME:-<all>}"
}

delete_selected_config() {
  case "${TARGET}" in
    skills)
      ensure_endpoint
      delete_data_directory_selected "skills" "/api/v2/extendedAgent/skills"
      ;;
    subagents)
      ensure_endpoint
      delete_data_directory_selected "subagents" "/api/v2/extendedAgent/agents"
      ;;
    tools)
      ensure_endpoint
      delete_tools_selected
      ;;
    common-prompts)
      ensure_endpoint
      delete_data_directory_selected "common-prompts" "/api/v2/extendedAgent/commonprompts"
      ;;
    scheduled-tasks)
      ensure_endpoint
      delete_data_directory_selected "automations/scheduled-tasks" "/api/v2/extendedAgent/scheduledtasks"
      ;;
    incident-filters)
      ensure_endpoint
      delete_data_directory_selected "automations/incident-filters" "/api/v2/extendedAgent/incidentFilters"
      ;;
    connectors)
      ensure_endpoint
      delete_data_directory_selected "connectors" "/api/v2/extendedAgent/connectors"
      ;;
    repos)
      ensure_endpoint
      delete_repos_selected
      ;;
    hooks)
      ensure_endpoint
      delete_data_directory_selected "hooks" "/api/v2/extendedAgent/hooks"
      ;;
    plugin-configs)
      ensure_endpoint
      delete_data_directory_selected "plugin-configs" "/api/v2/extendedAgent/plugins"
      ;;
    knowledge-files)
      ensure_endpoint
      delete_knowledge_files_selected
      ;;
    http-triggers|plugin-marketplaces|plugin-installations)
      die "delete is not implemented for target ${TARGET}; no stable DELETE route is documented in this script."
      ;;
    *)
      die "Unknown target: ${TARGET}"
      ;;
  esac
}

validate_manifest() {
  local file="$1"
  local json raw_json content_file content_path name kind
  validate_placeholders "${file}"
  json="$(manifest_json "${file}")" || return $?
  name="$(jq -r '.metadata.name // .spec.name // .name // empty' <<< "${json}")"
  kind="$(jq -r '.kind // empty' <<< "${json}")"
  [[ -n "${name}" ]] || die "Missing manifest name in ${file}"
  [[ -n "${kind}" ]] || die "Missing kind in ${file}"
  validate_current_api_contract "${file}" "${kind}" "${json}"

  raw_json="$(render_yaml_to_json "${file}")" || return $?
  if [[ "$(jq -r '(.spec.files // empty) | type' <<< "${raw_json}")" == "array" ]]; then
    local entry entry_path
    while IFS= read -r entry; do
      [[ "${entry}" = /* ]] && entry_path="${entry}" || entry_path="$(cd "$(dirname "${file}")" && pwd)/${entry}"
      [[ -f "${entry_path}" ]] || die "Missing file ${entry_path} referenced by ${file}"
    done < <(jq -r '.spec.files[]' <<< "${raw_json}")
    return 0
  fi
  content_file="$(jq -r '.spec.content_file // empty' <<< "${raw_json}")"
  [[ -z "${content_file}" ]] && return 0
  if [[ "${content_file}" = /* ]]; then
    content_path="${content_file}"
  else
    content_path="$(cd "$(dirname "${file}")" && pwd)/${content_file}"
  fi
  [[ -f "${content_path}" ]] || die "Missing content file ${content_path} referenced by ${file}"
}

validate_current_api_contract() {
  local file="$1"
  local kind="$2"
  local json="$3"

  case "${kind}" in
    Skill)
      jq -e '.spec | has("safety")' <<< "${json}" >/dev/null && \
        die "${file}: skill safety metadata is not part of the current Skill API; run mode belongs on the trigger"
      # Supporting files are keyed by filePath; any other element shape is rejected by the service.
      jq -e '(.spec.additionalFiles // []) | all(has("filePath") and has("content"))' <<< "${json}" >/dev/null || \
        die "${file}: every skill supporting file must resolve to an object with filePath and content"
      ;;
    SubAgent)
      jq -e '.spec | has("agent_type") or has("agentType")' <<< "${json}" >/dev/null && \
        die "${file}: subagent run mode belongs on its response plan or scheduled task; agent_type/agentType is not supported"
      [[ "$(jq -r '(.spec.handoffs // []) | length' <<< "${json}")" -eq 0 ]] || \
        die "${file}: new agent-to-agent handoffs are not supported in workspace mode"
      [[ "$(jq -r '(.spec.agents_as_tools // .spec.agentsAsTools // []) | length' <<< "${json}")" -eq 0 ]] || \
        die "${file}: new agents-as-tools entries are not supported in workspace mode"
      ;;
    IncidentFilter)
      jq -e '.spec | has("customInstructions")' <<< "${json}" >/dev/null && \
        die "${file}: customInstructions is not part of the current IncidentFilter API"
      [[ "$(jq -r '.spec.agentMode // empty' <<< "${json}")" == "Autonomous" ]] || \
        die "${file}: every demo incident filter must declare agentMode: Autonomous"
      [[ "$(jq -r '.spec.isEnabled // .spec.enabled // false' <<< "${json}")" == "true" ]] || \
        die "${file}: every demo incident filter must be enabled"
      ;;
    ScheduledTask)
      [[ "$(jq -r '.spec.mode // .spec.agentMode // empty' <<< "${json}")" == "Autonomous" ]] || \
        die "${file}: every demo scheduled task must declare mode: Autonomous"
      [[ "$(jq -r '.spec.enabled // .spec.isEnabled // false' <<< "${json}")" == "true" ]] || \
        die "${file}: every demo scheduled task must be enabled"
      ;;
    AgentConnector)
      [[ "$(jq -r '.spec.properties.dataConnectorType // empty' <<< "${json}")" != "GitHubOAuth" ]] || \
        die "${file}: GitHubOAuth is deprecated; configure GitHub authentication through the GitHub Domains PAT API"
      if [[ "$(jq -r '.spec.properties.dataConnectorType // empty' <<< "${json}")" == "Mcp" ]]; then
        [[ -n "$(jq -r '.spec.properties.endpoint // empty' <<< "${json}")" ]] || \
          die "${file}: MCP connectors require spec.properties.endpoint"
        [[ -n "$(jq -r '.spec.properties.dataSource // empty' <<< "${json}")" ]] || \
          die "${file}: MCP connectors require spec.properties.dataSource"
        [[ -n "$(jq -r '.spec.properties.extendedProperties.type // empty' <<< "${json}")" ]] || \
          die "${file}: MCP connectors require spec.properties.extendedProperties.type"
        [[ -z "$(jq -r '.spec.properties.identity // empty' <<< "${json}")" ]] || \
          [[ "$(jq -r '.spec.properties.identity' <<< "${json}")" == /subscriptions/* ]] || \
          die "${file}: connector identity must be empty or a full ARM resource ID"
        jq -e '.spec.properties.extendedProperties | has("customHeaders")' <<< "${json}" >/dev/null && \
          die "${file}: use extendedProperties.headers, not the obsolete customHeaders field"
      fi
      ;;
    Repository)
      if [[ "$(jq -r '(.spec.type // "GitHub") | ascii_downcase' <<< "${json}")" == "github" ]]; then
        [[ -z "$(jq -r '.spec.authConnectorName // empty' <<< "${json}")" ]] || \
          die "${file}: GitHub Code Access uses the GitHub Domains PAT API, not authConnectorName"
      fi
      ;;
  esac
  return 0
}

validate_config() {
  local file count=0
  require_local_dependencies
  load_env_file
  [[ -d "${CONFIG_DIR}" ]] || die "Configuration directory not found: ${CONFIG_DIR}"
  normalize_selection
  validate_knowledge_exclusions

  if selection_requested; then
    if [[ "${TARGET}" == "custom-instructions" ]]; then
      validate_custom_instructions
      log "Configuration validation succeeded: custom-instructions"
      return 0
    fi

    if [[ "${TARGET}" == "knowledge-files" ]]; then
      [[ -n "${RESOURCE_FILE}" ]] && [[ -f "${RESOURCE_FILE}" ]] && log "Configuration validation succeeded: ${RESOURCE_FILE}" && return 0
      [[ -d "${CONFIG_DIR}/knowledge/files" ]] || die "Knowledge directory not found: ${CONFIG_DIR}/knowledge/files"
      while IFS= read -r file; do
        [[ -z "${file}" ]] && continue
        if [[ -n "${RESOURCE_NAME}" ]]; then
          knowledge_file_matches_name "${file}" "${RESOURCE_NAME}" || continue
        fi
        count=$((count + 1))
      done < <(find_knowledge_files "${CONFIG_DIR}/knowledge/files")
      [[ "${count}" -gt 0 ]] || die "No knowledge file matched target ${TARGET} name ${RESOURCE_NAME:-<all>}"
      log "Configuration validation succeeded: ${TARGET}${RESOURCE_NAME:+/${RESOURCE_NAME}}"
      return 0
    fi

    validate_selected_manifests
    return 0
  fi

  while IFS= read -r file; do
    [[ -z "${file}" ]] && continue
    validate_manifest "${file}"
  done < <(find_all_yaml_files)

  validate_custom_instructions

  log "Configuration validation succeeded: ${CONFIG_DIR}"
}

validate_selected_manifests() {
  local file count=0 relative_dir
  relative_dir="$(target_relative_dir "${TARGET}")"
  while IFS= read -r file; do
    [[ -z "${file}" ]] && continue
    count=$((count + 1))
    validate_manifest "${file}"
  done < <(selected_yaml_files "${relative_dir}")

  [[ "${count}" -gt 0 ]] || die "No manifest matched target ${TARGET} name ${RESOURCE_NAME:-<all>}"
  log "Configuration validation succeeded: ${TARGET}${RESOURCE_NAME:+/${RESOURCE_NAME}}"
}

target_relative_dir() {
  case "$1" in
    skills) printf 'skills\n' ;;
    subagents) printf 'subagents\n' ;;
    tools) printf 'tools\n' ;;
    common-prompts) printf 'common-prompts\n' ;;
    scheduled-tasks) printf 'automations/scheduled-tasks\n' ;;
    incident-filters) printf 'automations/incident-filters\n' ;;
    connectors) printf 'connectors\n' ;;
    repos) printf 'repos\n' ;;
    hooks) printf 'hooks\n' ;;
    plugin-configs) printf 'plugin-configs\n' ;;
    http-triggers) printf 'automations/http-triggers\n' ;;
    plugin-marketplaces) printf 'plugins/marketplaces\n' ;;
    plugin-installations) printf 'plugins/installations\n' ;;
    *) die "Target $1 does not map to YAML manifests" ;;
  esac
}

apply_all_config() {
  [[ "${COMMAND}" == "plan" ]] || ensure_endpoint

  if [[ "${COMMAND}" == "plan" ]]; then
    apply_custom_instructions
    apply_extension_directory "skills" data_put_skill
    apply_extension_directory "subagents" data_put_subagent
    apply_extension_directory "tools" data_put_tool
    apply_extension_directory "common-prompts" data_put_common_prompt
    apply_extension_directory "automations/scheduled-tasks" data_put_scheduled_task
    apply_extension_directory "automations/incident-filters" data_put_incident_filter

    apply_data_directory "connectors" "/api/v2/extendedAgent/connectors"
    apply_repos
    apply_extension_directory "hooks" data_put_hook
    apply_data_directory "plugin-configs" "/api/v2/extendedAgent/plugins"
    apply_post_directory "automations/http-triggers" "/api/v1/httptriggers/create"
    apply_post_directory "plugins/marketplaces" "/api/v2/plugins/marketplaces"
    apply_post_directory "plugins/installations" "/api/v2/plugins/installations"
    remove_excluded_knowledge_files
    upload_knowledge_files
    return 0
  fi

  APPLY_FAILURES=()

  run_apply_step "custom-instructions" apply_custom_instructions
  apply_extension_directory_best_effort "skills" data_put_skill "skills"
  apply_extension_directory_best_effort "subagents" data_put_subagent "subagents"
  apply_extension_directory_best_effort "tools" data_put_tool "tools"
  apply_extension_directory_best_effort "common-prompts" data_put_common_prompt "common-prompts"
  apply_extension_directory_best_effort "automations/scheduled-tasks" data_put_scheduled_task "scheduled-tasks"
  apply_extension_directory_best_effort "automations/incident-filters" data_put_incident_filter "incident-filters"

  ensure_endpoint
  apply_data_directory_best_effort "connectors" "/api/v2/extendedAgent/connectors" "connectors"
  apply_repos_best_effort
  apply_extension_directory_best_effort "hooks" data_put_hook "hooks"
  apply_data_directory_best_effort "plugin-configs" "/api/v2/extendedAgent/plugins" "plugin-configs"
  apply_post_directory_best_effort "automations/http-triggers" "/api/v1/httptriggers/create" "http-triggers"
  apply_post_directory_best_effort "plugins/marketplaces" "/api/v2/plugins/marketplaces" "plugin-marketplaces"
  apply_post_directory_best_effort "plugins/installations" "/api/v2/plugins/installations" "plugin-installations"
  run_apply_step "knowledge-exclusions" remove_excluded_knowledge_files
  upload_knowledge_files_best_effort

  finish_full_apply
}

apply_selected_config() {
  case "${TARGET}" in
    custom-instructions)
      [[ "${COMMAND}" == "plan" ]] || ensure_endpoint
      apply_custom_instructions
      ;;
    skills)
      [[ "${COMMAND}" == "plan" ]] || ensure_endpoint
      apply_extension_directory_selected "skills" data_put_skill
      ;;
    subagents)
      [[ "${COMMAND}" == "plan" ]] || ensure_endpoint
      apply_extension_directory_selected "subagents" data_put_subagent
      ;;
    tools)
      [[ "${COMMAND}" == "plan" ]] || ensure_endpoint
      apply_extension_directory_selected "tools" data_put_tool
      ;;
    common-prompts)
      [[ "${COMMAND}" == "plan" ]] || ensure_endpoint
      apply_extension_directory_selected "common-prompts" data_put_common_prompt
      ;;
    scheduled-tasks)
      [[ "${COMMAND}" == "plan" ]] || ensure_endpoint
      apply_extension_directory_selected "automations/scheduled-tasks" data_put_scheduled_task
      ;;
    incident-filters)
      [[ "${COMMAND}" == "plan" ]] || ensure_endpoint
      apply_extension_directory_selected "automations/incident-filters" data_put_incident_filter
      ;;
    connectors)
      [[ "${COMMAND}" == "plan" ]] || ensure_endpoint
      apply_data_directory_selected "connectors" "/api/v2/extendedAgent/connectors"
      ;;
    repos)
      [[ "${COMMAND}" == "plan" ]] || ensure_endpoint
      apply_repos_selected
      ;;
    hooks)
      [[ "${COMMAND}" == "plan" ]] || ensure_endpoint
      apply_extension_directory_selected "hooks" data_put_hook
      ;;
    plugin-configs)
      [[ "${COMMAND}" == "plan" ]] || ensure_endpoint
      apply_data_directory_selected "plugin-configs" "/api/v2/extendedAgent/plugins"
      ;;
    http-triggers)
      [[ "${COMMAND}" == "plan" ]] || ensure_endpoint
      apply_post_directory_selected "automations/http-triggers" "/api/v1/httptriggers/create"
      ;;
    plugin-marketplaces)
      [[ "${COMMAND}" == "plan" ]] || ensure_endpoint
      apply_post_directory_selected "plugins/marketplaces" "/api/v2/plugins/marketplaces"
      ;;
    plugin-installations)
      [[ "${COMMAND}" == "plan" ]] || ensure_endpoint
      apply_post_directory_selected "plugins/installations" "/api/v2/plugins/installations"
      ;;
    knowledge-files)
      [[ "${COMMAND}" == "plan" ]] || ensure_endpoint
      if [[ -z "${RESOURCE_NAME}" && -z "${RESOURCE_FILE}" ]]; then
        remove_excluded_knowledge_files
      fi
      upload_knowledge_files_selected
      ;;
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

delete_config() {
  [[ "${YES}" == "true" ]] || die "delete requires --yes"
  require_azure_dependencies
  load_env_file
  require_arm_args
  normalize_selection

  preflight_connector_delete

  if selection_requested; then
    delete_selected_config
    return 0
  fi

  ensure_endpoint

  delete_data_directory "plugin-configs" "/api/v2/extendedAgent/plugins"
  delete_data_directory "hooks" "/api/v2/extendedAgent/hooks"
  delete_data_directory "connectors" "/api/v2/extendedAgent/connectors"
  delete_repos
  delete_knowledge_files

  delete_data_directory "automations/incident-filters" "/api/v2/extendedAgent/incidentFilters"
  delete_data_directory "automations/scheduled-tasks" "/api/v2/extendedAgent/scheduledtasks"
  delete_data_directory "common-prompts" "/api/v2/extendedAgent/commonprompts"
  delete_tools
  delete_data_directory "subagents" "/api/v2/extendedAgent/agents"
  delete_data_directory "skills" "/api/v2/extendedAgent/skills"
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

verify_arm_target() {
  local path="$1"
  local name
  name="$(selected_manifest_name)"

  if [[ -n "${name}" ]]; then
    az rest --method GET \
      --url "$(arm_agent_base_url)/${path}/${name}?api-version=${ARM_API_VERSION}" \
      --query '{name:name,type:type}' \
      --output table
  else
    az rest --method GET \
      --url "$(arm_agent_base_url)/${path}?api-version=${ARM_API_VERSION}" \
      --query 'value[].name' \
      --output table
  fi
}

verify_data_target() {
  local endpoint_path="$1"
  local name
  name="$(selected_manifest_name)"

  if [[ -n "${name}" ]]; then
    curl -fsS -H "Authorization: Bearer $(data_plane_token)" "${ENDPOINT}${endpoint_path}/${name}" | jq '.'
  else
    curl -fsS -H "Authorization: Bearer $(data_plane_token)" "${ENDPOINT}${endpoint_path}" | jq -r '(.value // . // []) | if type == "array" then .[]?.name // .[]?.metadata?.name // empty else empty end'
  fi
}

verify_data_collection_target() {
  local endpoint_path="$1"
  local name
  name="$(selected_manifest_name)"

  if [[ -n "${name}" ]]; then
    curl -fsS -H "Authorization: Bearer $(data_plane_token)" "${ENDPOINT}${endpoint_path}" | jq -r --arg name "${name}" '(if type == "object" and has("value") then .value elif type == "array" then . else [] end) | .[]? | (.name // .metadata.name // empty) | select(. == $name)'
  else
    curl -fsS -H "Authorization: Bearer $(data_plane_token)" "${ENDPOINT}${endpoint_path}" | jq -r '(if type == "object" and has("value") then .value elif type == "array" then . else [] end) | .[]? | (.name // .metadata.name // empty)'
  fi
}

verify_selected_target() {
  case "${TARGET}" in
    custom-instructions)
      curl -fsS -H "Authorization: Bearer $(data_plane_token)" \
        "${ENDPOINT}/api/v2/agent/customInstructions" | jq '.'
      ;;
    skills)
      verify_data_target "/api/v2/extendedAgent/skills"
      ;;
    subagents)
      verify_data_target "/api/v2/extendedAgent/agents"
      ;;
    tools)
      if [[ -n "${RESOURCE_NAME}" || -n "${RESOURCE_FILE}" ]]; then
        while IFS= read -r file; do
          [[ -z "${file}" ]] && continue
          if is_manifest_api_preview_blocked "${file}"; then
            log "Skipped API-preview-blocked tool $(manifest_name "${file}")"
            return 0
          fi
        done < <(selected_yaml_files "tools")
      fi
      verify_data_target "/api/v2/extendedAgent/tools"
      ;;
    common-prompts)
      verify_data_target "/api/v2/extendedAgent/commonprompts"
      ;;
    scheduled-tasks)
      verify_data_target "/api/v2/extendedAgent/scheduledtasks"
      ;;
    incident-filters)
      verify_data_target "/api/v2/extendedAgent/incidentFilters"
      ;;
    connectors)
      verify_agent_connector_manifests
      verify_connector_v2_manifests
      ;;
    repos)
      verify_data_target "/api/v2/repos"
      ;;
    hooks)
      verify_data_target "/api/v2/extendedAgent/hooks"
      ;;
    plugin-configs)
      verify_data_target "/api/v2/extendedAgent/plugins"
      ;;
    http-triggers)
      verify_data_collection_target "/api/v1/httptriggers"
      ;;
    plugin-marketplaces)
      verify_data_collection_target "/api/v2/plugins/marketplaces"
      ;;
    plugin-installations)
      verify_data_collection_target "/api/v2/plugins/installations"
      ;;
    knowledge-files)
      curl -fsS -H "Authorization: Bearer $(data_plane_token)" \
        "${ENDPOINT}/api/v1/agentmemory/status" | jq '.'
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

  log "Agent ARM state:"
  az rest --method GET \
    --url "$(arm_agent_base_url)?api-version=${ARM_API_VERSION}" \
    --query '{name:name,provisioningState:properties.provisioningState,powerState:properties.powerState,endpoint:properties.agentEndpoint}' \
    --output table

  log "ARM sub-resource checks:"
  log "- Connectors"
  az rest --method GET \
    --url "$(arm_agent_base_url)/connectors?api-version=${ARM_API_VERSION}" \
    --query 'value[].name' \
    --output tsv || true

  log "Data-plane knowledge status:"
  curl -fsS -H "Authorization: Bearer $(data_plane_token)" \
    "${ENDPOINT}/api/v1/agentmemory/status" | jq '.' || true

  log "Agent-global custom instructions:"
  curl -fsS -H "Authorization: Bearer $(data_plane_token)" \
    "${ENDPOINT}/api/v2/agent/customInstructions" | jq -r '.instructions // empty' || true

  log "Data-plane extended config checks:"
  for path in \
    /api/v2/repos \
    /api/v2/extendedAgent/skills \
    /api/v2/extendedAgent/agents \
    /api/v2/extendedAgent/tools \
    /api/v2/extendedAgent/commonprompts \
    /api/v2/extendedAgent/scheduledtasks \
    /api/v2/extendedAgent/incidentFilters \
    /api/v2/extendedAgent/hooks \
    /api/v2/extendedAgent/plugins \
    /api/v2/plugins/marketplaces \
    /api/v2/plugins/installations \
    /api/v1/httptriggers; do
    log "- ${path}"
    curl -fsS -H "Authorization: Bearer $(data_plane_token)" "${ENDPOINT}${path}" | jq -r '(if type == "object" and has("value") then .value elif type == "array" then . else [] end) | .[]? | (.name // .metadata.name // empty)' || true
  done

  verify_agent_connector_manifests
  verify_connector_v2_manifests
}

main() {
  parse_args "$@"
  resolve_config_dir

  case "${COMMAND}" in
    validate)
      validate_config
      ;;
    plan|apply)
      apply_config
      ;;
    verify)
      verify_live
      ;;
    delete)
      delete_config
      ;;
    *)
      usage
      die "Unknown command: ${COMMAND}"
      ;;
  esac
}

main "$@"