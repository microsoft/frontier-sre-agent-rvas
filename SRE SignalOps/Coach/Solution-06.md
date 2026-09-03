[< Previous Solution](./Solution-05.md) | **[Home](./README.md)** | [Next Solution >](./Solution-07.md)

# Coach Guide — Challenge 06: Route a Cross-Domain Incident

## Purpose

Coach an ambiguous Grubify availability incident across application and network domains while preserving one owner, timeline, and evidence record. Expected time: 20–25 minutes.

## Mini-Lecture (5 min before challenge)

- Route according to the next evidence required, not a keyword in the incident title.
- A specialist handoff should return evidence, a bounded uncertainty, or an escalation; it should not create a second incident narrative.
- Skills and specialist agents matter only insofar as they make investigation repeatable, relevant, and least-privileged.

## Expected Student Output

- An initial hypothesis and evidence need for the Grubify HTTP 5xx and dependency-connection exercise.
- A live data-plane specialist inventory compared with the three relevant desired-state manifests.
- A three-specialist live roster containing `aca-app-incident-handler`, `network-traffic-analyst`, and `cost-optimization-agent`; any missing specialist is recorded as configuration drift.
- A schema-normalized roster that reads `handoffDescription` from the live record's `properties` object when the v2 API returns an ARM-style envelope.
- Defensible application-to-network routing decisions with evidence returned at each handoff.
- One accountable incident timeline, unresolved-question list, and owner.
- A compact record of unsafe scope, overlap, or unowned gaps that affect resolution.

## Coach Runbook

1. Have the participant run each command from Challenge 06 directly; there is no wrapper script.
2. Verify the endpoint is discovered from `signalops-core`, the short-lived token uses `https://azuresre.dev`, and the token is never displayed or persisted.
3. Inspect `/api/v2/extendedAgent/agents` before discussing routes. The prepared environment should return all three expected specialists with populated handoff descriptions; treat an empty or incomplete collection as live configuration drift.
4. Compare live registration with the application, network, and cost manifests. Desired state must not be reported as live capability.
5. Present the exercise as an application symptom plus a dependency connection failure; require the next evidence before selecting a domain.
6. Evolve the evidence from HTTP failure to denied network flow without losing the primary owner or timeline.
7. Use the cost prompt as a negative control and reject diversion without causal evidence.
8. Stop if a specialist writes, a simulated route is presented as live, or evidence is replaced with a domain assumption.

## Common Issues and Hints

- **Symptom:** The endpoint returns `{ value: [], nextLink: null }` or fewer than three expected specialists. **Fix:** record live configuration drift, mark affected routes unavailable, and continue only as a labeled manifest-based exercise.
- **Symptom:** The roster object is counted as one specialist. **Fix:** normalize the `value` or `agents` property into an array before counting.
- **Symptom:** `agentType` and `handoffDescription` appear blank even though a specialist is registered. **Fix:** normalize the v2 envelope: read `properties.handoffDescription`, and report `AgentType` as `<not returned>` when neither the top level nor `properties` exposes it. Do not treat top-level `type: ExtendedAgent` as equivalent to manifest `agent_type: Autonomous`.
- **Symptom:** Data-plane request returns `401`. **Fix:** reacquire the short-lived token for `https://azuresre.dev`; never print or persist it.
- **Symptom:** Live fields differ from the manifest. **Fix:** report configuration drift and treat live registration as authoritative for current routing.
- **Symptom:** Every prompt routes to one agent. **Fix:** compare handoff descriptions and the exact evidence required for overlap.
- **Symptom:** The handoff is based only on “network” or “HTTP.” **Fix:** ask which query or observation the receiving domain must provide.
- **Symptom:** Each specialist creates a separate conclusion. **Fix:** require all evidence and uncertainty to return to one primary incident record.
- **Symptom:** A write-capable agent attempts remediation. **Fix:** stop the exercise; Mission 06 authorizes inspection and routing only.

## Debrief Discussion Guide

1. What makes a handoff defensible? → The current investigation requires evidence or authority owned by another bounded domain.
2. Who retains incident accountability? → The primary responder coordinating the shared timeline, decisions, and unresolved questions.
3. How does specialization reduce response risk? → It limits context and permissions while keeping actions within a reviewed operational domain.

## Success Criteria Notes

- **Require:** direct live inventory, live-versus-desired comparison, evidence-led routing, coherent handoffs, one incident owner, and explicit unresolved gaps.
- **Reject:** wrapper use, simulated registration presented as live, keyword-only routing, fragmented timelines, unrelated cost diversion, or any write.
- **Accept:** more than one plausible first domain when the student states a discriminating check and clear tie-breaker.
