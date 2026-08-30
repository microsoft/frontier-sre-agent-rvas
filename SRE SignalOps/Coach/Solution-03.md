[< Previous Solution](./Solution-02.md) | **[Home](./README.md)** | [Next Solution >](./Solution-04.md)

# Coach Guide — Challenge 03: Arm the Operator

## Purpose

Apply the mission-owned skills, subagents, Azure Monitor incident platform, and incident filters, then expose tool and approval boundaries. Expected time: 20–25 minutes.

## Mini-Lecture (5 min before challenge)

A skill is an executable contract: routing description, allowed tools, procedure, and safety posture.

## Expected Student Output

Validated, planned, applied, and verified mission targets; a successful read; and a blocked or approval-held destructive request. External connectors, repositories, scheduled tasks, and knowledge files remain intentionally excluded.

## Common Issues and Hints

- **Symptom:** Git Bash path is missing. **Fix:** locate `bash.exe` under the installed Git directory.
- **Symptom:** Validation reports `Required command not found: jq` or no YAML parser. **Fix:** install `jq` and `yq`, open a new PowerShell window, and rerun validation.
- **Symptom:** Validation fails on placeholders. **Fix:** resolve only documented non-secret environment variables.
- **Symptom:** Apply targets the wrong agent. **Fix:** print subscription, resource group, and agent before execution.

## Debrief Discussion Guide

1. Why validate before apply?
2. Which layer enforces write approval?
3. Why constrain tool grants?

## Success Criteria Notes

Do not accept a direct destructive action in Review mode.
