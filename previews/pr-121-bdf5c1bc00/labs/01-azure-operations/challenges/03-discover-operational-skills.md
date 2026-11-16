---
title: Discover Operational Skills
summary: Add the supplied skills so the agent can run KQL queries, inspect Container App health, and follow operational runbooks. Test its tool and approval boundaries.
phase: Config
group: Agent configuration
tags:
- skill YAML
- runbooks
- KQL
highlight: false
---

# Challenge 03 — Discover Operational Skills

> **Application focus:** Infrastructure/platform only

> **Capabilities added in this challenge**: Skills

## Purpose

- Show that a loaded skill changes the agent's behavior: it runs real queries instead of only describing an investigation.
- Name the tools one skill declares and explain what the agent can't do because of that list.
- Expected time: 20 minutes.

## Introduction

Your agent can answer questions from documentation (Challenge 02). Now test whether it can run a KQL query or check a Container App's health before you add the investigation skills.

Each skill defines an investigation procedure and its tools, such as specific `az` commands, KQL queries, or REST calls. The agent follows the skill's runbook. Tool grants, subagent instructions, and invocation mode govern what it can do.

## Description

### Step 1 — Ask the agent to investigate (before skills)

In the SRE Agent portal, ask:

```text
Investigate the current health of the Grubify Container App. Check for any active errors or anomalies.
```

Note whether the agent only describes an investigation or actually runs queries and commands.

Also ask:

```text
Show me the denied network flows in the last hour.
```

The same problem applies: the agent knows what Traffic Analytics is but has no tools to query it.

### Step 2 — Add the skills

Apply the skill YAMLs from `labs/01-azure-operations/resources/azure-sre-agent-config/skills/`:

```bash
make skills
```

Verify custom skills under **Skills** in the portal — you should see 10 skills listed.

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

This probes the boundary between autonomous and approval-gated action. The agent should
explain that skills only declare read/write tools and a natural-language runbook; the skill has no
`safety` block. Autonomy is governed elsewhere: by which tools a skill lists
(e.g. `RunAzCliReadCommands` vs. write commands), by the subagent's own instructions, and by the
`agentMode` (`Review` vs. `Autonomous`) set on the incident filter or scheduled task that invokes it.

### Step 6 — Read a skill definition in the portal

In the portal under **Skills**, select `connectivity-diagnostics` to view its definition. Note the `tools` list and the runbook steps referenced in its files.

## Success Criteria

- [ ] Before adding skills, the agent describes investigation steps but cannot execute any
- [ ] After adding skills, the agent runs real KQL queries and returns data from the lab
- [ ] The agent lists all 10 loaded skills with correct names and purposes
- [ ] The agent correctly describes what requires approval vs. what it can do autonomously
- [ ] **Explain in your own words** (two or three written sentences) — why do skills list tools explicitly rather than giving the agent all tools? What is the security benefit of this constraint?

## Learning Resources

- [Azure SRE Agent — skills](https://learn.microsoft.com/en-us/azure/sre-agent/skills)
- [Azure SRE Agent — tool grants reference](https://learn.microsoft.com/en-us/azure/sre-agent/tools)
- [Azure Container Apps — log monitoring](https://learn.microsoft.com/en-us/azure/container-apps/log-monitoring)

## Tips

- Skills work together with knowledge documents: the skill provides the tool grants, the knowledge doc provides the runbook steps. Keep tool policy in YAML and content in Markdown.
- The `description` field is the routing signal: the agent picks a skill based on it, so make it specific.
- After this challenge: the agent can query Azure-native telemetry but still cannot reach external systems such as GitHub, Microsoft Learn, or third-party APIs. That's Challenge 04.

## Hints and notes

> Hidden until you click. Expand a section only when you want it.

<details>
<summary><strong>Background</strong></summary>

- A skill YAML has three parts: `description`, `content_file`, and `tools`.
- The ten certified skills cover: Sample Food incident analysis,
  connectivity diagnostics, Traffic Analytics, VNet Flow Log ingestion, cost optimization,
  GitHub issue triage, Linux service recovery, RBAC/resource access, source-fix delivery,
  and Parking VM issue creation.
- Routing comes from the description; least privilege comes from the tools list.
- Example dependency chain: the knowledge doc tells the agent *how* to query `NTANetAnalytics`; the skill grants `QueryLogAnalyticsByWorkspaceId` so it can run the query.

</details>

<details>
<summary><strong>Expected Output</strong></summary>

- Before loading skills, the agent describes investigations without executing them.
- After `make skills`, the portal shows ten skills.
- The agent invokes a real skill and returns live data for Grubify or network flow questions.
- You can explain approval boundaries from custom-agent tool grants and response-plan or scheduled-task mode.

</details>

<details>
<summary><strong>Common Issues and Hints</strong></summary>

- **Symptom:** Skill objects exist but the agent still answers generically. **Fix:** ask a prompt tightly aligned to a skill description, e.g. denied flows or Container App health.
- **Symptom:** No live data appears. **Fix:** verify earlier validation/traffic steps and remember monitoring tables may have short ingestion lag.
- **Symptom:** You think skills themselves contain all content. **Fix:** open one `.yaml` and its paired `.md` to see the separation.
- **Symptom:** You expect the skill's local `safety` metadata to enforce runtime approval. **Fix:** check the custom agent's live tools and the trigger's Review/Autonomous mode, which are the effective controls.
- **Symptom:** There are zero denied flows in the last hour — and zero flow data of any kind in NTANetAnalytics right now. **Fix:** to generate denied flows for testing, run `make trigger-nsg-block` from the scenarios Makefile, which modifies an NSG rule to block traffic (it might take ~15 minutes to have denied traffic in the NTANetAnalytics table). After testing, run `make restore-nsg-block` to restore the NSG rule.

</details>

<details>
<summary><strong>Debrief Discussion Guide</strong></summary>

- Why explicitly list tools in a skill? → Constrains blast radius and makes capability auditable.
- Why separate skill YAML from knowledge markdown? → Policy and procedure change at different rates.
- What changed operationally after this challenge? → The agent can now query and inspect real systems, not just discuss them.

</details>
