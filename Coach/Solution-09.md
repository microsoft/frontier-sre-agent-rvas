[< Previous Solution](./Solution-08.md) | **[Home](./README.md)**

# Coach Guide — Challenge 06: Autonomous NSG Remediation

## Purpose

This challenge closes the loop on the interactive ↔ autonomous spectrum: the agent **acts without being prompted**, applying VNet Flow Log evidence to identify and remove a malicious/misconfigured NSG deny rule that blocks database traffic. It is the highest-stakes scenario in the workshop — an agent that modifies network security policy with no human in the loop.

Expected time: **20–25 minutes** including alert propagation (~10 min delay for flow logs).

## Mini-Lecture (5 min before challenge)

Cover:
- The `network-observability-review` incident filter: `titleNotContains: nginx` AND doesn't match food filter → catches broad network alerts
- The NSG deny rule: a high-priority deny rule blocking port 5432 (PostgreSQL) from the app subnet to the database subnet
- The evidence trail: `NTANetAnalytics | where FlowStatus == "D" and DestPort == 5432` — shows denied flows with source/dest subnet
- The autonomous remediation: `az network nsg rule delete` — the agent identifies the specific rule and removes it
- **The governance provocation**: this agent has `RunAzCliWriteCommands` — in production, this would require approval gates, change record creation, and post-remediation verification

## Expected Agent Behavior

1. Agent receives network-observability alert (fired when denied DB flows exceed threshold)
2. Queries `NTANetAnalytics`: finds denied flows on port 5432 between app-subnet → db-subnet
3. Queries the NSG rules: `az network nsg rule list --nsg-name nsg-db`
4. Identifies the high-priority deny rule (`DenyAppToDb` or similar)
5. Deletes the rule: `az network nsg rule delete --nsg-name nsg-db --name DenyAppToDb --resource-group <rg>`
6. Verifies: queries flow logs again (or runs a connectivity test) to confirm traffic is flowing
7. Reports: incident summary with rule name, justification (flow log evidence), action taken

## Common Issues and Hints

### Alert doesn't fire — flows are not reaching the threshold
- Verify `generate-baseline-traffic.sh` has been running to generate DB queries (port 5432 traffic)
- Without baseline traffic hitting the deny rule, there are no denied flows → no alert
- Coach fallback: trigger via portal chat: "I'm seeing DB connection timeouts in Grubify. Investigate network denies on port 5432 and remediate"

### Agent identifies the rule but won't delete it
- The agent system prompt is scoped to autonomous remediation — but if the rule name or NSG name doesn't match what the agent expects, it may pause and report
- Prompt: "Confirm it's safe to remove and proceed"
- If the agent still won't proceed: have the student prompt from the portal chat window explicitly

### Agent deletes the wrong rule
- This is a real risk worth discussing. If the agent deletes a legitimate security rule, the fix is `restore-nsg-block.sh` (which removes the injected rule and re-adds any legitimate baseline)
- In this workshop environment, all NSG rules are managed by Terraform — any agent-deleted rule will be restored on `terraform apply`

### Flow logs show delayed evidence
- Same 10-minute Traffic Analytics delay as S5
- Coach action: trigger the NSG block at least 10 minutes before telling students to watch for the alert

## KQL Reference for Coach

```kusto
// Show denied flows on DB port
NTANetAnalytics
| where TimeGenerated > ago(1h)
| where FlowStatus == "D" and DestPort == 5432
| project TimeGenerated, SrcIp, SrcSubnet, DestIp, DestSubnet, DestPort, BytesSentD_A

// Confirm remediation (flows now active)
NTANetAnalytics
| where TimeGenerated > ago(30m)
| where DestPort == 5432
| summarize by FlowStatus, SrcSubnet, DestSubnet
```

## Autonomous vs Interactive Contrast (Debrief)

This is the central debrief topic — use Challenge 05 and 06 together as a case study:

| Dimension | S5 Interactive | S6 Autonomous |
|---|---|---|
| Human involvement | Student drives every step | No human prompt after alert |
| Speed to remediation | 15–25 min (conversation) | 5–8 min (agent acts immediately) |
| Explainability | Complete conversation log | Agent-generated incident report |
| Risk | Human can course-correct at each step | Agent may make wrong call |
| Appropriate for | Policy decisions, ambiguous causes, high blast radius | Well-understood, low-variance failure modes |

Key question for discussion: **"What would it take for your organization to trust an agent to do what S6 just did?"** — Answers cluster around: audit trail, rollback mechanism, blast radius limits, escalation path, pre-approved remediation playbooks.

## Debrief Discussion Guide (10 min)

1. **How did you feel watching the agent modify a security rule?** — This surfaces the governance instinct; validate the concern
2. **Is this any different from a runbook automation (e.g., Azure Automation, Logic App)?** — Not technically; the difference is reasoning under uncertainty and evidence synthesis
3. **What guardrails would you add?** — Time-boxed autonomy ("only remove rules that match these patterns"), mandatory approval for Priority < 100, pre-notification, auto-revert if connectivity not restored within 5 min
4. **Contrast with S5**: same tools, same data, very different mode — the deciding factor is the incident trigger pattern, not the agent capability

## Success Criteria Notes

- The agent must identify the specific NSG rule (name + priority) from flow log evidence — not just guess
- Accept partial credit if the agent produces the KQL query + NSG rule identification without actually deleting (happens if alert didn't fire and student used chat)
- Restore: `Student/Resources/scenarios/scripts/restore-nsg-block.sh` — run this even if the agent already removed the rule (script is idempotent)
