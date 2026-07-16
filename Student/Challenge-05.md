[< Previous Challenge](./Challenge-04.md) — **[Home](../README.md)** — [Next Challenge >](./Challenge-06.md)

# Challenge 02 — Code Correlation & GitHub Integration

## Introduction

The agent diagnosed the incident. But where in the code did it come from? And once you know the root cause, how do you prevent it from happening again?

In this challenge you'll push the agent further: after it investigates the Grubify 5xx incident, you'll ask it to **correlate the failure to specific source code**, pinpoint the offending file and line, and **open a GitHub pull request** with a proposed fix — all through the same portal conversation.

This is **Scenario S2: Grubify Developer** — it requires the GitHub OAuth connector to be authorized (completed in Challenge 00). The agent reads the Grubify source code under `Student/Resources/grubify/` in this repository, uses its investigation evidence to identify the root cause in code, and creates a branch + commit + PR.

> **Prerequisite:** The GitHub OAuth connector must be authorized. In the portal, navigate to Connectors → github and confirm the status is **Connected**. If it shows *Unauthorized*, complete the OAuth sign-in before proceeding.

## Description

### Trigger the same incident as S1

```bash
Student/Resources/scenarios/scripts/break-sample-food-app.sh
```

Wait for the Azure Monitor alert to fire (~3–5 minutes) and confirm the incident appears in the agent portal.

### Ask the agent to correlate to source code and open a PR

In the **SRE Agent portal chat**, enter the following prompt (or a variation that captures the same intent):

> "For the current Grubify 5xx incident, analyze the API source code in this repository, identify the specific file and line responsible for the failure, and open a GitHub pull request with a minimal fix. Include the root cause, evidence from the logs, and the proposed change in the PR description."

### Observe the agent's behavior

Watch the agent:
1. Use its incident investigation evidence (from Azure Monitor / App Insights)
2. Read the Grubify source files via GitHub tools (`get_file_contents`, `search_code`)
3. Identify the root cause at the code level (file + line reference)
4. Create a branch, apply the fix, and open a pull request in `microsoft/frontier-sre-agent-rvas`

### Review and close

- Open the pull request the agent created and review its contents
- Check that the PR description includes: incident summary, log evidence, code snippet, and proposed fix
- Close or discard the PR after review (do not merge — this is a demo fix)

### Restore

```bash
Student/Resources/scenarios/scripts/validate-sample-food-app.sh
```

## Success Criteria

To complete this challenge, demonstrate:

1. The agent read at least one source file from `Student/Resources/grubify/` (visible in the tool call log)
2. A GitHub pull request was created in `microsoft/frontier-sre-agent-rvas` with:
   - A clear title referencing the incident
   - A description including log evidence and a code-level root cause (file + line)
   - A proposed code change (even if minimal/illustrative)
3. The PR was created by the agent (not a human commit)
4. `validate-sample-food-app.sh` returns healthy after restore
5. **Explain to your coach** — what is the difference between the agent's role in S1 (IT Ops) and S2 (Developer)? What additional capability does the GitHub connector unlock? What are the risks of an autonomous agent that can commit code and open PRs?

## Learning Resources

- [GitHub OAuth connector for SRE Agent](https://learn.microsoft.com/en-us/azure/sre-agent/connectors/github)
- [GitHub REST API — pull requests](https://docs.github.com/en/rest/pulls/pulls)
- [Azure SRE Agent — subagent capabilities](https://learn.microsoft.com/en-us/azure/sre-agent/subagents)

## Tips

- If the agent says "GitHub tool not available" or "not authorized," the OAuth connector needs to be re-authorized in the portal (Connectors → github → Authorize).
- The agent's code reading is scoped to what the OAuth token can access. If the PR creation fails with a permissions error, verify your GitHub account has write access to `microsoft/frontier-sre-agent-rvas`.
- The code fix the agent produces may be illustrative rather than production-ready — that is expected and worth discussing in the debrief.
- You can guide the agent if it gets stuck: "Focus on the Grubify API controllers under `Student/Resources/grubify/GrubifyApi/Controllers/`."
