# Troubleshooting Scenarios

## Scenario 1: baseline visibility

Objective: show healthy traffic before faults, with centralized routing already active via Azure Firewall in the hub. The lab firewall policy allows all flows routed to the firewall via the wildcard network rule `allow-all`.

Initial validation:

- Network Watcher Next Hop from client `10.20.1.10` to DB `10.30.2.10` must show `VirtualAppliance` and the private IP of Azure Firewall.
- Effective routes on the spokes must show Terraform-managed routes toward the firewall for inter-spoke traffic and `0.0.0.0/0`.

Command:

```bash
./scripts/generate-baseline-traffic.sh
```

Expected evidence:

- `FlowType`: IntraVNet, InterVNet, AzurePublic/ExternalPublic.
- `FlowStatus`: A for allowed.
- `BytesSrcToDest`, `BytesDestToSrc`, `AllowedInFlows`, `AllowedOutFlows`.
- For app -> data traffic, effective routing passes through the central firewall even though Traffic Analytics remains a flow view, not a hop-by-hop traceroute.

Query:

```kql
NTANetAnalytics
| where SubType == "FlowLog" and TimeGenerated > ago(24h)
| summarize TotalBytes=sum(BytesSrcToDest + BytesDestToSrc) by SrcIp, DestIp, DestPort, L4Protocol, FlowType, FlowStatus
| top 20 by TotalBytes desc
```

Source: https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-queries#ntanetanalytics-queries

## Scenario 2: NSG block

Objective: simulate an app unable to reach the database.

Command:

```bash
./scripts/trigger-nsg-block.sh
```

Expected evidence:

- `FlowStatus == "Denied"` (full word, not `D`).
- `AclRule` with `Demo-Deny-App-To-Db-5432`.
- `SrcIp` client/app and `DestIp` DB.
- `DestPort == 5432`.

Root cause: a high-priority NSG rule blocks application traffic toward the database port. The firewall is not the deny point in this scenario, because its wildcard network rule allows the traffic.

Complementary validation: Network Watcher IP Flow Verify. Source: https://learn.microsoft.com/en-us/azure/network-watcher/ip-flow-verify-overview

Restore:

```bash
./scripts/restore-nsg-block.sh
```

## Scenario 3: unexpected internet ports or public endpoints

Objective: show unexpected public exposure or communications.

Expected evidence:

- `FlowType == "ExternalPublic"` or `AzurePublic`.
- Ports and public IPs in `NTANetAnalytics`.
- IP details in `NTAIpDetails`.

Query:

```kql
NTANetAnalytics
| where SubType == "FlowLog" and TimeGenerated > ago(24h)
| where FlowType in ("ExternalPublic", "AzurePublic", "MaliciousFlow")
| summarize Flows=sum(AllowedOutFlows + DeniedOutFlows + AllowedInFlows + DeniedInFlows), Bytes=sum(BytesSrcToDest + BytesDestToSrc) by FlowType, SrcIp, DestIp, DestPort, L4Protocol
| order by Bytes desc
```

Source: https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-usage-scenarios#view-ports-and-virtual-machines-receiving-traffic-from-the-internet

## Scenario 4: UDR and asymmetric routing on centralized firewall

Objective: show how to isolate a routing issue when the centralized baseline is correct but a more specific route breaks the return path.

Command:

```bash
./scripts/trigger-udr-asymmetry.sh
```

Expected evidence:

- Next Hop from client -> DB continues to show `VirtualAppliance` and the firewall IP.
- Effective routes on the data spoke show `10.20.1.0/24 -> None`, more specific than the baseline route toward the firewall.
- Traffic Analytics shows direction, bytes, and possible imbalances or missing expected return traffic.
- `IsFlowCapturedAtUDRHop` may be populated when the flow is captured at a UDR hop.

Demonstrated root cause: route table with an incorrect more-specific route that overrides the centralized baseline.

Next Hop source: https://learn.microsoft.com/en-us/azure/network-watcher/next-hop-overview

TA schema source: https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-schema

Restore:

```bash
./scripts/restore-udr-asymmetry.sh
```

## Scenario 5: load balancer traffic distribution

Objective: show distribution toward backends and top conversations.

Expected evidence:

- Top talkers toward ILB IP `10.20.2.100`.
- Flows toward web backends.
- Load balancer fields where Traffic Analytics populates them.

Source: https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-queries#view-load-balancer-traffic-distribution

