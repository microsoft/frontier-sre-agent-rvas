[< Previous Challenge](./Challenge-02.md) — **[Home](../README.md)** — [Next Challenge >](./Challenge-04.md)

# Challenge 03 — Discover Operational Skills

> **Capabilities added in this challenge**: Skills

## Introduction

Your agent can answer questions from documentation (Challenge 02) but it cannot *act*. Ask it to run a KQL query or check a Container App's health and it will describe what it would do — but it can't actually do it, because it has no tools.

**Skills** unlock action. Each skill is a YAML file that packages a named investigation procedure, a constrained set of tools (specific `az` commands, KQL queries, REST calls), and a safety posture into a reusable capability. When a skill is loaded, the agent can execute that procedure — following the runbook, calling only the allowed tools, producing a consistent result.

## Description

### Step 1 — Ask the agent to investigate (before skills)

In the SRE Agent portal, ask:

```text
Investigate the current health of the Grubify Container App. Check for any active errors or anomalies.
```

Note the response. The agent knows *how* to investigate (from its knowledge documents) but cannot actually run any queries or commands. It's like asking an expert to examine a patient but not allowing them to touch anything.

Also ask:

```text
Show me the denied network flows in the last hour.
```

Same problem — the agent knows what Traffic Analytics is, but has no tools to query it.

### Step 2 — Add the skills

Apply the skill YAMLs from `Student/Resources/azure-sre-agent-config/skills/`:

```bash
make skills
```

Verify under **Skills** in the portal — you should see 8 skills listed.

### Step 3 — Ask the same questions again

```text
Investigate the current health of the Grubify Container App. Check for any active errors or anomalies.
```

Now the agent should:

- Invoke the `sample-food-container-app-incident-analysis` skill
- Run actual KQL queries against Container Apps HTTP logs and Application Insights
- Return real data from your lab environment

```text
Show me the denied network flows in the last hour.
```

Now the agent should:

- Invoke the `traffic-analytics-kql-analysis` skill
- Query `NTANetAnalytics` in Log Analytics
- Return actual flow data (or confirm no denied flows if the lab is clean)

### Step 4 — List what skills were loaded

```text
What skills do you have loaded? For each one, describe its purpose and the tools it uses.
```

### Step 5 — Probe the safety boundary

```text
If you found the root cause was an NSG deny rule, could you delete the rule right now without asking me?
```

This surfaces the `safety.default_mode` and `requires_approval_for_actions` fields. The agent should explain what requires approval and what it will never do autonomously.

### Step 6 — Read a skill definition in the portal

In the portal under **Skills**, click on `connectivity-diagnostics` to view its definition. Note the `tools` list, the `safety` block, and the runbook steps.

## Success Criteria

- [ ] Before adding skills, the agent describes investigation steps but cannot execute any
- [ ] After adding skills, the agent runs real KQL queries and returns data from the lab
- [ ] The agent lists all 8 loaded skills with correct names and purposes
- [ ] The agent correctly describes what requires approval vs. what it can do autonomously
- [ ] **Explain to your coach** — why do skills list tools explicitly rather than giving the agent all tools? What is the security benefit of this constraint?

## Learning Resources

- [Azure SRE Agent — skills](https://learn.microsoft.com/en-us/azure/sre-agent/skills)
- [Azure SRE Agent — tool grants reference](https://learn.microsoft.com/en-us/azure/sre-agent/tools)
- [Azure Container Apps — log monitoring](https://learn.microsoft.com/en-us/azure/container-apps/log-monitoring)

## Tips

- Skills work together with knowledge documents: the skill provides the tool grants, the knowledge doc provides the runbook steps. Separate them cleanly — tool policy in YAML, content in Markdown.
- The `description` field is the routing signal: the agent picks which skill to use based on this description. Make it specific.
- After this challenge: the agent can query Azure-native telemetry but still cannot reach external systems — GitHub, Microsoft Learn, or third-party APIs. That's Challenge 04.
