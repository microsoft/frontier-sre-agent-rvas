[< Previous Challenge](./Challenge-18.md) — **[Home](../README.md)**

# Challenge 19 — Build Your Own Production-Ready SRE Agent

> **Application focus:** Infrastructure/platform only

## Introduction

Use the skills, subagents, incident filters, connectors, and scheduled tasks you've explored to build an agent configuration for a real operations problem from your environment.

Choose the scenario, implement it, and demonstrate an end-to-end test. Treat the result as a tested prototype: explain what further controls and validation it would need before production use.

## Description

### Step 1 — Define your use case

Choose a real reliability or operations problem from your work. It should be something that currently requires manual investigation or intervention. Good candidates:

- A recurring alert that always requires the same investigation steps
- A failure mode you've seen in production that has a known remediation
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

Sketch your design on paper or a whiteboard before building. Have your coach review it before you start coding YAML.

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

For skills: create your `.md` runbook and `.yaml` skill definition in `Student/Resources/azure-sre-agent-config/skills/`, then upload them via **Skills → Add skill** in the portal.

For subagents, incident filters, and scheduled tasks: configure them directly in the SRE Agent portal.

Refer to the skills and subagents you configured in Challenges 01–18 as templates.

### Step 4 — Validate

Test your agent end-to-end:

- **Alert-driven**: trigger the condition (or simulate it) and confirm the incident is routed and the agent responds correctly
- **Chat-driven**: open the SRE Agent portal and prompt your agent directly with a realistic incident description
- **Scheduled**: if applicable, trigger the scheduled task manually and confirm the output

Capture the agent's tool call log and response. This is your demo artifact.

### Step 5 — Present to the group

Prepare a 3-minute demo covering:

1. The problem: what fails, how often, what the manual effort costs today
2. The design: which building blocks you used and why
3. The demo: trigger the scenario and walk through the agent's response live (or replay the captured log)
4. Production readiness: what guardrails, audit trail, or escalation path you would add before deploying this in your real environment

## Success Criteria

To complete this challenge, demonstrate:

1. A written use-case description (one paragraph minimum) that your coach has approved
2. At least one custom subagent with a scoped system prompt and at least one skill YAML
3. At least one knowledge doc that the agent references during its response
4. A working end-to-end test: the agent responds to the scenario with correct tool calls and a coherent remediation or analysis report
5. A 3-minute group presentation covering problem, design, demo, and production-readiness considerations
6. **Explain to your coach**: "What would need to be true — technically and organizationally — for you to deploy this agent to your production environment next week?"

## Learning Resources

- [Azure SRE Agent — skill authoring](https://learn.microsoft.com/en-us/azure/sre-agent/skills)
- [Azure SRE Agent — subagent configuration](https://learn.microsoft.com/en-us/azure/sre-agent/sub-agents)
- [Azure SRE Agent — incident filters](https://learn.microsoft.com/en-us/azure/sre-agent/automate-incidents)
- [Azure SRE Agent — knowledge docs](https://learn.microsoft.com/en-us/azure/sre-agent/connect-knowledge)
- [Azure SRE Agent — connectors](https://learn.microsoft.com/en-us/azure/sre-agent/connectors)
- [Azure SRE Agent — scheduled tasks](https://learn.microsoft.com/en-us/azure/sre-agent/scheduled-tasks)

## Tips

- **Start small.** Pick a use case that fits in a single subagent with 3–5 tool calls. You can always expand scope later.
- **Make the system prompt specific.** Define the agent's role, scope, and escalation path, then test it with the configured tools and skills.
- **Use knowledge docs for everything you'd put in a runbook.** Thresholds, resource names, subscription IDs, known failure modes — if a human would look it up, the agent should have it.
- **Limit blast radius before adding write permissions.** Use narrow tool grants and resource permissions as well as explicit scope in the system prompt.
- **The demo is the deliverable.** A working 3-minute demo with a real trigger and a coherent agent response is more valuable than a perfect YAML that's never been tested.
