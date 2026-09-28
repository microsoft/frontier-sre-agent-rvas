[< Previous Challenge](./Challenge-08.md) — **[Home](../../README.md)**

# Challenge 09 — Build Your Own SQL Server DBA Agent

> **Capabilities added in this challenge**: Custom DBA Agent · Investigation Design · Read-Only Validation

## Introduction

You have practiced schema discovery, Query Store analysis, waits, blocking,
index evidence, query shape, parameter behavior, and incident handoffs. Now
design a focused database reliability workflow around a problem that matters to
your team.

Build and demonstrate a purpose-built SQL Server DBA agent configuration that
turns a clear operational question into a repeatable, evidence-led
investigation without changing database state.

## Description

Create a capstone that:

* Defines one database reliability question, its audience, impact, and bounded
  observation window
* Configures a focused DBA custom agent and target-specific investigation
  guidance using the supplied `sqlserver-mcp` connector and its approved tools
* Identifies the expected native evidence, important alternative explanations,
  and conditions where the agent must report insufficient evidence
* Demonstrates the workflow against an approved sample-database scenario and
  tests at least one unsupported or out-of-scope request
* Produces a concise technical handoff with evidence, recommendations, owners,
  validation considerations, and an explicit read-only confirmation

The scenario must extend the techniques from this track rather than repeat the
combined incident exercise in Challenge 08. Keep the database trust boundary
and the supplied MCP tool contract intact.

## Success Criteria

- [ ] A coach-approved scenario brief states the operational question, impact, audience, and observation window
- [ ] A purpose-built DBA agent and target-specific investigation guidance have a clear scope and use only the approved `sqlserver-mcp` tools
- [ ] The live or replayable demonstration cites native evidence, distinguishes observations from hypotheses, and considers at least one alternative explanation
- [ ] An unsupported request or evidence gap is handled safely without switching tools, inventing findings, or changing database state
- [ ] The final handoff gives actionable read-only recommendations with owners and validation considerations
- [ ] A concise presentation explains the scenario, design choices, demonstration, and production-readiness gaps
- [ ] **Explain to your coach** — what evidence or organizational control would you require before this workflow could influence a production database decision?

## Learning Resources

* [Azure SRE Agent skills](https://learn.microsoft.com/azure/sre-agent/skills)
* [Azure SRE Agent subagents](https://learn.microsoft.com/azure/sre-agent/sub-agents)
* [Monitor and tune for performance](https://learn.microsoft.com/sql/relational-databases/performance/monitor-and-tune-for-performance)
* [Query Store usage scenarios](https://learn.microsoft.com/sql/relational-databases/performance/query-store-usage-scenarios)

## Tips

* Choose one question with a repeatable signal and an observable outcome.
* Reuse the supplied safety policy; narrow the agent's purpose rather than
  weakening its tool or permission boundaries.
* A well-supported conclusion of "insufficient evidence" is a valid result.