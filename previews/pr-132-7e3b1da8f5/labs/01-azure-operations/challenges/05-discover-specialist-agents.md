---
title: Discover Specialist Agents
summary: Add domain-specific subagents with their own instructions, tools, and runbooks. Compare their investigation plans with the main agent's.
phase: Config
group: Agent configuration
tags:
- subagents
- agent routing
- specialist
highlight: false
---

# Challenge 05 — Discover Specialist Agents

> **Application focus:** Grubify (Sample Food) and Parking Manager

> **Capabilities added in this challenge**: Subagents

## Purpose

- Pick two subagents and state, from their configuration, which tools and skills each may use and which incident types each owns.
- This sets up incident routing in the next challenge, where alerts go to specialists instead of a generic assistant.
- Expected time: 20 minutes.

## Introduction

The main agent handles network, application, cost, and code questions with one configuration. Subagents give each domain its own instructions, tools, and runbooks.

You invoke a named subagent to use its configuration. In Challenge 06, incident filter rules route incoming alerts to these subagents automatically.

## Description

### Step 1 — Ask a domain-specific question (before subagents)

> **Syntax note:** `/agent <name>` routes your next prompt to a named specialist. Type `/agent` (no name) to return to the main agent. You can also use `@<name>:` as a prefix inline. Both forms are introduced in this challenge.

In the SRE Agent portal, ask:

```text
/agent network-traffic-analyst

What are the first 5 steps you would take to investigate a database connectivity failure from the app tier?
```

Without subagents, `/agent network-traffic-analyst` fails or gives a generalist answer, because no specialist with that name exists.

Also ask the main agent to investigate a network issue. After you add the subagents, compare its answer with the specialist's VNet Flow Log queries and effective-route analysis.

### Step 2 — Add the subagents

Apply the subagent YAMLs from `labs/01-azure-operations/resources/azure-sre-agent-config/subagents/`:

```bash
make subagents
```

Verify in the portal under **Subagents**. All **14** should be listed.

### Step 3 — Invoke the network specialist

```text
/agent network-traffic-analyst

What are the first 5 steps you would take to investigate a database connectivity failure from the app tier?
```

Look for VNet Flow Log queries, effective route checks, NSG rule analysis, and next-hop validation.

Compare this response with the main agent's answer from Step 1.

### Step 4 — Invoke the app specialist

```text
/agent aca-app-incident-handler

The Grubify API is returning HTTP 503. Walk me through your first 3 investigation steps.
```

Look for `ContainerAppHTTPLogs` queries, replica health checks, and ingress status.

### Step 5 — Understand the specialist roster

Back in the main agent, ask:

```text
What specialist subagents are available? For each one, describe their domain, their tools, and what type of alert or question routes to them.
```

The agent should list all **14** specialists. The roster includes:

| Specialist | Domain |
|---|---|
| `network-traffic-analyst` | VNet flows, NSGs, UDRs, routing forensics |
| `aca-app-incident-handler` | Container Apps HTTP errors, OOM, replica health |
| `iaas-vm-incident-handler` | Guest OS failures, Syslog, VM run-command |
| `code-analyzer` | Source code correlation, GitHub issues and PRs |
| `issue-triager` | GitHub issue triage and labelling |
| `cost-optimization-agent` | FinOps, Advisor, Resource Graph |
| `azure-resource-config-auditor` | RBAC, resource configuration audits |
| `access-to-3rd-party-logs` | Berlin Parking API third-party telemetry (MCP) |
| `dependency-analyzer` | Application dependency topology, App Insights |
| `madrid-api` | Madrid Parking API on Windows VMs (Event logs) |
| `paris-api` | Paris Parking API on Linux VMs (Syslog) |
| `parking-vm-incident-handler` | Paris Parking API service-down incidents; restarts the VM and validates recovery |
| `parking-vm-incident-reporter` | Parking VM unhealthy alerts; creates or updates the GitHub issue |
| `agent-quality-reviewer` | Read-only review of the agent's own investigation quality |

### Step 6 — Inspect a subagent definition in the portal

In the portal under **Sub Agents**, click `network-traffic-analyst` to view its configuration. The `system_prompt` or `instructions`, `skills`, and `tools` fields define its network investigation scope.

## Success Criteria

- [ ] Before adding subagents, `/agent network-traffic-analyst` fails with "not found"
- [ ] After adding subagents, the network specialist gives a precise domain-specific investigation plan
- [ ] The Container Apps specialist gives a Container Apps-specific investigation plan
- [ ] The main agent lists all **14** specialists with correct domains
- [ ] **Explain in your own words** (two or three written sentences) — what prevents a subagent from calling tools outside its configured toolset? What is the governance benefit of narrow tool grants on a specialist?

## Learning Resources

- [Azure SRE Agent — subagents](https://learn.microsoft.com/en-us/azure/sre-agent/sub-agents)
- [Azure SRE Agent — agent routing](https://learn.microsoft.com/en-us/azure/sre-agent/automate-incidents)
- [Azure SRE Agent — overview](https://learn.microsoft.com/en-us/azure/sre-agent/overview)

## Tips

- The `system_prompt` field defines the specialist's role and investigation approach. Read it alongside the tool grants and skills.
- Invoke a specialist with `/agent <name>`, or use `@<name>:` as an inline prefix. Type `/agent` (no name) to return to the main agent.
- The agent now has identity, knowledge, skills, connectors, and domain specialists, but every interaction is still chat-driven. Alerts don't trigger investigations yet. That's Challenge 06.

## Hints and notes

> Hidden until you click. Expand a section only when you want it.

<details>
<summary><strong>Background</strong></summary>

- Six primary specialists in the certified roster: `aca-app-incident-handler`, `iaas-vm-incident-handler`, `network-traffic-analyst`, `code-analyzer`, `issue-triager`, and `cost-optimization-agent`.
- Before configuration, `/agent network-traffic-analyst` fails. Afterward it should answer with `NTANetAnalytics`, routes, NSGs, and next-hop language.
- Narrow tool grants are a governance feature, not a limitation.
- A useful sketch: main agent → specialist roster → each specialist owns a failure domain.

</details>

<details>
<summary><strong>Expected Output</strong></summary>

- Portal shows all **14** certified subagents after `make subagents`.
- `/agent network-traffic-analyst` returns domain-specific network investigation steps.
- `/agent aca-app-incident-handler` returns Container Apps-specific investigation steps.
- You can explain why a scoped system prompt changes answer quality.

</details>

<details>
<summary><strong>Common Issues and Hints</strong></summary>

- **Symptom:** `/agent network-traffic-analyst` not found. **Fix:** the subagents were not applied, or the portal needs a refresh.
- **Symptom:** Specialist still sounds generic. **Fix:** use a prompt in its exact domain, e.g. routing/NSG for network or HTTP 503 for ACA.
- **Symptom:** You confuse skills and subagents. **Fix:** the subagent is the specialist identity; skills are the tools and runbooks it may use.
- **Symptom:** GitHub specialist can clone code but cannot create an issue. **Fix:** verify the `github-mcp` connector is authorized (OAuth) and that its `mcp_tools` list includes the needed `github-mcp_*` write tools (e.g. `github-mcp_create_pull_request`).

</details>

<details>
<summary><strong>Debrief Discussion Guide</strong></summary>

- What does a subagent add beyond skills alone? → Prioritization, persona, scope, and domain-specific instructions.
- Why not give every tool to every specialist? → Smaller blast radius and clearer accountability.
- Which specialist seems most reusable across multiple challenges? → Usually `network-traffic-analyst`.

</details>
