[< Previous Solution](./Solution-04.md) | **[Home](./README.md)** | [Next Solution >](./Solution-06.md)

# Coach Guide — Challenge 05: Investigate an Evidence Blind Spot

## Purpose

Coach an SRE investigation when one required evidence source is failed, stale, unauthorized, or unavailable during Grubify triage. Expected time: 15–20 minutes.

## Mini-Lecture (5 min before challenge)

- An investigation is only as current and scoped as the evidence it can retrieve.
- Configured, authenticated, authorized, reachable, and fresh are distinct states.
- Missing evidence should reduce confidence, trigger a fallback or escalation, and never be silently replaced by assumptions.

## Expected Student Output

- A current evidence-source matrix tied to the Grubify incident question.
- One classified blind spot with diagnostic impact, alternate evidence, owner, and recovery proof.
- An explicit `unverified` label wherever a current read was not completed.

## Coach Runbook

1. Continue the Grubify HTTP-health exercise and ask which evidence source is needed for the next decision.
2. Designate one real failed or stale read, or provide a labeled failed-read result. Never disable a production source for the exercise.
3. Require harmless reads with timestamp, scope, freshness, and returned object type, then classify the blind spot.
4. Ask what can still be concluded, which alternate source can discriminate next, who owns restoration, and what proves evidence access recovered.
5. Stop and rotate credentials if any token or secret appears in output.

## Common Issues and Hints

- **Symptom:** Connector shows healthy but reads fail. **Fix:** test authentication and authorization separately.
- **Symptom:** Secrets appear in output. **Fix:** redact and rotate exposed values immediately.
- **Symptom:** The SRE Agent completes the diagnosis despite missing required evidence. **Fix:** reduce confidence and require an alternate discriminating source or escalation.
- **Symptom:** All sources are healthy. **Fix:** use a labeled failed-read result instead of breaking a live connector.

## Debrief Discussion Guide

1. When can investigation continue with a blind spot? → When alternate evidence can answer the decision safely and uncertainty remains explicit.
2. When should the SRE stop or escalate? → When missing evidence prevents impact, cause, or action risk from being bounded.
3. What proves the blind spot recovered? → A current, authorized, scoped read returning expected data, not configuration state alone.

## Success Criteria Notes

- **Require:** incident relevance, a classified blind spot, explicit diagnostic impact, fallback or escalation, owner, and recovery proof.
- **Reject:** secrets in evidence, invented data, or a confident diagnosis that depends on an unavailable source.
- **Accept:** healthy live sources plus a coach-provided failed-read result, clearly labeled as an exercise.
