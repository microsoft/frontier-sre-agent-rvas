[< Previous Challenge](./Challenge-09.md) — **[Home](../README.md)**

# Challenge 10 — Build Your Own Production-Ready SRE Agent

## Introduction

You've configured skills, subagents, incident filters, connectors, and scheduled tasks. You've watched the Azure SRE Agent autonomously detect, investigate, and remediate faults across PaaS, IaaS, and network layers.

Now it's your turn.

In this capstone challenge, you'll design and implement a **production-ready SRE agent configuration** for a real use case **you bring from your own environment**. There is no pre-built scenario, no trigger script, and no expected output — only the requirements of the problem you choose to solve.

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
|---|---|---|
| **Skill YAML** | Tool set (read/write Azure CLI, KQL, GitHub, REST) | Define which tools the agent needs |
| **Knowledge doc** | Domain context (architecture, thresholds, runbooks) | Write a doc the agent can reference |
| **Subagent** | A named agent with a scoped system prompt | Define the agent's name, persona, and instructions |
| **Incident filter** | Routes alerts to your subagent | Only if alert-driven |
| **Connector** | Gives the agent access to a data source or action target | Only if non-standard data sources are needed |
| **Scheduled task** | Triggers the agent on a cron schedule | Only if proactive/periodic |

Sketch your design on paper or a whiteboard before building. Have your coach review it before you start coding YAML.

### Step 3 — Implement

Write and apply the configuration:

```bash
make config-sre-agent
```

Refer to the configuration files you built in Challenges 01–03 as templates.

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
6. **Answer to your coach**: "What would need to be true — technically and organizationally — for you to deploy this agent to your production environment next week?"

## Learning Resources

- [Azure SRE Agent — skill authoring](https://learn.microsoft.com/en-us/azure/sre-agent/skills)
- [Azure SRE Agent — subagent configuration](https://learn.microsoft.com/en-us/azure/sre-agent/subagents)
- [Azure SRE Agent — incident filters](https://learn.microsoft.com/en-us/azure/sre-agent/incident-filters)
- [Azure SRE Agent — knowledge docs](https://learn.microsoft.com/en-us/azure/sre-agent/knowledge-docs)
- [Azure SRE Agent — connectors](https://learn.microsoft.com/en-us/azure/sre-agent/connectors)
- [Azure SRE Agent — scheduled tasks](https://learn.microsoft.com/en-us/azure/sre-agent/scheduled-tasks)

## Tips

- **Start small.** Pick a use case that fits in a single subagent with 3–5 tool calls. You can always expand scope later.
- **The system prompt is the most important artifact.** A well-written system prompt with a clear persona, scope, and escalation path will outperform a complex skill configuration every time.
- **Use knowledge docs for everything you'd put in a runbook.** Thresholds, resource names, subscription IDs, known failure modes — if a human would look it up, the agent should have it.
- **Think about blast radius before adding write permissions.** Autonomous write commands are powerful; make sure your system prompt constrains them to the narrowest possible scope.
- **The demo is the deliverable.** A working 3-minute demo with a real trigger and a coherent agent response is more valuable than a perfect YAML that's never been tested.
