# Ingestion Diagnostics — KQL And Azure CLI

Executable diagnostics for the flow-log funnel: flow log enabled, successful raw writes reported
by Azure Storage metrics, and Traffic Analytics enrichment in Log Analytics. Replace placeholders
with values resolved from Azure. Use `GetAzCliHelp` when command syntax differs in the installed
Azure CLI version.

## KQL

### Ingestion smoke test

```kql
NTANetAnalytics
| where SubType == "FlowLog"
| take 10
```

### Freshness by target

```kql
NTANetAnalytics
| where TimeGenerated > ago(48h)
| summarize Records=count(), FirstSeen=min(TimeGenerated), LastSeen=max(TimeGenerated) by SubType, FlowType, TargetResourceId
| order by LastSeen desc
```

### Recent records for expected flow logs

```kql
NTANetAnalytics
| where SubType == "FlowLog" and TimeGenerated > ago(24h)
| summarize Records=count(), LastSeen=max(TimeGenerated) by TargetResourceId, SrcSubnet, DestSubnet, FlowType
| order by LastSeen desc
```

## Azure CLI read-only commands

### Flow log configuration

```bash
az network watcher flow-log list \
  --location <location> \
  --resource-group <network-watcher-resource-group> \
  --output table
```

### Log Analytics workspace

```bash
az monitor log-analytics workspace show \
  --resource-group <resource-group> \
  --workspace-name <workspace-name>
```

### Storage Account compliance with flow-log requirements

```bash
az storage account show \
  --name <flow-log-storage-account> \
  --resource-group <resource-group> \
  --query "{name:name, location:location, kind:kind, sku:sku.name, publicNetworkAccess:publicNetworkAccess, defaultAction:networkRuleSet.defaultAction, bypass:networkRuleSet.bypass, minTlsVersion:minimumTlsVersion}" \
  --output json
```

The workshop storage account intentionally has `publicNetworkAccess: Disabled`,
`defaultAction: Deny`, and `bypass: AzureServices`. Direct Blob data-plane listing from an
operator workstation is therefore expected to be blocked.

### Successful raw flow-log writes

```bash
STORAGE_ID="$(az storage account show \
  --name <flow-log-storage-account> \
  --resource-group <resource-group> \
  --query id \
  --output tsv)"

for API_NAME in PutBlock PutBlockList; do
  TOTAL="$(az monitor metrics list \
    --resource "${STORAGE_ID}" \
    --metrics Transactions \
    --aggregation Total \
    --interval 5m \
    --offset 1h \
    --filter "ApiName eq '${API_NAME}' and ResponseType eq 'Success'" \
    --query "sum(value[0].timeseries[0].data[].total)" \
    --output tsv)"
  printf '%s successful operations in the last hour: %s\n' "${API_NAME}" "${TOTAL:-0}"
done
```

Positive `PutBlock` and `PutBlockList` totals prove that the dedicated flow-log storage account is
still receiving committed block-blob writes. Correlate the observation window with generated IaaS
traffic, then use the KQL freshness queries above to verify Traffic Analytics processing.

## Authorization failures

If a control-plane or metrics command fails with an authorization error, do not request broad
permissions. Report the exact missing action and recommend least privilege, handing off to
`rbac-and-resource-access-check`. Do not treat blocked direct Blob listing as missing RBAC when
public network access is intentionally disabled.
