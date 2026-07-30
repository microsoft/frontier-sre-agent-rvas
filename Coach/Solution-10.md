[< Previous Solution](./Solution-09.md) | **[Home](./README.md)** | [Next Solution >](./Solution-11.md)

# Coach Guide — Challenge 10: Incident to GitHub Issue

## Purpose

- Show how incidents become durable engineering artifacts instead of disappearing after chat.
- This challenge closes the loop between monitoring evidence and backlog workflow.
- Expected time: 20 minutes.

## Mini-Lecture (3–5 min before challenge)

- Reinforce the GitHub prerequisites: `github` connector green and `grubify` repo linked.
- Name the knowledge template: `sample-food/incident-report-template.md` drives consistent issue structure.
- Show the expected lifecycle: incident context → telemetry evidence → issue creation → follow-up comment with updated findings.
- If no live Parking Manager incident exists, it is valid to use a realistic incident derived from Challenge 09’s health report.

## Expected Student Output

- A GitHub issue exists with clear title, severity, affected component, evidence, and next steps.
- The issue content reflects the knowledge-base template rather than ad hoc prose.
- A follow-up comment adds current error-rate or top-error telemetry.
- Student can review the issue in GitHub or via `gh issue list`.

## Common Issues and Hints

- **Symptom:** Agent says GitHub is not authorized. **Fix:** re-check portal OAuth status on the `github` connector.
- **Symptom:** Issue is created but structure is inconsistent. **Fix:** ask the student to explicitly tell the agent to use the incident report template.
- **Symptom:** No active incident is available. **Fix:** allow a health-report-derived incident narrative from Challenge 09.
- **Symptom:** Comment update lacks fresh evidence. **Fix:** ask specifically for last-hour error rate and top three errors.

## Debrief Discussion Guide

- Why store the template as knowledge instead of relying on the model’s default writing? → Consistency, auditability, and org standards.
- What changed operationally by creating the issue immediately? → Better handoff from on-call to engineering backlog.
- What belongs in the issue vs. what stays in chat history? → Durable evidence and action items belong in GitHub.

## Success Criteria Notes

- Be strict on the presence of live telemetry in the issue.
- Accept either a live incident or a clearly described synthetic incident if the environment is quiet.
- Do not require label perfection unless the repo already has the labels.
