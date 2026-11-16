---
title: Build Your Own Production-Ready SRE Agent
summary: Bring a real reliability problem, build a focused agent configuration, and demonstrate an end-to-end test. Explain the controls and validation needed before production use.
phase: Capstone
group: Capstone
tags:
- Capstone
- Custom subagent
- Your use case
highlight: true
---

# Challenge 19 — Build Your Own Production-Ready SRE Agent

> **Application focus:** Infrastructure/platform only

## Purpose

- Combine skills, knowledge, subagents, routing, and governance into a use case that matters to you.
- Produce a credible design and an end-to-end demonstration. A successful lab test doesn't establish production readiness.
- Expected time: 45–60 minutes.

## Introduction

Use the skills, subagents, incident filters, connectors, and scheduled tasks you've explored to build an agent configuration for a real operations problem from your environment.

Choose the scenario, implement it, and demonstrate an end-to-end test. Treat the result as a tested prototype, and explain what further controls and validation it needs before production use.

## Description

### Step 1 — Define your use case

Choose a real reliability or operations problem from your work that currently needs manual investigation or intervention. Good candidates:

- A recurring alert that always requires the same investigation steps
- A production failure mode with a known remediation
- A proactive check that nobody does because it's tedious
- A GitHub/ADO issue triage or labelling workflow
- A cost anomaly or quota exhaustion scenario

Write a one-paragraph description of the problem:

- What triggers or indicates the problem?
- What does a human engineer do today to investigate it?
- What does a successful remediation look like?
- What tools or data sources does the investigation rely on?

### Step 2 — Design your agent configuration

Map your use case to the SRE Agent building blocks:

| Building block | What it provides | Required for your use case? |
| --- | --- | --- |
| **Skill YAML** | Tool set (read/write Azure CLI, KQL, GitHub, REST) | Define which tools the agent needs |
| **Knowledge doc** | Domain context (architecture, thresholds, runbooks) | Write a doc the agent can reference |
| **Subagent** | A named agent with a scoped system prompt | Define the agent's name, persona, and instructions |
| **Incident filter** | Routes alerts to your subagent | Only if alert-driven |
| **Connector** | Gives the agent access to a data source or action target | Only if non-standard data sources are needed |
| **Scheduled task** | Triggers the agent on a cron schedule | Only if proactive/periodic |

Sketch your design and review it critically before you write any YAML.

> **Optional:** use the `rvas-sre-agent-jumpstart` skill to design and author Step 3 for you. It interviews you about your use case, researches the Azure SRE Agent documentation for the right building blocks, and generates the skill YAML, knowledge doc, and (where applicable) IaC artifacts after you approve its plan. Install it and its two dependency skills with:
>
> ```bash
> copilot plugin marketplace add microsoft/frontier-sre-agent-rvas
> copilot plugin install rvas-sre-agent-jumpstart@rvas-sre-agent-jumpstart
> gh skill install mattpocock/skills skills/productivity/grilling --agent github-copilot
> gh skill install MicrosoftDocs/Agent-Skills skills/azure-sre-agent --agent github-copilot
> ```

### Step 3 — Implement

Write and apply the configuration.

For skills: create your `.md` runbook and `.yaml` skill definition in `labs/01-azure-operations/resources/azure-sre-agent-config/skills/`, then upload them via **Skills → Add skill** in the portal.

For subagents, incident filters, and scheduled tasks: configure them directly in the SRE Agent portal.

Use the skills and subagents you configured in Challenges 01–18 as templates.

### Step 4 — Validate

Test your agent end-to-end:

- **Alert-driven**: trigger the condition (or simulate it) and confirm the incident is routed and the agent responds correctly
- **Chat-driven**: open the SRE Agent portal and prompt your agent directly with a realistic incident description
- **Scheduled**: if applicable, trigger the scheduled task manually and confirm the output

Capture the agent's tool call log and response for your demo.

### Step 5 — Present to the group

Prepare a 3-minute demo covering:

1. The problem: what fails, how often, what the manual effort costs today
2. The design: which building blocks you used and why
3. The demo: trigger the scenario and walk through the agent's response live (or replay the captured log)
4. Production readiness: what guardrails, audit trail, or escalation path you would add before deploying this in your real environment

