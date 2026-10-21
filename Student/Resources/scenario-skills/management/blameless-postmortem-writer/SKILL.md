---
name: blameless-postmortem-writer
description: Use when the user asks for a postmortem, a post incident review, an incident retrospective, a root cause writeup, or a blameless RCA document after an incident. Assembles the timeline, impact, root cause, contributing factors, and action items into a blameless postmortem, and produces a clean self contained HTML document ready to edit and share.
tools:
  - RunAzCliReadCommands
  - RunInTerminal
  - SaveFileToBlob
metadata:
  category: management
---

# Blameless Postmortem Writer

This skill turns the facts of a resolved incident into a blameless postmortem. It gathers the timeline and impact, states the root cause in terms of systems rather than people, captures contributing factors and what to change, and produces a clean self contained HTML document ready to edit and share. It removes the paperwork friction so teams actually write postmortems, which is where the durable reliability gains come from. It runs on demand after an incident.

## When to use this skill

Use this skill when the user asks to:

- Write a postmortem, a post incident review, or an incident retrospective.
- Turn an incident timeline into a shareable writeup with action items.
- Produce a blameless root cause document after an incident is resolved.

## Operating principles

- Blameless. Describe what the system did and why it was possible, not who did it. Replace names of people with roles and systems. Assume everyone acted reasonably with the information they had.
- Read only. This skill reads incident evidence and writes a document. It changes nothing in Azure.
- Evidence based and honest. The timeline and impact come from evidence. Where a fact is unknown, say so and make finding it an action item rather than guessing.
- Review before sharing. Generated artifacts are drafts. Sanitize identifiers and credentials, verify impact and evidence with the incident owner, and obtain approval before any external sharing. This skill never sends email, chat messages or external notifications automatically.

## Workflow

The renderer (tools/postmortem_render.py) is bundled with this skill. Run it with RunInTerminal using the Python in the agent runtime; it uses only the standard library.

### Phase 1: Gather the facts

1. Collect the incident facts from the user, from a prior incident report if the incident-triage-rca skill produced one, and from the Activity Log and Resource Health for the affected resources with RunAzCliReadCommands. Fill the structure in references/postmortem-template.md.
2. Build the timeline from first symptom to resolution: detection, escalation, the key diagnostic steps, the mitigation, and the all clear. Note detection time and time to mitigate.

### Phase 2: Write it blameless

Follow references/writing-guide.md. State the root cause as a chain of contributing conditions, not a single human error. Separate the trigger from the underlying weakness. Write action items that are specific, owned, and dated, and that address the underlying weakness, not just the trigger.

### Phase 3: Produce the document

1. Assemble the postmortem object described in references/postmortem-template.md and pipe it into python tools/postmortem_render.py with RunInTerminal. Default output uses the bundled sharing policy to alias identifiers and redact credentials. Use `--include-identifiers` only for an explicitly requested internal draft; credentials remain redacted. Review the file before publishing with SaveFileToBlob or sharing it externally.
2. Present the document, then a short inline summary: the incident in one line, the impact, the root cause, and the action items with owners.

## Scenario coverage

This skill implements its documented checks, not every related scenario. Use the related skills for their complete evidence workflows. See [scenario routing](./references/scenarios.md).


## Expected output

- Primary: a self contained HTML postmortem with summary, impact, timeline, root cause, contributing factors, detection and resolution, lessons, and action items.
- Inline: the one line summary, impact, root cause, and the action items with owners and dates.
- The language stays blameless throughout: systems and conditions, not individuals. Unknown facts are named and turned into action items rather than guessed.
- Carry `assessment_status` and evidence `sources` into the document. Missing or failed evidence collection is Partial or Not assessed, never a confident empty state. Record human review separately from collection status.

## Sources

- Incident evidence supplied by the user or the triage collector, listed in each generated document.
- [Writing method](references/writing-guide.md), preserved by the renderer.

## Assessment and customer sharing

Confirm the explicit customer scope and UTC window before collection. Accessible resources are not automatically approved scope. For a tool that enumerates all visible subscriptions, use an identity restricted to the approved scope or the related skill's scoped commands.

Follow [assessment states and limits](./references/assessment-contract.md), [permissions](./references/permissions-and-scope.md), and [customer sharing review](./references/customer-sharing.md), bundled during deployment. The shared renderer produces a sanitized draft by default; `--include-identifiers` requires an explicitly approved customer audience. Review custom exports with the same checklist.

Configure the host using [governance settings](./references/governance.json). General terminal access is not inherently read only. Never apply changes, schedule work, upload files or send messages without separate explicit approval.

## Approval boundary

Confirm explicit customer scope and the intended identity. Host authorization must enforce the bundled governance policy; general terminal access is not inherently read only. Changes, deployment, scheduling, uploads and messages require separate explicit approval. Preserve denied, missing and truncated evidence as unassessed, never healthy.
