[< Previous Solution](./Solution-07.md) | **[Home](./README.md)** | [Next Solution >](./Solution-09.md)

# Coach Guide — Challenge 08: Improve the Next Heartbeat Response

## Purpose

- Replay the heartbeat incident and demonstrate how verified organizational context improves impact, ownership, recovery, and escalation decisions.
- Teach students to reuse confirmed learning without allowing history to replace current investigation.
- Expected time: 20–25 minutes.

## Mini-Lecture (5 min before challenge)

- Monitoring answers “what is happening”; operational context answers “what does it mean here and who must act.”
- Useful knowledge includes architecture, ownership, policy, thresholds, recovery objectives, and boundaries.
- Knowledge must be versioned and reviewed because stale context can produce confidently wrong guidance.
- Incident learning belongs in the knowledge base only after evidence confirms it.

## Expected Student Output

- A baseline heartbeat-incident response captured before custom knowledge is added.
- A concise reliability knowledge document with ownership, architecture, objectives, and boundaries.
- A replayed response that visibly improves impact, ownership, recovery, or escalation reasoning.
- One verified incident lesson reused without overriding current Azure evidence.

## Coach Runbook

1. Replay the Challenge 07 heartbeat question before upload; preserve the exact prompt and exercise label.
2. Inspect the temporary document before upload and reject placeholders, secrets, personal contact details, assumptions, and transient resource state.
3. Watch the student upload one named document, list files, and inspect indexer status as separate commands.
4. Replay the identical prompt and identify exactly which decisions improved because of context.
5. Permit the verified lesson only after the cause, decisive evidence, prevention guidance, and review date are complete.
6. Confirm the final response tests current evidence rather than treating the historical cause as current truth.

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

- **Require:** identical incident replay, visible improvement to operational decisions, evidence/context separation, and a reusable verified lesson.
- **Reject:** incident transcripts, assumptions, secrets, or transient state stored as durable truth.
- **Accept:** any concise Markdown or text format supported by the configured source.

## Solution

### Verify the before state

The student should discover the agent endpoint through ARM, request a process-only `https://azuresre.dev` token, then run separate file-inventory and indexer-status reads. Require the exact baseline prompt from the challenge and preserve its answer before any upload.

### Review the knowledge document

The temporary document should contain:

- Workload owner and criticality
- Required RTO and RPO
- Approved investigation steps
- Escalation role or non-personal channel
- Heartbeat expectation and maintenance window
- Review owner and review date
- Explicit prohibition on write actions without approval

Require the `Select-String '<[^>]+>'` guard to pass before upload. Reject credentials, tokens, personal contact details, current resource state, and an unconfirmed RCA.

### Verify upload and comparison

Observe the visible multipart upload command. The student must then list files and read indexer status independently; an accepted upload is not proof of completed indexing. Replay the exact baseline prompt and compare work impact, ownership, objectives, maintenance interpretation, boundaries, and escalation in the supplied matrix.

### Add a verified lesson

Require all four lesson fields before the student appends and re-uploads the document. After final file and indexer checks, use the challenge’s evidence-precedence prompt. Reject any answer that substitutes the historical lesson for current evidence.

Confirm the student removes the process token and temporary local document. The durable Agent Memory file remains because this mission intentionally tests later retrieval; remove it only under the customer’s normal knowledge-governance process.