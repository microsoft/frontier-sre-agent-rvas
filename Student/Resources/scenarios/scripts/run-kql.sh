#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat >&2 <<'USAGE'
Usage: ./Infra/scripts/run-kql.sh [top-talkers|denied|flow-types|public-ips|sample-food-http-errors|sample-food-latency|sample-food-console]
       ./Infra/scripts/run-kql.sh "<KQL query>"
       ./Infra/scripts/run-kql.sh --query "<KQL query>"
       ./Infra/scripts/run-kql.sh - < query.kql
USAGE
}

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  usage
  exit 0
fi

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

looks_like_kql() {
  local candidate_query="$1"
  [[ "${candidate_query}" == *'|'* || "${candidate_query}" == *' '* || "${candidate_query}" == *$'\t'* || "${candidate_query}" == *$'\n'* ]]
}

query_name="${1:-top-talkers}"

case "${query_name}" in
  --query)
    shift
    if [[ "$#" -eq 0 ]]; then
      echo "Missing KQL query after --query." >&2
      usage
      exit 1
    fi
    query="$*"
    ;;
  -)
    query="$(cat)"
    ;;
  top-talkers)
    query='NTANetAnalytics | where SubType == "FlowLog" and TimeGenerated > ago(24h) | summarize TotalBytes=sum(BytesSrcToDest + BytesDestToSrc) by SrcIp, DestIp, DestPort, L4Protocol | top 20 by TotalBytes desc'
    ;;
  denied)
    query='NTANetAnalytics | where SubType == "FlowLog" and TimeGenerated > ago(24h) | where FlowStatus contains "Denied" or DeniedInFlows > 0 or DeniedOutFlows > 0 | summarize DeniedFlows=sum(DeniedInFlows + DeniedOutFlows) by AclRule, SrcIp, DestIp, DestPort, L4Protocol | order by DeniedFlows desc'
    ;;
  flow-types)
    query='NTANetAnalytics | where SubType == "FlowLog" and TimeGenerated > ago(24h) | summarize Flows=sum(AllowedInFlows + DeniedInFlows + AllowedOutFlows + DeniedOutFlows), Bytes=sum(BytesSrcToDest + BytesDestToSrc) by FlowType, FlowStatus | order by Bytes desc'
    ;;
  public-ips)
    query='NTAIpDetails | where TimeGenerated > ago(24h) | summarize Count=count() by FlowType, PublicIPDetails, Location, ThreatType | order by Count desc'
    ;;
  sample-food-http-errors)
    api_app_name="$(tf_output sample_food_api_container_app_name)"
    query="ContainerAppHTTPLogs | where TimeGenerated > ago(24h) | where ContainerAppName == '${api_app_name}' | where toint(StatusCode) >= 400 | summarize Errors=count(), StatusCodes=make_set(StatusCode, 10), ExampleDetails=take_any(ResponseCodeDetails) by Method, Path | order by Errors desc"
    ;;
  sample-food-latency)
    api_app_name="$(tf_output sample_food_api_container_app_name)"
    query="ContainerAppHTTPLogs | where TimeGenerated > ago(24h) | where ContainerAppName == '${api_app_name}' | summarize Requests=count(), P50=percentile(RequestDuration, 50), P95=percentile(RequestDuration, 95), P99=percentile(RequestDuration, 99) by Path | order by P95 desc"
    ;;
  sample-food-console)
    api_app_name="$(tf_output sample_food_api_container_app_name)"
    query="ContainerAppConsoleLogs_CL | where TimeGenerated > ago(24h) | where ContainerAppName_s == '${api_app_name}' | project TimeGenerated, RevisionName_s, ContainerName_s, Log_s | order by TimeGenerated desc | take 100"
    ;;
  *)
    if looks_like_kql "${query_name}"; then
      query="${query_name}"
    else
      usage
      exit 1
    fi
    ;;
esac

if [[ -z "${query//[[:space:]]/}" ]]; then
  echo "KQL query cannot be empty." >&2
  usage
  exit 1
fi

workspace_id="$(tf_output demo_lab_log_analytics_workspace_customer_id)"

az monitor log-analytics query \
  --workspace "${workspace_id}" \
  --analytics-query "${query}" \
  --output table