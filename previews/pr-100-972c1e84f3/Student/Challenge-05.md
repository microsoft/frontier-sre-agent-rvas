[< Previous Challenge](./Challenge-04.md) — **[Home](../README.md)** — [Next Challenge >](./Challenge-06.md)

# Challenge 05 — Discover Specialist Agents

> **Application focus:** Grubify (Sample Food) and Parking Manager

> **Capabilities added in this challenge**: Subagents

## Introduction

The main agent handles network, application, cost, and code questions with one configuration. Subagents let you give each domain its own instructions, tools, and runbooks.

Invoke a named subagent to use its domain-specific configuration. In Challenge 06, incident filter rules will route incoming alerts to these subagents automatically.

## Description

### Step 1 — Ask a domain-specific question (before subagents)

> **Syntax note:** `/agent <name>` routes your next prompt to a named specialist. Type `/agent` (no name) to return to the main agent. You can also use `@<name>:` as a prefix inline. Both forms are introduced in this challenge.

In the SRE Agent portal, ask:

```text
/agent network-traffic-analyst

What are the first 5 steps you would take to investigate a database connectivity failure from the app tier?
```

Without subagents configured, `/agent network-traffic-analyst` will fail or give a generalist answer — no specialist with that name exists.

Also ask the main agent to investigate a network issue. Compare its answer with the specialist's VNet Flow Log queries and effective-route analysis after deployment.

### Step 2 — Add the subagents

Apply the subagent YAMLs from `Student/Resources/azure-sre-agent-config/subagents/`:

```bash
make subagents
```

Verify in the portal under **Subagents** — you should see all **12** listed.

### Step 3 — Invoke the network specialist

```text
/agent network-traffic-analyst

What are the first 5 steps you would take to investigate a database connectivity failure from the app tier?
```

Look for VNet Flow Log queries, effective route checks, NSG rule analysis, and next-hop validation.

Compare this response to what the main agent gave in Step 1.

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

The agent should list all **11** specialists. The roster includes:

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

### Step 6 — Inspect a subagent definition in the portal

In the portal under **Sub Agents**, click `network-traffic-analyst` to view its configuration. Note how the `system_prompt` or `instructions`, `skills`, and `tools` fields define its network investigation scope.

## Success Criteria

- [ ] Before adding subagents, `/agent network-traffic-analyst` fails with "not found"
- [ ] After adding subagents, the network specialist gives a precise domain-specific investigation plan
- [ ] The Container Apps specialist gives a Container Apps-specific investigation plan
- [ ] The main agent lists all **11** specialists with correct domains
- [ ] **Explain to your coach** — what prevents a subagent from calling tools outside its configured toolset? What is the governance benefit of narrow tool grants on a specialist?

## Learning Resources

- [Azure SRE Agent — subagents](https://learn.microsoft.com/en-us/azure/sre-agent/sub-agents)
- [Azure SRE Agent — agent routing](https://learn.microsoft.com/en-us/azure/sre-agent/automate-incidents)
- [Azure SRE Agent — overview](https://learn.microsoft.com/en-us/azure/sre-agent/overview)

## Tips

- The `system_prompt` field defines the specialist's role and investigation approach. Read it alongside the tool grants and skills.
- You invoke a specialist with `/agent <name>`. Use `@<name>:` as an inline prefix for the same effect. Type `/agent` (no name) to return to the main agent.
- After this challenge: the agent has identity, knowledge, skills, connectors, and domain specialists — but all interactions are still chat-driven. Alerts don't automatically trigger investigations yet. That's Challenge 06.
