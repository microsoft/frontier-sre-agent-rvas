[< Previous Solution](./Solution-10.md) | **[Home](./README.md)** | [Next Solution >](./Solution-12.md)

# Coach Guide — Challenge 11: Context That Learns

## Purpose

- Demonstrate how organizational context improves an evidence-based operational response.
- Teach students to separate durable knowledge from transient telemetry and verified learning from assumptions.
- Expected time: 20–25 minutes.

## Mini-Lecture (5 min before challenge)

- Monitoring answers “what is happening”; knowledge answers “what does it mean here.”
- Useful knowledge includes architecture, ownership, policy, thresholds, recovery objectives, and boundaries.
- Knowledge must be versioned and reviewed because stale context can produce confidently wrong guidance.
- Incident learning belongs in the knowledge base only after evidence confirms it.

## Expected Student Output

- A baseline response captured before custom knowledge is added.
- A concise reliability knowledge document with ownership, architecture, objectives, and boundaries.
- A grounded response that visibly improves on the baseline.
- One verified incident lesson added and reused in a later response.

## Coach Runbook

1. Capture a baseline answer before attaching custom knowledge; preserve the exact prompt.
2. Review the proposed document for durable facts, owner, review date, boundaries, and no transient resource state.
3. After ingestion, repeat the identical prompt and identify exactly which improvements came from knowledge.
4. Add only a verified lesson, then confirm the agent still checks current telemetry rather than replaying history.

## Common Issues and Hints

- **Symptom:** The before-and-after responses are nearly identical. **Fix:** add concrete local context such as ownership, RTO/RPO, maintenance windows, and escalation boundaries.
- **Symptom:** The new document does not appear in the response. **Fix:** confirm ingestion completed, the source is attached to the agent, and the question contains terms present in the document.
- **Symptom:** The response treats old resource state in the document as current. **Fix:** remove transient state and require a live Azure query before conclusions.
- **Symptom:** Students add an unconfirmed RCA as a lesson. **Fix:** require the evidence and confidence level before accepting it as durable knowledge.

## Debrief Discussion Guide

- What belongs in knowledge rather than telemetry? → Durable organizational facts and policies, not current resource state.
- When should telemetry override knowledge? → Whenever live evidence conflicts with stale or generalized documentation.
- How does contextual learning stay trustworthy? → Evidence, review ownership, timestamps, versioning, and expiry rules.

## Success Criteria Notes

- **Require:** identical before/after question, visible local-context improvement, evidence/context separation, and a reusable verified lesson.
- **Reject:** incident transcripts, assumptions, secrets, or transient state stored as durable truth.
- **Accept:** any concise Markdown or text format supported by the configured source.

## Solution

### Create the knowledge document

Use a short document containing:

- Workload owner and criticality
- Required RPO and retention
- Approved investigation steps
- Escalation channel and on-call owner
- Heartbeat expectation and maintenance window
- Known verified failure modes
- Explicit prohibition on write actions without approval

### Run the comparison

Before attaching the source, ask: `The selected VM has missed heartbeats. Assess impact, likely causes, ownership, recovery objectives, and escalation.` Capture the answer. Attach and ingest the knowledge source, then ask the exact same question. The second response should add local context while still querying current Azure state.

### Add a verified lesson

Append the confirmed Challenge 10 cause, decisive evidence, and prevention guidance with a review date. Ask how the previous incident changes the current investigation. Reject any answer that substitutes the historical lesson for current evidence.