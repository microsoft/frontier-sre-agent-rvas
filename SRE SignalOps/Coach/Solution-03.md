[< Previous Solution](./Solution-02.md) | **[Home](./README.md)** | [Next Solution >](./Solution-04.md)

# Coach Guide — Challenge 03: Triage the First Grubify Incident

## Purpose

Configure the SRE operating model and coach a reported HTTP-health issue from ambiguous symptom to evidence-backed triage and a guarded response. The architecture and baseline are handled separately in [Coach Orientation — Understand Grubify](./Lab-Details.md). Expected time: 20–25 minutes.

## Mini-Lecture (5 min before challenge)

- SRE starts with an imperfect signal and reduces uncertainty through time-bounded evidence.
- Separate what the customer reported, what Azure currently proves, what remains a hypothesis, and what action is justified.
- Diagnostic skills and specialist agents support repeatable investigation and bounded delegation; they are implementation controls, not the lesson.
- Approval and recovery gates prevent a plausible diagnosis from becoming an unsafe environmental change.

## Expected Student Output

- A reviewed setup plan for 8 diagnostic skills, 11 specialist definitions, 1 Azure Monitor incident platform, and 4 incident filters.
- With coach approval, all four supporting control classes applied and verified against the intended SRE Agent.
- A time-bounded Grubify incident record that separates the reported symptom, observed evidence, hypotheses, provisional diagnosis, confidence, and evidence gaps.
- A safe response proposal with approval and measurable recovery criteria; no unapproved environmental write.
- External connectors, repositories, scheduled tasks, and knowledge files remain intentionally excluded.

## Coach Runbook

1. Confirm the [Lab Details baseline](../Lab-Details.md#normal-baseline) is preserved and any controlled limitation is explicit.
2. Run `pwsh -NoProfile -File '.\SRE SignalOps\Scripts\Challenge-03.ps1'`. This is plan-only and must not change agent configuration.
3. Confirm the output proposes 8 skill PUTs, 11 subagent PUTs, 1 incident-platform PATCH, and 4 incident-filter PUTs. Explain these briefly as diagnostic procedures, specialist routing, alert intake, and issue routing.
4. Review the target subscription, resource group, agent, manifests, and approval boundaries before allowing `-Execute`.
5. After apply and verification, present: `EXERCISE: Users report that Grubify is slow and intermittently returning HTTP errors.` Do not tell participants whether the report reflects a current fault.
6. Require current telemetry, a bounded investigation window, affected and unaffected components, at least two hypotheses, confidence, an evidence gap, the next discriminating check, and recovery criteria.
7. Run the destructive safety probe only after triage. Stop if any write executes without the configured approval path.
8. Stop if the configuration plan includes connectors, repositories, knowledge, scheduled tasks, secrets, or the wrong agent.

## Common Issues and Hints

- **Symptom:** Git Bash path is missing. **Fix:** locate `bash.exe` under the installed Git directory.
- **Symptom:** Validation reports `Required command not found: jq` or no YAML parser. **Fix:** install `jq` and `yq`; the mission runner also discovers current WinGet installations for Git Bash.
- **Symptom:** Bash reports an encoded string as an invalid option. **Fix:** use the current shared runner; its native-command helper must not use `$Command` as the scriptblock parameter name.
- **Symptom:** The investigation repeats the customer report as root cause. **Fix:** require one current Azure observation for every causal claim.
- **Symptom:** No active fault is visible. **Fix:** accept `not confirmed` when the student states the evidence gap and next discriminating check; do not manufacture an incident.
- **Symptom:** Apply targets the wrong agent. **Fix:** print subscription, resource group, and agent before execution.

## Debrief Discussion Guide

1. What did the customer report establish? → A symptom and starting point, not a confirmed incident or root cause.
2. What makes the triage useful to an on-call SRE? → Current evidence, bounded scope, explicit uncertainty, a discriminating next check, and measurable recovery criteria.
3. Why keep specialist routing and diagnostic procedures bounded? → They make investigation repeatable while limiting irrelevant context, permissions, and blast radius.
4. Which layer enforces write approval? → The configured action mode, tool grant, and approval policy; prompt wording alone is not a security boundary.

## Success Criteria Notes

- **Require:** a preserved baseline, exact target identity, reviewed configuration plan, an evidence-backed incident record, visible uncertainty, approval posture, recovery checks, and the safety probe.
- **Reject:** direct destructive execution, skipped plan/validation, invented telemetry, or a diagnosis based only on the customer report.
- **Accept:** `not confirmed` as a valid operational conclusion when supported by current evidence and a concrete next check. For plan-only completion, label apply, live routing, and safety probes as not executed.
