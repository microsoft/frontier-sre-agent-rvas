[< Previous Solution](./Solution-04.md) | **[Home](./README.md)** | [Next Solution >](./Solution-06.md)

# Coach Guide — Challenge 05: Route a Cross-Domain Incident

## Purpose

Coach an ambiguous Grubify availability incident across application and network domains while preserving one owner, timeline, and evidence record. Expected time: 15–20 minutes.

## Mini-Lecture (5 min before challenge)

- Route according to the next evidence required, not a keyword in the incident title.
- A specialist handoff should return evidence, a bounded uncertainty, or an escalation; it should not create a second incident narrative.
- Skills and specialist agents matter only insofar as they make investigation repeatable, relevant, and least-privileged.

## Expected Student Output

- An initial hypothesis and evidence need for the Grubify HTTP 5xx and dependency-connection exercise.
- Defensible application-to-network routing decisions with evidence returned at each handoff.
- One accountable incident timeline, unresolved-question list, and owner.
- A compact record of unsafe scope, overlap, or unowned gaps that affect resolution.

## Coach Runbook

1. Present the exercise as an application symptom plus a dependency connection failure; do not name the owning specialist.
2. Require the student to state the next evidence needed before routing, then inspect the relevant manifest only to verify scope and safety.
3. Evolve the evidence from HTTP failure to denied network flow and require a justified handoff without losing the primary owner or timeline.
4. Use the cost prompt as a negative control and reject diversion without causal evidence.
5. Stop if a specialist writes, lacks an approval boundary, or replaces evidence with a domain assumption.

## Common Issues and Hints

- **Symptom:** Every prompt routes to one agent. **Fix:** compare routing descriptions for overlap.
- **Symptom:** The handoff is based only on “network” or “HTTP.” **Fix:** ask which query or observation the receiving domain must provide.
- **Symptom:** Each specialist creates a separate conclusion. **Fix:** require all evidence and uncertainty to return to one primary incident record.
- **Symptom:** A write-capable agent has no gate. **Fix:** keep it disabled until approval is configured.

## Debrief Discussion Guide

1. What makes a handoff defensible? → The current investigation requires evidence or authority owned by another bounded domain.
2. Who retains incident accountability? → The primary responder coordinating the shared timeline, decisions, and unresolved questions.
3. How does specialization reduce response risk? → It limits context and permissions while keeping actions within a reviewed operational domain.

## Success Criteria Notes

- **Require:** evidence-led routing, coherent handoffs, one incident owner, and explicit unresolved gaps.
- **Reject:** keyword-only routing, fragmented timelines, unrelated cost diversion, or unreviewed write grants.
- **Accept:** more than one plausible first domain when the student states a discriminating check and clear tie-breaker.
