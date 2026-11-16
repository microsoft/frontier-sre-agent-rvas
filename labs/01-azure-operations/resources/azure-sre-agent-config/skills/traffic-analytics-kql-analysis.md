---
name: traffic-analytics-kql-analysis
description: Query and interpret Traffic Analytics records for network troubleshooting in the VNet Flow Logs demo lab.
---

# traffic-analytics-kql-analysis

Use this skill when analyzing Azure Traffic Analytics data in Log Analytics, especially `NTANetAnalytics`, top talkers, denied flows, allowed flows, ports, protocols, public traffic, bidirectional conversations, or unexpected flow volume.

## Trigger Conditions

Load this skill when the user asks about:

- Top talkers.
- Denied flows.
- Allowed vs blocked traffic.
- Flow direction.
- Traffic between client, web, API, DB, Azure Firewall or Private Endpoint.
- Unexpected public or internet traffic.
- TCP/UDP comparison.
- Traffic Analytics fields or `NTANetAnalytics` query design.
- KQL evidence for an incident response plan.

## Non-Goals

- Do not change alert rules, retention or flow-log settings.
- Do not treat Traffic Analytics as packet capture or application log analysis.
- Do not assume reverse traffic is always a separate row; return traffic can be represented by `BytesDestToSrc` and `PacketsDestToSrc` in the same flow tuple.

## Reference Files

Read these on demand instead of recalling field names or query shapes from memory. Each path below is the exact name the file is registered under:

- `traffic-analytics-kql-analysis/references/schema-fields.md` contains table and field semantics plus the field traps that silently invert a conclusion.
- `traffic-analytics-kql-analysis/references/kql-library.md` contains the approved, executable query library.

## Procedure

1. Confirm the user question and identify the time range. Default to last 24 hours unless the incident provides a more precise window.
2. Confirm the Log Analytics workspace from Terraform output or agent context.
3. Open `traffic-analytics-kql-analysis/references/kql-library.md` and use it as the executable source of truth. Do not invent a query when an approved one covers the question.
4. Start with a freshness query before deeper analysis.
5. Select a targeted query pattern:
   - Top talkers.
   - Denied flows by rule.
   - Subnet-to-subnet conversations.
   - Public or malicious traffic.
   - Endpoint-to-endpoint forward/reverse/bidirectional view.
   - UDR/asymmetry signal.
6. Map IP addresses to project VM roles using Terraform outputs and Azure resource data.
7. Interpret allowed/denied, bytes, ports and protocol using the project baseline.
8. Produce query, evidence and conclusion. Do not recommend changes without Review mode.

## Interpretation Rules

- `FlowStatus contains "Denied"` (or `DeniedInFlows > 0` / `DeniedOutFlows > 0`) indicates denied traffic; the field stores the full word `Denied`, not the single letter `D`.
- `FlowStatus contains "Allowed"` indicates allowed traffic (full word `Allowed`, not `A`).
- `L4Protocol == "T"` indicates TCP and `L4Protocol == "U"` indicates UDP.
- High `BytesSrcToDest` and low `BytesDestToSrc` can indicate asymmetric behavior, one-way traffic, blocked return, or normal one-directional traffic depending on protocol/application.
- Absence of separate reverse rows does not prove no return traffic. Check `BytesDestToSrc` and `PacketsDestToSrc`.
- Traffic Analytics is aggregated and delayed; always report the query time window and latest `TimeGenerated`.

## Evidence Required

- Workspace and table queried.
- Time range.
- Full KQL query.
- Record count.
- Top IPs, ports, protocols and flow status.
- Mapping to VM/service names where possible.
- Whether the finding matches expected project baseline.

## Output Format

```text
Question interpreted as: <analysis goal>
Time range: <range>
KQL used:
<query>
Key results:
- <result 1>
- <result 2>
Interpretation: <what it means>
Root cause hypothesis: <if applicable>
Confidence: High | Medium | Low
Next step: <read-only validation or active-trigger-permitted remediation>
References:
- `traffic-analytics-kql-analysis/references/kql-library.md`
- <official Microsoft URL>
```

## Escalation

Escalate when:

- Query returns no data but flow logs and traffic generation are expected.
- Required fields are absent or schema differs from documented project schema.
- Traffic is classified as malicious or policy-sensitive.
- The next step requires changing NSG, route table, flow log, workspace, Storage or alert configuration.

## Official Sources

- Traffic Analytics overview: https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics
- Traffic Analytics schema: https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-schema
- Traffic Analytics queries: https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-queries
- Log Analytics API: https://learn.microsoft.com/en-us/azure/azure-monitor/logs/api/overview