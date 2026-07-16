[< Previous Challenge](./Challenge-01.md) — **[Home](../README.md)** — [Next Challenge >](./Challenge-03.md)

# Challenge 02 — Subagents & Incident Filters

## Introduction

A **skill** gives the agent a procedure. A **subagent** gives the agent a *personality and a domain* — a specialist with its own system prompt, tool grants, and assigned incident response scope. An **incident filter** is the routing rule that connects an incoming Azure Monitor alert to the right subagent.

Together, subagents and incident filters are how the SRE Agent implements **domain-based routing**: each failure domain (PaaS app, IaaS VM, network) has exactly one owner, and alerts are routed there based on title matching.

In this challenge you will create a minimal subagent and wire it to an incident filter — the same way the lab's 7 pre-built subagents were created.

## Description

### Step 1 — Understand the subagent YAML format

Open an existing subagent as a reference:

```bash
cat Coach/Solutions/azure-sre-agent-config/subagents/azure-resource-config-auditor.yaml
```

Key fields:
```yaml
api_version: azuresre.ai/v1
kind: SubAgent
metadata:
  name: <unique-name>
spec:
  description: <what this agent does and owns>
  agentMode: Autonomous        # or Interactive
  system_prompt: |
    You are a specialist SRE agent responsible for ...
    When you receive an incident, you will:
    1. ...
    2. ...
  tools:
    - RunAzCliReadCommands
    - QueryLogAnalyticsByWorkspaceId
    - SearchMemory
  skills:
    - <skill-name>             # optional: reference skills this agent uses
```

> **`agentMode: Autonomous`** means the agent acts without a human prompt after the incident arrives. **`Interactive`** means it waits for a user to ask it questions.

### Step 2 — Write a subagent for a new domain

Create `Coach/Solutions/azure-sre-agent-config/subagents/<your-agent-name>.yaml`.

Ideas for a new minimal domain:
- A **storage-auditor** that checks for public blob containers or missing lifecycle policies
- A **certificate-expiry-watcher** that scans Key Vault certificates nearing expiry
- A **compute-quota-checker** that reports vCPU usage vs. subscription limits

Your subagent's system prompt should:
1. State what failure domain it owns
2. Describe its investigation procedure (step-by-step)
3. State what output to produce (incident summary, recommended action)

Keep `tools` to `read_only` commands unless you specifically need write capability.

### Step 3 — Write an incident filter to route alerts to your subagent

Incident filters connect Azure Monitor alerts to subagents via **title matching**.

Open an existing filter as a reference:
```bash
cat Coach/Solutions/azure-sre-agent-config/automations/incident-filters/sample-food-http-errors.yaml
```

Key fields:
```yaml
api_version: azuresre.ai/v1
kind: IncidentFilter
metadata:
  name: <unique-name>
spec:
  incidentPlatform: AzMonitor
  isEnabled: true
  priorities:
    - Sev2
  titleContains: <keyword>     # case-insensitive match on alert title
  handlingAgent: <your-agent-name>
  agentMode: Autonomous        # or Interactive
  maxAutomatedInvestigationAttempts: 3
  customInstructions: >-
    <optional context injected into the agent's prompt when this filter matches>
```

Create `Coach/Solutions/azure-sre-agent-config/automations/incident-filters/<your-filter-name>.yaml`.

Choose a `titleContains` keyword that:
- Matches the Azure Monitor alert name you would create for this domain
- Does **not** overlap with existing filters (`food`, `nginx`, and the network filter's `titleNotContains` logic)

### Step 4 — Apply both resources

```bash
cd Coach/Solutions
./infra/scripts/sre-agent-config.sh apply --target subagents --name <your-agent-name>
./infra/scripts/sre-agent-config.sh apply --target incident-filters --name <your-filter-name>
```

### Step 5 — Verify in portal

1. Navigate to **Subagents** — confirm your new subagent appears
2. Navigate to **Incident Filters** — confirm your filter appears with the correct `titleContains` and `handlingAgent`
3. Test routing: in the portal chat window addressed to your subagent, send a prompt describing a fake incident — verify the agent responds using its system prompt persona

## Success Criteria

- [ ] A valid `<agent-name>.yaml` exists under `subagents/` and appears in the portal
- [ ] A valid `<filter-name>.yaml` exists under `automations/incident-filters/` and appears in the portal
- [ ] You can explain the **domain-routing architecture**: why each incident filter owns a non-overlapping failure domain
- [ ] You can explain the difference between `agentMode: Autonomous` and `agentMode: Interactive`
- [ ] You can explain what happens if two incident filters match the same alert title (and why the lab avoids this)

## Learning Resources

- [Azure SRE Agent — Subagents documentation](https://learn.microsoft.com/en-us/azure/sre-agent/subagents)
- [Azure SRE Agent — Incident filters](https://learn.microsoft.com/en-us/azure/sre-agent/incident-filters)
- Existing subagents in `Coach/Solutions/azure-sre-agent-config/subagents/`
- Existing filters in `Coach/Solutions/azure-sre-agent-config/automations/incident-filters/`

## Tips

- **System prompt quality matters more than tool grants.** A verbose, well-structured system prompt produces consistent agent behavior. Vague prompts produce vague responses.
- The `handlingAgent` value in the incident filter must exactly match the `metadata.name` in the subagent YAML.
- `agentMode: Autonomous` in the incident filter must match (or be compatible with) the `agentMode` in the subagent.
- The `maxAutomatedInvestigationAttempts: 3` limit prevents runaway retries — keep it at 3 for lab use.
- Agent-to-agent handoffs (`handoffs:`) are **not supported** in workspace mode. If you need cross-domain capability, inline it in the system prompt (see how `aca-app-incident-handler` handles code analysis).
