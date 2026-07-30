#!/usr/bin/env bash
# Convenience wrapper: run the full validate -> plan -> apply -> verify cycle of the Azure SRE
# Agent data-plane desired state (Student/Resources/azure-sre-agent-config/) against the live
# agent. The script self-locates, so it can be run from any working directory.
#
# Prerequisites:
#   az login, and the following env vars set (or a .env in Student/):
#     SRE_AGENT_RG    — resource group containing the SRE Agent
#     SRE_AGENT_NAME  — SRE Agent resource name
#   Subscription is read from Terraform outputs (requires a prior 'make infra').
#   Override with SRE_AGENT_SUB if needed.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}"

# Load .env from Student/ (two levels up from scripts/) if present.
ENV_FILE="${SCRIPT_DIR}/../../.env"
[[ -f "${ENV_FILE}" ]] && source "${ENV_FILE}"
[[ -n "${BERLIN_MCP_URL:-}" ]] && export BERLIN_MCP_URL
[[ -n "${BERLIN_MCP_AUTH_TOKEN:-}" ]] && export BERLIN_MCP_AUTH_TOKEN

# Layout contract: config dir relative to this script.
export SRE_AGENT_CONFIG_DIR=../../azure-sre-agent-config

# Resolve subscription from Terraform outputs if not already set.
if [[ -z "${SRE_AGENT_SUB:-}" ]]; then
  _tf_dir="$(cd "${SCRIPT_DIR}/.." && pwd)"
  SRE_AGENT_SUB="$(terraform -chdir="$_tf_dir" output -raw subscription_id)"
  unset _tf_dir
fi

if [[ -z "${BERLIN_MCP_URL:-}" ]]; then
  _tf_dir="$(cd "${SCRIPT_DIR}/.." && pwd)"
  BERLIN_MCP_URL="$(terraform -chdir="$_tf_dir" output -raw parking_berlin_mcp_url)"
  export BERLIN_MCP_URL
  unset _tf_dir
fi

: "${SRE_AGENT_RG:?SRE_AGENT_RG is not set. Add it to Student/.env or export it.}"
: "${SRE_AGENT_NAME:?SRE_AGENT_NAME is not set. Add it to Student/.env or export it.}"

az account set --subscription "${SRE_AGENT_SUB}"

mkdir -p tmp

# 1) validate — full, fail-fast
./sre-agent-config.sh validate

# 2) plan — full
./sre-agent-config.sh plan \
  --subscription "${SRE_AGENT_SUB}" --resource-group "${SRE_AGENT_RG}" --agent "${SRE_AGENT_NAME}"

# 3) apply — full, best-effort (continues on failures, prints a final summary)
./sre-agent-config.sh apply \
  --subscription "${SRE_AGENT_SUB}" --resource-group "${SRE_AGENT_RG}" --agent "${SRE_AGENT_NAME}"

# 4) verify — full
./sre-agent-config.sh verify \
  --subscription "${SRE_AGENT_SUB}" --resource-group "${SRE_AGENT_RG}" --agent "${SRE_AGENT_NAME}"