## Success Criteria

To complete this challenge, demonstrate:

1. A written use-case description (one paragraph minimum) that you have reviewed against the checklist below
2. At least one custom subagent with a scoped system prompt and at least one skill YAML
3. At least one knowledge doc that the agent references during its response
4. A working end-to-end test: the agent responds to the scenario with correct tool calls and a coherent remediation or analysis report
5. A 3-minute group presentation covering problem, design, demo, and production-readiness considerations
6. **Explain in your own words** (two or three written sentences): "What would need to be true — technically and organizationally — for you to deploy this agent to your production environment next week?"

## Learning Resources

- [Azure SRE Agent — skill authoring](https://learn.microsoft.com/en-us/azure/sre-agent/skills)
- [Azure SRE Agent — subagent configuration](https://learn.microsoft.com/en-us/azure/sre-agent/sub-agents)
- [Azure SRE Agent — incident filters](https://learn.microsoft.com/en-us/azure/sre-agent/automate-incidents)
- [Azure SRE Agent — knowledge docs](https://learn.microsoft.com/en-us/azure/sre-agent/connect-knowledge)
- [Azure SRE Agent — connectors](https://learn.microsoft.com/en-us/azure/sre-agent/connectors)
- [Azure SRE Agent — scheduled tasks](https://learn.microsoft.com/en-us/azure/sre-agent/scheduled-tasks)

## Tips

- **Start small.** Pick a use case that fits in a single subagent with 3–5 tool calls. Expand later.
- **Make the system prompt specific.** Define the agent's role, scope, and escalation path, then test it with the configured tools and skills.
- **Put runbook content in knowledge docs.** Thresholds, resource names, subscription IDs, known failure modes: if a human would look it up, the agent should have it.
- **Limit blast radius before adding write permissions.** Use narrow tool grants and resource permissions as well as explicit scope in the system prompt.
- **The demo is the deliverable.** A working demo with a real trigger and a coherent agent response beats a polished YAML that was never tested.

## Hints and notes

> Hidden until you click. Expand a section only when you want it.

<details>
<summary><strong>Background</strong></summary>

- Design checklist: repeating failure, known investigation path, clear remediation or escalation, measurable success signal, least-privilege tool set.
- Building blocks: skill YAML, knowledge doc, subagent, optional incident filter, optional connector, optional scheduled task.
- Keep scope narrow: one real problem solved well beats a broad but vague design.
- Production readiness: what technical and organizational conditions must hold to ship next week?

</details>

<details>
<summary><strong>Expected Output</strong></summary>

- A written use-case statement.
- At least one custom subagent and one skill YAML, plus a supporting knowledge document.
- A live or replayable end-to-end test showing correct tool use and coherent output.
- A 3-minute presentation covering problem, design, demo, and production guardrails.

</details>

<details>
<summary><strong>Common Issues and Hints</strong></summary>

- **Symptom:** Use case is too broad (“handle all outages”). **Fix:** narrow the scope to one repeating failure mode.
- **Symptom:** You jump into YAML without a clear operational procedure. **Fix:** write down the investigation, validation, and escalation path before configuring it.
- **Symptom:** You add write permissions casually. **Fix:** ask what rollback, validation, and ownership model would justify them.
- **Symptom:** Demo is purely conceptual. **Fix:** use at least one concrete test prompt, alert simulation, or captured agent log.
- **Symptom:** You are stuck mapping your use case to the building-blocks table. **Fix:** use the `rvas-sre-agent-jumpstart` skill. It interviews you and drafts the skill YAML, knowledge doc, and subagent configuration for you to review and refine.

</details>

<details>
<summary><strong>Debrief Discussion Guide</strong></summary>

- What would need to be true technically to deploy next week? → Data sources, permissions, validation signals, rollback, observability.
- What would need to be true organizationally? → Ownership, approval model, audit trail, incident policy, trust.
- Which workshop pattern was most reusable in your design? → Good discussion starter: scheduled checks, issue creation, or domain specialists.

</details>
