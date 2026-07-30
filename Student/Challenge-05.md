[< Previous Challenge](./Challenge-04.md) — **[Home](../README.md)** — [Next Challenge >](./Challenge-06.md)

# Challenge 05 — Discover Specialist Agents

> **Capabilities added in this challenge**: Subagents

## Introduction

Your agent is generalist. It handles everything — network, application, cost, code analysis — with the same set of tools and the same system prompt. For simple queries this works, but for complex domain investigations it's a problem: a generalist network diagnosis is shallower than one done by an agent whose entire identity, toolset, and runbooks are focused on network forensics.

**Subagents** are named domain specialists. Each has a scoped system prompt, a curated toolset, and a deep knowledge of one failure domain. When you invoke one, you're handing the investigation to an expert — and the agent platform routes incoming alerts to the right expert automatically, based on incident filter rules you'll configure in Challenge 06.

## Description

### Step 1 — Ask a domain-specific question (before subagents)

> **Syntax note:** `/agent <name>` routes your next prompt to a named specialist. Type `/agent` (no name) to return to the main agent. You can also use `@<name>:` as a prefix inline. Both forms are introduced in this challenge.

In the SRE Agent portal, ask:

```text
/agent network-traffic-analyst

What are the first 5 steps you would take to investigate a database connectivity failure from the app tier?
```

Without subagents configured, `/agent network-traffic-analyst` will fail — no specialist with that name exists.

Also note: if you ask the main agent to investigate a network issue, it answers with generic advice rather than the precise VNet Flow Log KQL queries and effective-route analysis a real network specialist would start with.

### Step 2 — Add the subagents

Apply the subagent YAMLs from `Student/Resources/azure-sre-agent-config/subagents/`:

```bash
make subagents
```

Verify in the portal under **Subagents** — you should see all **11** listed.

### Step 3 — Invoke the network specialist

```text
/agent network-traffic-analyst

What are the first 5 steps you would take to investigate a database connectivity failure from the app tier?
```

Now you get a network-expert response: VNet Flow Log queries, effective route checks, NSG rule analysis, next-hop validation — not generic advice.

Compare this response to what the main agent gave in Step 1.

### Step 4 — Invoke the app specialist

```text
/agent aca-app-incident-handler

The Grubify API is returning HTTP 503. Walk me through your first 3 investigation steps.
```

The Container Apps specialist will jump directly to `ContainerAppHTTPLogs` KQL, replica health, and ingress status — exactly what a Container Apps expert would do.

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

In the portal under **Subagents**, click `network-traffic-analyst` to view its configuration. Note the `system_prompt`, `skills`, and `tools` fields. The system prompt is what makes this agent a network expert rather than a generalist.

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

- The `system_prompt` field in the subagent YAML is the most important field. It is what makes a specialist an expert rather than a generalist with a different name.
- You invoke a specialist with `/agent <name>`. Use `@<name>:` as an inline prefix for the same effect. Type `/agent` (no name) to return to the main agent.
- After this challenge: the agent has identity, knowledge, skills, connectors, and domain specialists — but all interactions are still chat-driven. Alerts don't automatically trigger investigations yet. That's Challenge 06.
