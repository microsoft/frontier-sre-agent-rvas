[< Previous Solution](./Solution-08.md) | **[Home](../../README.md)**

# Coach Guide — Challenge 09: Build Your Own SQL Server DBA Agent

## Purpose

* Synthesize the track's diagnostic techniques into a focused, repeatable DBA investigation.
* Assess safe agent design, evidence quality, and production-readiness judgment.
* Expected time: 75-90 minutes.

## Mini-Lecture (10 min before challenge)

* A useful agent starts with a bounded operational question, not a broad role description.
* The `sqlserver-mcp` tool contract and database permissions remain the enforcement boundary.
* Every conclusion should be traceable to native evidence with a clear scope and time window.
* Missing evidence and safe refusal are valid outcomes; a confident unsupported root cause is not.
* A production workflow also needs ownership, review, and validation outside the agent.

## Expected Student Output

* A coach-approved scenario brief with impact, audience, observation scope, and expected signals.
* A purpose-built DBA custom-agent configuration and target-specific investigation guidance that preserve the supplied read-only policy.
* A live or replayable test showing evidence-based findings and a safe response to an unsupported request or evidence gap.
* A technical handoff with observations, hypotheses, alternatives, recommendations, owners, and validation considerations.
* A concise presentation of the scenario, design, demonstration, and production-readiness gaps.

## Common Issues and Hints

* **Symptom:** The scenario asks the agent to diagnose every database problem. **Fix:** limit it to one question, one audience, and a bounded evidence window.
* **Symptom:** The student adds tools or database permissions to make the demo easier. **Fix:** preserve the supplied `sqlserver-mcp` contract and treat missing access as a reported prerequisite.
* **Symptom:** The report presents one signal as proven root cause. **Fix:** ask for a second corroborating signal, an alternative explanation, and explicit uncertainty.
* **Symptom:** The demo only shows the expected happy path. **Fix:** test a request outside scope or a case where the required evidence is unavailable.
* **Symptom:** Recommendations imply that the agent applied a fix. **Fix:** separate recommendation from execution and name the owner and validation needed before approval.

## Debrief Discussion Guide

* What made the scenario narrow enough to produce a useful answer?
* Which native evidence most changed the team's confidence, and what remained unknown?
* How did the unsupported-request test demonstrate the trust boundary?
* What review, ownership, or monitoring would be needed before production use?

## Success Criteria Notes

* Be strict on approved-tool use, read-only behavior, evidence traceability, and the unsupported-request test.
* Accept any database reliability scenario that is bounded, reproducible, and appropriate for the sample environment.
* Accept an inconclusive result when the student accurately identifies missing or stale evidence.
* Grade the presentation for clear reasoning and production-readiness judgment, not visual polish.

## Solution

An acceptable capstone might investigate a recurring Query Store regression for
one business operation. The student should:

1. Define the affected operation, user impact, database profile, and UTC time window.
2. Configure a narrowly scoped agent and guidance that use only
   `list_profiles`, `get_object`, `run_query`, and `analyze_query` through
   `sqlserver-mcp`.
3. Compare bounded Query Store intervals and plan evidence, then check one
   credible alternative such as workload change or parameter distribution.
4. Test a request outside the scenario scope and confirm the agent stops or
   explains the missing prerequisite without using another connection path.
5. Present a handoff that labels observations and hypotheses separately,
   recommends an owner-led validation, and confirms no database changes.

Other scenarios are valid when they use the available sample evidence and meet
the same safety and traceability standard.