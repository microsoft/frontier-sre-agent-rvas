#!/usr/bin/env bash
# Generic apply script for azuresre.ai/v1 capability manifests.
#
# This file is a pre-built, generic asset copied unmodified into every target repository's
# azure-sre-agent-config/scripts/ directory — it is never re-generated or re-authored per run.
# It discovers manifests dynamically by scanning for `api_version: azuresre.ai/v1` YAML files
# and reading each one's own `kind:` field; it never assumes a fixed, per-plan manifest list.
#
# Usage:
#   apply.sh --resource-group <rg> --agent-name <agent> [--subscription-id <sub>]
#            [--manifest-dir <dir>] [--api-version <version>] [--force]
#
# Required parameters:
#   --resource-group / -g   Resource group containing the target Microsoft.App/agents resource.
#   --agent-name     / -n   Name of the target Azure SRE Agent resource.
#
# Optional parameters:
#   --subscription-id / -s  Azure subscription ID. Defaults to the current `az account show`.
#   --manifest-dir    / -d  Directory to scan for manifests. Defaults to the parent of this
#                           script's own directory (the azure-sre-agent-config/ root).
#   --api-version           ARM/data-plane api-version to use. This is a preview surface —
#                           confirm the current value against the live Learn/REST reference
#                           fetched when the plan this script accompanies was authored, and
#                           override this default if it has changed.
#   --force           / -f  Proceed even when the preflight step finds the 5-skill cap exceeded
#                           or a name collision. Without this flag the script hard-stops
#                           (non-zero exit, no write call made) on either condition.
#
# Exit codes: 0 on full success; non-zero on any missing dependency, preflight hard-stop, or
# apply/verify failure. On a partial failure, every manifest applied successfully before the
# failure is printed, so a partial apply is never silently reported as complete.
#
# Concurrency: do not run two invocations of this script against the same agent at the same
# time — the preflight check and the later apply calls are not atomic as a pair, so two
# simultaneous runs can each pass preflight before either writes, bypassing the 5-skill cap.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEFAULT_MANIFEST_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
DATA_PLANE_AUDIENCE="https://azuresre.dev"
API_VERSION="2026-01-01"

RESOURCE_GROUP=""
AGENT_NAME=""
SUBSCRIPTION_ID=""
MANIFEST_DIR="${DEFAULT_MANIFEST_DIR}"
FORCE="false"

log() { printf '%s\n' "$*" >&2; }
die() { log "ERROR: $*"; exit 1; }

usage() {
  cat <<'USAGE'
Usage: apply.sh --resource-group <rg> --agent-name <agent> [options]

Required:
  -g, --resource-group <rg>     Resource group of the target agent.
  -n, --agent-name <agent>      Name of the target Azure SRE Agent resource.

Optional:
  -s, --subscription-id <sub>   Subscription ID (default: current `az account show`).
  -d, --manifest-dir <dir>      Manifest root to scan (default: this script's parent directory).
      --api-version <version>   Override the ARM/data-plane api-version (default: 2026-01-01).
  -f, --force                   Proceed past a cap/collision preflight hard-stop.
  -h, --help                    Show this help and exit.
USAGE
}

parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      -g|--resource-group) RESOURCE_GROUP="${2:-}"; shift 2 ;;
      -n|--agent-name) AGENT_NAME="${2:-}"; shift 2 ;;
      -s|--subscription-id) SUBSCRIPTION_ID="${2:-}"; shift 2 ;;
      -d|--manifest-dir) MANIFEST_DIR="${2:-}"; shift 2 ;;
      --api-version) API_VERSION="${2:-}"; shift 2 ;;
      -f|--force) FORCE="true"; shift ;;
      -h|--help) usage; exit 0 ;;
      *) die "Unknown option: $1 (see --help)" ;;
    esac
  done
  [[ -n "${RESOURCE_GROUP}" ]] || die "--resource-group is required"
  [[ -n "${AGENT_NAME}" ]] || die "--agent-name is required"
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || die "Required command not found: $1"
}

