[< Previous Solution](./Solution-09.md) | **[Home](./README.md)**

# Coach Guide — Challenge 10: Build Your Own Production-Ready SRE Agent

## Purpose

This is the capstone challenge. Students apply everything they've learned — skills, subagents, incident filters, connectors, knowledge docs, and scheduled tasks — to a use case they own. There is no single correct answer. Your role shifts from instructor to design reviewer and demo facilitator.

Expected time: **45–60 minutes** (design + build + demo presentations).

## Mini-Lecture (10 min before challenge)

Cover:

- **Recap the building blocks**: skill → subagent → incident filter/connector/scheduled task — draw the dependency graph on a whiteboard
- **What makes an agent "production-ready"**: narrowly scoped write permissions, a runbook-style knowledge doc, a clear escalation path when confidence is low, an audit trail (incident report + tool call log)
- **The system prompt is the contract**: it defines what the agent will and won't do — treat it like a code review artifact
- **Encourage bold use cases**: the students who pick hard problems learn the most, even if the demo isn't perfect

## Facilitation Guide

### Use-case review (10–15 min)

Circulate while students write their use-case description (Step 1). Review each one before they start building:

**Approve if:**
- The trigger is observable (alert, cron, chat prompt, GitHub event)
- The investigation steps are finite and describable
- The remediation has a clear success condition
- The blast radius is manageable (a wrong action can be undone)

**Push back if:**
- The use case is too broad ("monitor everything")
- There is no clear success condition
- The remediation involves irreversible destructive actions with no rollback path
- The use case is identical to a scenario already covered in Challenges 04–09 (push them to differentiate)

**Common use cases that work well:**
- Certificate / secret expiry alert → query Key Vault, open a GitHub issue or notify a team
- Disk pressure on a VM → identify the top files/directories, optionally clean up temp dirs
- AKS node NotReady → cordon, drain, and restart, with escalation if unresolvable
- Cost spike alert → identify top-cost resources in a subscription, generate a Markdown report
- Azure DevOps / GitHub PR stale reviewer → label and comment after N days of inactivity
- Deployment failure → parse pipeline logs, correlate with recent commits, suggest rollback candidate

### Design review (5 min per group)

Before students start writing YAML, confirm:

1. They can name the subagent, its persona, and its one-sentence responsibility
2. They know which tools (read vs. write) the skill needs
3. They have at least one knowledge doc topic in mind
4. They know how the agent will be triggered (alert / chat / schedule)

Ask: **"If the agent makes the wrong call, what happens? How would you know? How would you fix it?"**

### Build support

Point students to the configuration files they produced in Challenges 01–03 as templates. The most common blockers:

| Blocker | Coach action |
|---|---|
| System prompt too vague | Ask: "What are the first 3 tool calls the agent should make?" Then put those in the prompt as numbered steps |
| No knowledge doc | Ask: "What would a new engineer read before handling this alert?" That's the knowledge doc |
| Write permissions blocked | Verify the skill YAML includes `RunAzCliWriteCommands` and the system prompt explicitly authorizes the action |
| Agent routes to wrong subagent | Check the incident filter — `titleContains` / `titleNotContains` conditions may need tuning |
| Scheduled task not triggering | Confirm `make config-sre-agent` was re-run after editing the YAML |

## Demo Facilitation (3 min per group)

Keep a timer. After each demo, ask the group one question:

- **"Would you trust this agent to run in production tonight?"** — No wrong answer; the point is the reasoning
- **"What's the first guardrail you'd add?"**
- **"Where does the human stay in the loop?"**

## Evaluating Production Readiness

Use this checklist during demos:

| Criterion | Look for |
|---|---|
| **Scoped skill** | Only the tools the scenario needs — no unnecessary write permissions |
| **System prompt** | Named agent, clear responsibility, explicit escalation path ("if X, stop and report") |
| **Knowledge doc** | At least one doc with domain context the agent referenced during the demo |
| **Trigger** | The agent responds to a realistic trigger, not just a direct chat prompt |
| **Audit trail** | The agent produces a summary with tool calls, findings, and action taken |
| **Blast radius** | The student can articulate what a wrong action would do and how to recover |

Full credit requires all six. Partial credit for four or more with a strong explanation of what's missing and why.

## Debrief Discussion Guide (10–15 min, full group)

Run this after all demos:

1. **"Which demo was closest to something you'd deploy to production?"** — Forces the group to apply the production-readiness criteria themselves

2. **"What patterns did you see across all the designs?"** — Surface: most good agents have a narrow scope, a clear "stop and escalate" condition, and write permissions locked to a specific resource type

3. **"What's the difference between an SRE agent and a runbook automation?"** — The key answer: reasoning under uncertainty, evidence synthesis, and natural language interface. The risk answer: a runbook does exactly what you wrote; an agent may improvise

4. **"What would your organization need to do before deploying one of these agents to production?"** — Cluster answers: change management, approval gates, pre-approved remediation playbooks, blast radius limits, incident audit trail, SLA for human escalation

5. **"What would you build next?"** — End on an expansive note; the goal is for students to leave with a concrete next step

## Success Criteria Notes

- Accept any working end-to-end demo where the agent makes correct tool calls and produces a coherent response — the use case does not have to be novel
- If a student's live trigger fails during the demo, accept a replayed tool call log from a successful prior test run
- The 3-minute presentation is required — a working agent with no explanation of production readiness is incomplete
- The answer to "what would it take to deploy this next week?" is the most important artifact: it shows whether the student has internalized the governance dimension of agentic automation
