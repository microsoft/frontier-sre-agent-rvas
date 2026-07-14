# nsg-deny-flow-investigation

Use this skill when investigating denied flows in Traffic Analytics, especially after running `Student/Resources/scenarios/scripts/trigger-nsg-block.sh`, when an Azure Monitor denied-flow alert fires, or when a user reports blocked traffic between workload subnets.

## Builder Upload Settings

| Field | Value |
| --- | --- |
| Skill name | `nsg-deny-flow-investigation` |
| Description | Use when denied flows appear in `NTANetAnalytics`, an NSG block scenario is active, or Traffic Analytics shows blocked traffic by ACL rule/group. |
| Recommended tools | `RunAzCliReadCommands`, `QueryLogAnalyticsByWorkspaceId`, `GetAzCliHelp` |
| Recommended knowledge files | `documentation/troubleshooting-scenarios.md`, `documentation/kql-catalog.md`, `documentation/terraform-design.md`, `Student/Resources/scenarios/scripts/trigger-nsg-block.sh`, `Student/Resources/scenarios/scripts/restore-nsg-block.sh` |
| Default run mode | Review for remediation and restore actions |

## Operating Principles

1. Use Traffic Analytics evidence before proposing remediation.
2. Identify the deny rule and ACL/NSG group, not just the source/destination IP.
3. Distinguish demo-controlled deny rules from real configuration drift.
4. Restore demo overlays with the project restore script only after approval.
5. Do not weaken NSG policy automatically.

## Official References

- VNet Flow Logs log format: https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-overview#log-format
- Network Watcher NSG diagnostics: https://learn.microsoft.com/en-us/azure/network-watcher/nsg-diagnostics-overview
- Effective security rules: https://learn.microsoft.com/en-us/azure/network-watcher/effective-security-rules-overview
- Traffic Analytics overview: https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics

## Trigger Conditions

Load this skill when:

- `FlowStatus contains "Denied"` (or `DeniedInFlows`/`DeniedOutFlows` > 0) appears in `NTANetAnalytics`.
- Azure Monitor alert indicates denied flows.
- The user ran or suspects `Student/Resources/scenarios/scripts/trigger-nsg-block.sh`.
- Client, API, web or DB communication is denied.
- A rule name or ACL group must be identified.
- The user asks for root cause of blocked traffic.

## Non-Goals

- Do not delete or modify NSG rules without Review-mode approval.
- Do not assume every deny is bad; some denies are expected default posture.
- Do not treat denied flow count alone as impact; map it to expected service path.

## Procedure

### Step 1: Establish incident context

Collect:

- Time window.
- Source and destination if known.
- Expected application flow.
- Whether this is a demo fault scenario.
- Whether `trigger-nsg-block.sh` was run.

### Step 2: Query denied flows

```kql
NTANetAnalytics
| where SubType == "FlowLog" and TimeGenerated > ago(24h)
| where FlowStatus contains "Denied" or DeniedInFlows > 0 or DeniedOutFlows > 0
| summarize DeniedFlows=sum(DeniedInFlows + DeniedOutFlows) by AclRule, AclGroup, SrcIp, DestIp, DestPort, L4Protocol
| order by DeniedFlows desc
```

### Step 3: Focus on known project endpoints

Use for client to DB/API scenarios:

```kql
let SourceIp = "10.20.1.10";
let DestinationIp = "10.30.2.10";
NTANetAnalytics
| where SubType == "FlowLog" and TimeGenerated > ago(24h)
| where (SrcIp == SourceIp and DestIp == DestinationIp) or (SrcIp == DestinationIp and DestIp == SourceIp)
| project TimeGenerated, SrcIp, DestIp, DestPort, L4Protocol, FlowDirection, FlowStatus, AclRule, AclGroup, DeniedInFlows, DeniedOutFlows, BytesSrcToDest, BytesDestToSrc
| order by TimeGenerated desc
```

### Step 4: Inspect live NSG/effective rules

Use read-only commands to inspect the source or destination NIC:

```bash
az network nic list-effective-nsg \
  --resource-group <resource-group-name> \
  --name <nic-name>
```

List NSG rules if the NSG name is known:

```bash
az network nsg rule list \
  --resource-group <resource-group-name> \
  --nsg-name <nsg-name> \
  --query "[].{name:name, priority:priority, direction:direction, access:access, protocol:protocol, source:sourceAddressPrefix, destination:destinationAddressPrefix, destinationPort:destinationPortRange}" \
  --output table
```

### Step 5: Determine if it is demo-controlled

Check project scripts:

- `Student/Resources/scenarios/scripts/trigger-nsg-block.sh` adds the temporary deny rule.
- `Student/Resources/scenarios/scripts/restore-nsg-block.sh` removes the temporary deny rule.

If the deny rule matches the demo rule, recommend restore:

```bash
Student/Resources/scenarios/scripts/restore-nsg-block.sh
```

Do not execute restore automatically unless the response plan is explicitly approved for that action.

## Classification

| Classification | Evidence | Next action |
| --- | --- | --- |
| Expected deny | Default deny or intended security policy. | Document and no remediation. |
| Demo deny | Rule from trigger script. | Recommend `restore-nsg-block.sh` in Review mode. |
| Drift deny | Rule not expected by Terraform. | Recommend Terraform comparison and owner review. |
| Wrong path deny | Traffic hits unexpected NSG/ACL group. | Use Network Watcher effective rules and UDR diagnostics. |
| Unknown deny | KQL lacks enough rule context. | Run effective rules / NSG diagnostics. |

## Evidence Required

- Time window.
- Source IP, destination IP, port, protocol.
- `FlowStatus`, `AclRule`, `AclGroup`.
- Denied flow count.
- VM/subnet mapping.
- Effective NSG rule output, if available.
- Whether demo trigger script was used.
- Restore recommendation if applicable.

## Output Format

```markdown
## Denied Flow Finding
<Expected deny | Demo deny | Drift deny | Wrong path deny | Unknown>

## Impacted Flow
- Source:
- Destination:
- Port/protocol:
- Direction:

## Evidence
- KQL result:
- AclRule/AclGroup:
- Effective NSG:
- Project script correlation:

## Root Cause Hypothesis
<explanation and confidence>

## Recommended Action
<none | restore script | Terraform review | Review-mode NSG change>

## References
- documentation/troubleshooting-scenarios.md
- documentation/kql-catalog.md
- <official source>
```

## Escalation Criteria

Escalate when:

- The denied traffic affects production-like service connectivity.
- A non-demo rule blocks required application traffic.
- A broad allow rule is requested as remediation.
- NSG and Traffic Analytics evidence disagree.
- Security/admin rules outside project Terraform appear involved.

## Related Skills

- `traffic-analytics-kql-analysis`
- `connectivity-diagnostics`
- `vnet-flow-logs-and-ingestion`
- `rbac-and-resource-access-check`