yaml_to_json() {
  if command -v python3 >/dev/null 2>&1 && python3 -c 'import yaml' >/dev/null 2>&1; then
    python3 -c 'import json, sys, yaml; print(json.dumps(yaml.safe_load(sys.stdin.read())))'
  elif command -v yq >/dev/null 2>&1; then
    yq -o=json '.'
  else
    die "Required YAML parser not found: install Python 3 with PyYAML, or yq"
  fi
}

# Discover every azuresre.ai/v1 manifest under MANIFEST_DIR by reading each YAML file's own
# `kind:` field — never a hardcoded, per-plan manifest list.
discover_manifests() {
  local file
  while IFS= read -r -d '' file; do
    grep -qE '^api_version:[[:space:]]*["'"'"']?azuresre\.ai/v1["'"'"']?[[:space:]]*$' "${file}" 2>/dev/null || continue
    printf '%s\n' "${file}"
  done < <(find "${MANIFEST_DIR}" -type f -name '*.yaml' -print0 | sort -z)
}

endpoint_kind_for() {
  case "$1" in
    Skill) printf 'skills' ;;
    SubAgent) printf 'agents' ;;
    Tool) printf 'tools' ;;
    ScheduledTask) printf 'scheduledtasks' ;;
    CommonPrompt) printf 'commonprompts' ;;
    IncidentFilter) printf 'incidentFilters' ;;
    Hook) printf 'hooks' ;;
    Plugin) printf 'plugins' ;;
    ConnectorV2) printf 'connectors' ;;
    Connector) printf 'ARM' ;;  # AgentConnector: applied through ARM control-plane, not data-plane
    *) die "Unknown manifest kind: $1" ;;
  esac
}

