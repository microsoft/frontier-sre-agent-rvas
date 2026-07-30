[< Previous Solution](./Solution-18.md) | **[Home](./README.md)**

# Coach Guide — Challenge 19: Build Your Own Production-Ready SRE Agent

## Purpose

- Capstone: students synthesize skills, knowledge, subagents, routing, and governance into a use case that matters to them.
- The goal is not perfection; it is a credible design plus an end-to-end demonstration.
- Expected time: 45–60 minutes.

## Mini-Lecture (5–7 min before challenge)

- Give a design checklist: repeating failure, known investigation path, clear remediation or escalation, measurable success signal, least-privilege tool set.
- Revisit the building blocks table: skill YAML, knowledge doc, subagent, optional incident filter, optional connector, optional scheduled task.
- Encourage students to keep scope narrow: one real problem solved well beats a broad but vague design.
- End with the production-readiness framing question: what technical and organizational truths must exist to ship next week?

## Expected Student Output

- A written use-case statement approved by the coach.
- At least one custom subagent and one skill YAML, plus a supporting knowledge document.
- A live or replayable end-to-end test showing correct tool use and coherent output.
- A 3-minute presentation covering problem, design, demo, and production guardrails.

## Common Issues and Hints

- **Symptom:** Use case is too broad (“handle all outages”). **Fix:** force scope reduction to one repeating failure mode.
- **Symptom:** Student jumps into YAML without clear operational procedure. **Fix:** make them write the human runbook first.
- **Symptom:** They add write permissions casually. **Fix:** ask what rollback, validation, and ownership model would justify that.
- **Symptom:** Demo is purely conceptual. **Fix:** require at least one concrete test prompt, alert simulation, or captured agent log.

## Debrief Discussion Guide

- What would need to be true technically to deploy next week? → Data sources, permissions, validation signals, rollback, observability.
- What would need to be true organizationally? → Ownership, approval model, audit trail, incident policy, trust.
- Which workshop pattern was most reusable in student designs? → Good discussion starter: scheduled checks, issue creation, or domain specialists.

## Success Criteria Notes

- Grade for realism, coherence, and safe scoping, not flashy ambition.
- Be strict that there is a test and a presentation.
- Accept partial implementation if the design is strong and the demonstrated slice is real and well-governed.