## Scenario 6: private endpoint

Objective: show traffic toward a private endpoint captured from the source VM side.

Official note: traffic is not recorded at the private endpoint itself; it must be captured from the source VM and can use `PrivateEndpointResourceId`. Source: https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-overview#private-endpoint-traffic

Recommended query: Query 16 in [kql-catalog.md](kql-catalog.md).

## Scenario 7: Traffic Analytics shows no data

Objective: diagnose an apparently empty demo without confusing raw logs, Traffic Analytics processing, and the query window.

Symptoms:

- `NTANetAnalytics` returns no rows.
- The Traffic Analytics dashboard is empty.
- The raw blobs may be present but Log Analytics does not yet show data.

Checklist:

1. Run `./scripts/generate-baseline-traffic.sh`.
2. Wait at least the configured processing interval: 10 minutes in the lab or 60 minutes in steady state.
3. Verify Storage container `insights-logs-flowlogflowevent`.
4. Verify flow log enabled and `traffic_analytics.enabled`.
5. Verify the correct workspace and Log Analytics access.
6. Run Query 14 in [kql-catalog.md](kql-catalog.md).

Sources: https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-schema#data-aggregation, https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-manage#download-a-flow-log

## Scenario 8: duplicates or apparently inflated volumes

Objective: avoid wrong conclusions when the same flow is visible from multiple capture points.

Symptoms:

- Byte or flow counts appear higher than expected traffic.
- The same conversation appears in both inbound and outbound directions.
- Logging is enabled on multiple scopes or on both sides of the communication.

Diagnosis:

- Use `FlowDirection` to distinguish direction relative to the capture point.
- Use `MacAddress` when it is necessary to distinguish the device.
- Use Query 15 in [kql-catalog.md](kql-catalog.md).

Source: https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-queries#prevent-duplicate-records

## Scenario 9: Traffic Analytics broken after manual changes to `NWTA` resources

Objective: recognize an operational breakage caused by manual modification of service-managed resources.

Symptoms:

- Flow logs appear enabled but Traffic Analytics does not update the workspace.
- Data Collection Rules or Data Collection Endpoints with the `NWTA` prefix have been modified or removed.

Probable root cause: Traffic Analytics creates and manages DCR/DCE in the same resource group as the Log Analytics workspace. Microsoft warns not to modify them manually.

Action:

1. Do not attempt to manually manage `NWTA` DCR/DCE via local Terraform.
2. Verify the Traffic Analytics configuration on the flow log.
3. Disable and re-enable Traffic Analytics on the flow log if service-managed resources need to be regenerated.
4. Document ownership: these resources are service-managed.

Source: https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-manage#enable-or-disable-traffic-analytics

## Scenario 10: RBAC error or 403 on activation

Objective: distinguish a product issue from a permissions issue.

Symptoms:

- Terraform fails with 403 errors.
- Flow log creation fails.
- Traffic Analytics fails to configure workspace/DCR/DCE.
- Storage operations fail when Shared Key is disabled.

Checks:

- Does the identity have Flow Logs permissions on Network Watcher?
- Does it have access to the Storage Account and the SAS/key actions required by the flow?
- Does it have Log Analytics access and Insights/DCR/DCE permissions for Traffic Analytics?
- If Shared Key is disabled, does the provider use `storage_use_azuread = true`?

Source: https://learn.microsoft.com/en-us/azure/network-watcher/required-rbac-permissions

## Scenario 11: Sample Food Ordering App HTTP 5xx

Objective: show an application incident on Azure Container Apps managed by the dedicated SRE subagent.

Preparation:

```bash
./scripts/deploy-sample-food-images.sh
./scripts/validate-sample-food-app.sh
```

Controlled fault:

```bash
./scripts/break-sample-food-app.sh
```

Expected evidence:

- `ContainerAppHTTPLogs` shows errors or latency on API paths.
- `ContainerAppConsoleLogs_CL` contains any application exceptions/logs.
- `ContainerAppSystemLogs_CL` shows revision/crash/image-pull events if the issue is platform/runtime.
- Application Insights shows request/failure telemetry if the app emits telemetry.

Quick query:

```bash
./scripts/run-kql.sh sample-food-http-errors
```

Critical note: do not use `NTANetAnalytics` as the primary evidence for Azure Container Apps workload traffic, because the service is not supported by VNet Flow Logs. Source: https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-overview#incompatible-services
