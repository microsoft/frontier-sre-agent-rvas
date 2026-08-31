[< Previous Solution](./Solution-02.md) | **[Home](./README.md)** | [Next Solution >](./Solution-04.md)

# Coach Guide — Challenge 03: Arm the Operator

## Purpose

Apply the mission-owned skills, subagents, Azure Monitor incident platform, and incident filters, then expose tool and approval boundaries. Expected time: 20–25 minutes.

## Mini-Lecture (5 min before challenge)

- A skill is an executable contract: routing description, allowed tools, procedure, and safety posture.
- `plan` describes intended data-plane and ARM requests; `apply` performs them.
- Explicit grants remain enforceable even when a prompt is ambiguous or adversarial.

## Expected Student Output

- Clean plans for 8 skills, 11 subagents, 1 Azure Monitor incident platform, and 4 incident filters.
- With coach approval, applied and verified target classes against the intended agent.
- A successful read-only investigation and a destructive request that is rejected or held for approval.
- External connectors, repositories, scheduled tasks, and knowledge files remain intentionally excluded.

## Coach Runbook

1. Run `pwsh -NoProfile -File '.\SRE SignalOps\Scripts\Challenge-03.ps1'` first. This is plan-only and must not change agent configuration.
2. Confirm the output proposes 8 skill PUTs, 11 subagent PUTs, 1 incident-platform PATCH, and 4 incident-filter PUTs.
3. Review the target subscription, resource group, agent, manifests, and approval boundaries before allowing `-Execute`.
4. After apply, verify all four target classes and run one harmless read probe followed by one destructive safety probe.
5. Stop if the plan includes connectors, repositories, knowledge, scheduled tasks, secrets, or the wrong agent.

## Common Issues and Hints

- **Symptom:** Git Bash path is missing. **Fix:** locate `bash.exe` under the installed Git directory.
- **Symptom:** Validation reports `Required command not found: jq` or no YAML parser. **Fix:** install `jq` and `yq`; the mission runner also discovers current WinGet installations for Git Bash.
- **Symptom:** Bash reports an encoded string as an invalid option. **Fix:** use the current shared runner; its native-command helper must not use `$Command` as the scriptblock parameter name.
- **Symptom:** Validation fails on placeholders. **Fix:** resolve only documented non-secret environment variables.
- **Symptom:** Apply targets the wrong agent. **Fix:** print subscription, resource group, and agent before execution.

## Debrief Discussion Guide

1. Why validate before apply? → It catches malformed manifests, wrong targets, and unsafe scope before mutation.
2. Which layer enforces write approval? → The configured action mode, tool grant, and approval policy; prompt wording alone is not a security boundary.
3. Why constrain tool grants? → Fewer tools reduce accidental action paths and credential or blast-radius exposure.

## Success Criteria Notes

- **Require:** all four plans, exact target identity, post-apply verification, and both safety probes.
- **Reject:** direct destructive execution, skipped plan/validation, or configuration of excluded target classes.
- **Accept:** plan-only completion when the exercise is explicitly a simulation; mark apply and live safety probes as not executed.
