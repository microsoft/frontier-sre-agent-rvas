# udr-asymmetry-investigation

Use this skill when investigating route table issues, UDR blackholes, asymmetric routing, unexpected next hop, Azure Firewall/NVA path issues, or the controlled `Student/Resources/scenarios/scripts/trigger-udr-asymmetry.sh` scenario.

## Builder Upload Settings

| Field | Value |
| --- | --- |
| Skill name | `udr-asymmetry-investigation` |
| Description | Use when routing asymmetry, UDR blackhole, unexpected next hop, firewall routing, or the controlled UDR demo fault is suspected. |
| Recommended tools | `RunAzCliReadCommands`, `QueryLogAnalyticsByWorkspaceId`, `GetAzCliHelp` |
| Recommended knowledge files | `documentation/terraform-design.md`, `documentation/troubleshooting-scenarios.md`, `documentation/architecture.md`, `documentation/kql-catalog.md`, `Student/Resources/scenarios/scripts/trigger-udr-asymmetry.sh`, `Student/Resources/scenarios/scripts/restore-udr-asymmetry.sh` |
| Default run mode | Review for restore/remediation; read-only diagnostics can run autonomously if allowed |

## Operating Principles

1. Determine expected path from Terraform before diagnosing live path.
2. Use Next hop/effective routes for point-in-time routing truth.
3. Use Traffic Analytics for historical flow evidence, not for route-table source of truth.
4. Distinguish demo route overlays from persistent Terraform-managed route tables.
5. Do not change route tables without Review-mode approval.

## Official References

- Network Watcher Next hop: https://learn.microsoft.com/en-us/azure/network-watcher/network-watcher-next-hop-overview
- Network Watcher overview: https://learn.microsoft.com/en-us/azure/network-watcher/network-watcher-monitoring-overview
- Traffic Analytics overview: https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics
- VNet Flow Logs overview: https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-overview

## Trigger Conditions

Load this skill when:

- The user ran `Student/Resources/scenarios/scripts/trigger-udr-asymmetry.sh`.
- A route table sends traffic to `None`, wrong appliance, wrong firewall, or internet unexpectedly.
- Client-to-DB or app-to-data traffic fails while NSG appears allowed.
- Traffic Analytics shows one-way traffic or unusual byte asymmetry.
- `IsFlowCapturedAtUDRHop` is relevant.
- The agent needs to compare effective routes against Terraform route tables.

## Non-Goals

- Do not modify route tables or associations automatically.
- Do not infer asymmetric routing solely from unequal byte counters.
- Do not ignore NSG/firewall evidence; routing and filtering can both contribute.
- Do not assume the NVA is the default path; the lab defaults to Azure Firewall centralized routing when enabled.

## Procedure

### Step 1: Identify expected topology

Read project knowledge and Terraform:

- `terraform/network.tf` for route tables and associations.
- `documentation/terraform-design.md` for routing design.
- `enable_centralized_firewall_routing` expected value.
- Azure Firewall private IP from Terraform output.

Expected default when centralized routing is enabled:

- App/data spokes use UDRs toward Azure Firewall private IP.
- Temporary demo route may add a more specific route to `None`.

### Step 2: Identify source/destination pair

Common demo pair:

- Source client: `10.20.1.10`.
- Destination DB listener: `10.30.2.10`.
- Destination port: `5432`.

### Step 3: Query UDR/asymmetry evidence

```kql
NTANetAnalytics
| where SubType == "FlowLog" and TimeGenerated > ago(24h)
| where SrcIp in ("10.20.1.10", "10.30.2.10") or DestIp in ("10.20.1.10", "10.30.2.10")
| project TimeGenerated, SrcIp, DestIp, DestPort, FlowDirection, FlowStatus, BytesSrcToDest, BytesDestToSrc, IsFlowCapturedAtUDRHop, SrcSubnet, DestSubnet
| order by TimeGenerated desc
```

### Step 4: Check effective routes

Use the source NIC first, then destination NIC if reverse path matters.

```bash
az network nic show-effective-route-table \
  --resource-group <resource-group-name> \
  --name <source-nic-name> \
  --output table
```

### Step 5: Check next hop

```bash
az network watcher show-next-hop \
  --resource-group <source-vm-resource-group> \
  --vm <source-vm-name> \
  --source-ip <source-private-ip> \
  --dest-ip <destination-private-ip>
```

Interpretation:

| Next hop | Meaning |
| --- | --- |
| `VirtualAppliance` with firewall private IP | Expected centralized firewall route. |
| `None` | Route table blackhole, likely demo UDR fault if recent. |
| `VnetLocal` | Same VNet path or no forced route. Check whether expected. |
| `Internet` | Public path. Usually unexpected for private spoke-to-spoke traffic. |

### Step 6: Check route table rules

```bash
az network route-table route list \
  --resource-group <resource-group-name> \
  --route-table-name <route-table-name> \
  --output table
```

Look for:

- More specific routes overriding default route.
- `nextHopType` set to `None`.
- Wrong virtual appliance IP.
- Missing route association.

### Step 7: Determine if it is demo-controlled

If the temporary route matches the script behavior, recommend:

```bash
Student/Resources/scenarios/scripts/restore-udr-asymmetry.sh
```

Only execute after approval.

## Classification

| Classification | Evidence | Next action |
| --- | --- | --- |
| Healthy centralized routing | Next hop is expected firewall private IP; flows allowed. | Continue application/service checks. |
| Demo blackhole | More specific route to `None` from trigger script. | Recommend restore script in Review mode. |
| Wrong appliance | Next hop is unexpected appliance/IP. | Compare route tables with Terraform. |
| Missing association | Subnet lacks expected route table. | Review Terraform associations. |
| Asymmetry suspected | Forward/reverse path differ or only one direction observed. | Check both source and destination effective routes. |
| Filtering not routing | Next hop expected but flow denied. | Hand off to `nsg-deny-flow-investigation`. |

## Evidence Required

- Source/destination IPs and ports.
- Expected route from Terraform.
- Effective route table output.
- Next hop output.
- Traffic Analytics query result.
- Route table name and route entry, if relevant.
- Whether demo trigger script was used.

## Output Format

```markdown
## Routing Finding
<Healthy | Demo blackhole | Wrong appliance | Missing route association | Asymmetry suspected | Filtering issue | Unknown>

## Expected Path
<from Terraform/project docs>

## Observed Path
- Effective route:
- Next hop:
- Traffic Analytics evidence:

## Root Cause Hypothesis
<explanation and confidence>

## Recommended Action
<read-only next check | restore script | Terraform review | Review-mode route change>

## References
- documentation/terraform-design.md
- documentation/troubleshooting-scenarios.md
- <official source>
```

## Escalation Criteria

Escalate when:

- Production-like routing changes are required.
- Route state conflicts with Terraform and no demo script explains it.
- Azure Firewall or NVA policy must be changed.
- Asymmetry remains after route table evidence appears healthy.
- The next hop result indicates platform or unsupported behavior.

## Related Skills

- `connectivity-diagnostics`
- `traffic-analytics-kql-analysis`
- `nsg-deny-flow-investigation`
- `vnet-flow-logs-and-ingestion`
