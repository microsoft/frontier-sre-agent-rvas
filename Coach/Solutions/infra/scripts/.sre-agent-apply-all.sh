#!/usr/bin/env bash
# Convenience wrapper: run the full validate -> plan -> apply -> verify cycle of the Azure SRE
# Agent data-plane desired state (Coach/Solutions/AZ-SRE-Agent-Configuration/) against the live
# agent. The script self-locates, so it can be run from any working directory.
#
# Prerequisites: az login (with access to the agent). GITHUB_PAT is optional until
# the github-mcp connector is re-enabled (rename example-github-mcp.yaml → github-mcp.yaml).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}"

# Optional local secrets (e.g. GITHUB_PAT). Never commit a real .env.
[[ -f .env ]] && source .env

# Layout contract: config and Terraform root paths.
export SRE_AGENT_CONFIG_DIR=../azure-sre-agent-config
export SRE_AGENT_TERRAFORM_DIR=.

# Resolve target agent identifiers from Terraform outputs.
# Requires a successful `terraform apply` in SRE_AGENT_TERRAFORM_DIR before running.
_tf_dir="$(cd "${SCRIPT_DIR}/.." && pwd)"
export SUB="$(terraform -chdir="$_tf_dir" output -raw subscription_id)"
export RG="$(terraform -chdir="$_tf_dir" output -raw agent_resource_group)"
export AGENT="$(terraform -chdir="$_tf_dir" output -raw agent_name)"
unset _tf_dir

az account set --subscription "$SUB"

mkdir -p tmp

# 1) validate — full, fail-fast
./sre-agent-config.sh validate

# 2) plan — full
./sre-agent-config.sh plan \
  --subscription "$SUB" --resource-group "$RG" --agent "$AGENT"

# 3) apply — full, best-effort (continues on failures, prints a final summary)
./sre-agent-config.sh apply \
  --subscription "$SUB" --resource-group "$RG" --agent "$AGENT"

# 4) verify — full
./sre-agent-config.sh verify \
  --subscription "$SUB" --resource-group "$RG" --agent "$AGENT"