# Build the plain (not base64-encoded) JSON body this manifest PUTs as its `properties`. A
# Skill manifest's `spec.files` list names the paired Markdown body (first entry) to inline as
# `skillContent`; every other kind's `spec` block is passed through as-is.
manifest_properties_json() {
  local json="$1" kind="$2" base_dir="$3"
  if [[ "${kind}" == "Skill" ]]; then
    local first content_path content_json
    first="$(jq -r '.spec.files[0] // empty' <<< "${json}")"
    [[ -n "${first}" ]] || die "Skill manifest has no spec.files entry"
    [[ "${first}" = /* ]] && content_path="${first}" || content_path="${base_dir}/${first}"
    [[ -f "${content_path}" ]] || die "Skill body file not found: ${content_path}"
    content_json="$(jq -Rs '.' < "${content_path}")"
    jq --argjson content "${content_json}" \
      '.spec.skillContent = $content | .spec.description = (.spec.description // "") | .spec.tools = (.spec.tools // []) | .spec | del(.files)' \
      <<< "${json}"
  else
    jq '.spec' <<< "${json}"
  fi
}

resolve_endpoint() {
  local arm_url token
  arm_url="https://management.azure.com/subscriptions/${SUBSCRIPTION_ID}/resourceGroups/${RESOURCE_GROUP}/providers/Microsoft.App/agents/${AGENT_NAME}?api-version=${API_VERSION}"
  ENDPOINT="$(az rest --method GET --url "${arm_url}" --query properties.agentEndpoint -o tsv)"
  [[ -n "${ENDPOINT}" ]] || die "Could not resolve agentEndpoint for ${AGENT_NAME} in ${RESOURCE_GROUP}"
  TOKEN="$(az account get-access-token --resource "${DATA_PLANE_AUDIENCE}" --query accessToken -o tsv)"
}

data_plane_get() {
  curl -fsS -H "Authorization: Bearer ${TOKEN}" "${ENDPOINT}/api/v2/extendedAgent/$1"
}

# Returns the HTTP status code for a data-plane GET without failing on a non-2xx response, so
# callers can distinguish "not found" (404) from a transient or auth failure (any other
# non-2xx), which would otherwise look identical to "absent" if swallowed.
data_plane_get_status() {
  curl -s -o /dev/null -w '%{http_code}' -H "Authorization: Bearer ${TOKEN}" "${ENDPOINT}/api/v2/extendedAgent/$1"
}

data_plane_put() {
  curl -fsS -X PUT -H "Authorization: Bearer ${TOKEN}" -H 'Content-Type: application/json' \
    --data "$3" "${ENDPOINT}/api/v2/extendedAgent/$1/$2"
}

arm_put_connector() {
  local name="$1" properties_json="$2"
  az rest --method PUT \
    --url "https://management.azure.com/subscriptions/${SUBSCRIPTION_ID}/resourceGroups/${RESOURCE_GROUP}/providers/Microsoft.App/agents/${AGENT_NAME}/DataConnectors/${name}?api-version=${API_VERSION}" \
    --body "$(jq -nc --argjson properties "${properties_json}" '{properties:$properties}')" >/dev/null
}

arm_get_connector() {
  az rest --method GET \
    --url "https://management.azure.com/subscriptions/${SUBSCRIPTION_ID}/resourceGroups/${RESOURCE_GROUP}/providers/Microsoft.App/agents/${AGENT_NAME}/DataConnectors/$1?api-version=${API_VERSION}"
}

# Checks whether an AgentConnector-kind connector already exists without treating a transient
# or auth failure as "absent." Echoes "exists", "absent", or dies with the captured error on
# anything else (so preflight never silently misreports connectivity trouble as a clean check).
arm_connector_status() {
  local name="$1" err
  if err="$(az rest --method GET --url "https://management.azure.com/subscriptions/${SUBSCRIPTION_ID}/resourceGroups/${RESOURCE_GROUP}/providers/Microsoft.App/agents/${AGENT_NAME}/DataConnectors/${name}?api-version=${API_VERSION}" 2>&1 >/dev/null)"; then
    printf 'exists\n'
  elif grep -qi '404\|notfound' <<< "${err}"; then
    printf 'absent\n'
  else
    die "Preflight: could not check connector '${name}' existence (${err})"
  fi
}

# Reject any manifest name that is not a URL-safe slug — metadata.name is interpolated directly
# into REST paths and query strings, so a name containing '/', '?', '&', '#', whitespace, or
# unicode would otherwise retarget or corrupt the request with no validation anywhere else.
validate_manifest_name() {
  local name="$1"
  [[ "${name}" =~ ^[A-Za-z0-9._-]+$ ]] || die "Manifest name is not a URL-safe slug: '${name}' (allowed: letters, digits, '.', '_', '-')"
}

# Confirm the verify-GET's returned properties match what was PUT. Only the keys present in the
# PUT body are checked — an agent-side default or computed field that only appears in the
# response is not treated as a mismatch.
verify_properties_match() {
  local expected_json="$1" actual_json="$2"
  jq -en --argjson expected "${expected_json}" --argjson actual "${actual_json}" \
    '($actual.properties // $actual) as $a
     | ($expected | to_entries) as $entries
     | ($entries | map($a[.key] == .value) | all)' >/dev/null
}

# Preflight (read-only): check the 5-skill cap and every discovered manifest's name for a
# collision against what already exists. Hard-stops (non-zero exit, no write call) unless
# FORCE=true.
run_preflight() {
  local -n manifests_ref=$1
  local existing_skills existing_count new_skill_count=0 problem="false" file json kind name endpoint_kind

  existing_skills="$(data_plane_get skills)" || die "Preflight: could not list existing skills"
  existing_count="$(jq 'length' <<< "${existing_skills}")"

  for file in "${manifests_ref[@]}"; do
    json="$(yaml_to_json < "${file}")"
    kind="$(jq -r '.kind // empty' <<< "${json}")"
    name="$(jq -r '.metadata.name // empty' <<< "${json}")"
    [[ -n "${kind}" && -n "${name}" ]] || die "Manifest missing kind/metadata.name: ${file}"
    validate_manifest_name "${name}"
    endpoint_kind="$(endpoint_kind_for "${kind}")"

    if [[ "${kind}" == "Skill" ]]; then
      if ! jq -e --arg n "${name}" 'any(.[]; .name == $n)' <<< "${existing_skills}" >/dev/null; then
        new_skill_count=$((new_skill_count + 1))
      fi
    fi

    if [[ "${endpoint_kind}" == "ARM" ]]; then
      if [[ "$(arm_connector_status "${name}")" == "exists" ]]; then
        log "Preflight: name collision — connector '${name}' already exists"
        problem="true"
      fi
    else
      local get_status
      get_status="$(data_plane_get_status "${endpoint_kind}/${name}")"
      case "${get_status}" in
        200) log "Preflight: name collision — ${kind} '${name}' already exists"; problem="true" ;;
        404) ;;
        *) die "Preflight: unexpected HTTP ${get_status} checking ${kind} '${name}' (connectivity or auth issue?)" ;;
      esac
    fi
  done

  if (( existing_count + new_skill_count > 5 )); then
    log "Preflight: 5-skill cap would be exceeded (${existing_count} existing + ${new_skill_count} new)."
    log "Recommendation: fold the new capability into an existing skill instead of adding a sixth."
    problem="true"
  fi

  if [[ "${problem}" == "true" ]]; then
    if [[ "${FORCE}" == "true" ]]; then
      log "Preflight found the issue(s) above; proceeding because --force was passed."
    else
      die "Preflight hard-stop (no write call made). Re-run with --force only after you've explicitly accepted this risk."
    fi
  fi
}

apply_manifest() {
  local file="$1" base_dir json kind name endpoint_kind properties_json body verify_json
  base_dir="$(cd "$(dirname "${file}")" && pwd)"
  json="$(yaml_to_json < "${file}")"
  kind="$(jq -r '.kind' <<< "${json}")"
  name="$(jq -r '.metadata.name' <<< "${json}")"
  validate_manifest_name "${name}"
  endpoint_kind="$(endpoint_kind_for "${kind}")"
  properties_json="$(manifest_properties_json "${json}" "${kind}" "${base_dir}")"

  if [[ "${endpoint_kind}" == "ARM" ]]; then
    arm_put_connector "${name}" "${properties_json}"
    verify_json="$(arm_get_connector "${name}")"
  else
    body="$(jq -nc --arg name "${name}" --arg type "${kind}" --argjson properties "${properties_json}" \
      '{name:$name, type:$type, tags:[], properties:$properties}')"
    data_plane_put "${endpoint_kind}" "${name}" "${body}" >/dev/null
    verify_json="$(data_plane_get "${endpoint_kind}/${name}")"
  fi

  verify_properties_match "${properties_json}" "${verify_json}" \
    || die "Verify failed: ${kind} '${name}' returned properties do not match what was PUT"
  log "Applied and verified: ${kind} '${name}'"
}

main() {
  parse_args "$@"
  require_command az
  require_command curl
  require_command jq

  [[ -n "${SUBSCRIPTION_ID}" ]] || SUBSCRIPTION_ID="$(az account show --query id -o tsv)"
  [[ -d "${MANIFEST_DIR}" ]] || die "Manifest directory not found: ${MANIFEST_DIR}"

  mapfile -t manifests < <(discover_manifests)
  [[ "${#manifests[@]}" -gt 0 ]] || die "No azuresre.ai/v1 manifests found under ${MANIFEST_DIR}"

  resolve_endpoint
  run_preflight manifests

  local applied=()
  for file in "${manifests[@]}"; do
    apply_manifest "${file}"
    applied+=("${file}")
  done

  log "All ${#applied[@]} manifest(s) applied and verified successfully."
}

main "$@"
