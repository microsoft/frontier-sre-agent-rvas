[< Previous Solution](./Solution-01.md) | **[Home](../README.md)** | [Next Solution >](./Solution-03.md)

# Coach Guide — Challenge 02: Build Grubify Knowledge and Incident Memory

## Purpose

- Convert the supplied contextual-learning demo into a real, inspectable Agent Memory exercise.
- Teach participants to separate repository knowledge, indexed memory, desired subagent configuration, and live registration.
- Expected time: 20–30 minutes, including asynchronous indexing.

## Mini-Lecture (5 min before challenge)

- Monitoring signals describe what is happening now; durable knowledge explains architecture, policy, and approved response patterns.
- Bicep stage 02 permits empty memory; Terraform completion preloads four approved documents. Audit the actual inventory, upload only missing or intentionally updated files, and verify retrieval in either case.
- The access token is short-lived process state. It must use the `https://azuresre.dev` audience and must never be printed or persisted.
- Memory can accelerate hypothesis selection, but current telemetry must confirm or reject every incident claim.
- A local JSON manifest is desired state. Only the data-plane collection proves whether that subagent is live.

## Expected Student Output

- A path inventory showing four files under `$Lab.CONFIG_ROOT\knowledge` and `handler.json` under `$Lab.CONFIG_ROOT`.
- Separate pre-upload responses for Agent Memory status, indexer status, and file inventory.
- Individual upload results for missing/updated files, or a verified preloaded inventory, containing all four expected basenames.
- Indexer evidence that is reported as running, successful, pending, or failed without embellishment.
- Local handler evidence for `Agent Memory first`, the report-template filename, and `SearchMemory`, plus a separate live subagent inventory.
- A memory-only response that attributes architecture, routes, triage guidance, and report structure to named documents.

## Coach Runbook

1. Confirm the participant runs from the repository root and resolves every path before authentication.
2. Require ARM endpoint discovery from `$Lab.SRE_AGENT_ID`; reject copied endpoint values.
3. Watch for accidental token output. If exposed, stop and reacquire a token before continuing; do not record it in notes or screenshots.
4. Capture the actual baseline: memory state, file inventory and indexer state. Do not assume an empty inventory or reuse a previous deployment's results.
5. Allow only the four reviewed knowledge files to be uploaded. Each missing/updated file's upload remains attributable; do not require redundant uploads when all four are already present.
6. Recheck the file collection and indexer. Do not require instant indexing and do not use repeated uploads as a polling mechanism.
7. Compare the local handler manifest with the live agent collection. Absence is a legitimate configuration gap.
8. In the final prompt, prohibit live queries so document retrieval can be evaluated independently of telemetry access.

## Common Issues and Hints

- **Symptom:** `Get-Item` cannot find a knowledge document. **Fix:** reload the matching deployment context and use `$Lab.CONFIG_ROOT\knowledge`.
- **Symptom:** The handler inspection finds no expected YAML fields. **Fix:** parse `$Lab.CONFIG_ROOT\handler.json` as JSON and inspect `properties.instructions` and `properties.tools`.
- **Symptom:** A data-plane request returns `401`. **Fix:** reacquire the token with `az account get-access-token --resource https://azuresre.dev`; do not use an ARM-audience token.
- **Symptom:** Agent Memory is enabled but the file list is empty. **Fix:** treat that as the expected pre-upload state and continue with the four explicit upload commands.
- **Symptom:** File upload succeeds but the indexer has not processed documents. **Fix:** wait for the asynchronous indexer and rerun the read-only status checks; do not duplicate uploads.
- **Symptom:** The specific handler is absent from the live agent collection. **Fix:** report desired-state/live-state drift and continue the knowledge retrieval exercise without claiming the handler is registered.
- **Symptom:** The answer invents `/api/menu` or current 5xx evidence. **Fix:** require document attribution and remind the participant that the memory-only prompt must not query current resources.

## Debrief Discussion Guide

1. What belongs in Agent Memory? → Reviewed architecture, runbooks, templates, ownership, and verified lessons that remain useful over time.
2. What must stay out? → Tokens, secrets, personal data, transient measurements, and unverified incident assumptions.
3. Why inspect status, indexer status, and files independently? → Service availability, indexing execution, and stored-document inventory are different states.
4. Why compare local and live subagents? → Git-managed desired state does not prove successful data-plane registration.
5. How does memory improve the next incident without deciding its cause? → It supplies context and known procedures; current evidence still determines the diagnosis.

## Success Criteria Notes

- **Require:** resolved local paths, safe token handling, all four documents present through uploads or verified preloading, recorded inventory, honest indexing state, and document attribution.
- **Reject:** stale Word-document paths, printed/persisted tokens, invented live registration, or current-health claims based only on knowledge.
- **Accept:** indexing still in progress or the ACA handler absent from the live collection when the participant records the state accurately.
