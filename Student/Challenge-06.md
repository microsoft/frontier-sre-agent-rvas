[< Previous Challenge](./Challenge-05.md) — **[Home](../README.md)** — [Next Challenge >](./Challenge-07.md)

# Challenge 03 — Proactive Workflow Automation

## Introduction

Incidents aren't the only thing an SRE agent can handle. What about the backlog of customer-reported issues sitting in GitHub, waiting to be triaged, labeled, and routed to the right team? Traditionally, triage happens manually — someone reads each issue, decides if it's a bug or a feature request, adds labels, and posts a comment. That takes time, and it happens inconsistently.

In this challenge, you'll see the SRE Agent handle **proactive, scheduled triage** of GitHub issues automatically. The `issue-triager` subagent runs on a schedule every 12 hours, reads unprocessed customer issues, classifies them, adds appropriate labels, and posts a structured triage comment — all without human involvement.

This is **Scenario S3: Grubify Workflow Automation**.

## Description

### Step 1 — Create sample customer issues

Create at least **3 GitHub issues** in `microsoft/frontier-sre-agent-rvas` that simulate customer-reported problems with the Grubify app. Each issue title **must** contain `[Customer Issue]` (this is the filter the triager uses to find unprocessed issues):

Example titles:
- `[Customer Issue] App crashes when adding items to cart`
- `[Customer Issue] Orders are extremely slow during peak hours`
- `[Customer Issue] Please add a dark mode to the app`

Write realistic descriptions — include symptoms, steps to reproduce (for bugs), or a feature request rationale. The richer the description, the more interesting the triage result.

> You can use the GitHub CLI: `gh issue create --title "[Customer Issue] ..." --body "..." --repo microsoft/frontier-sre-agent-rvas`

### Step 2 — Trigger the triage

The `triage-grubify-issues` scheduled task runs every **12 hours**. To see it immediately:

1. In the **SRE Agent portal**, navigate to **Scheduled Tasks → triage-grubify-issues**
2. Click **Run now** to trigger an immediate execution

Alternatively, wait for the next scheduled execution and observe the results.

### Step 3 — Observe the triage results

For each issue with `[Customer Issue]` in the title that has **not yet been triaged**:
- Check that the `issue-triager` subagent posted a comment starting with `🤖 **Grubify SRE Agent Bot**`
- Verify the comment includes a classification (Bug / Performance / Feature Request / Question)
- Verify appropriate labels were added
- For bugs, check if a sub-category label was assigned (`api-bug`, `frontend-bug`, `infrastructure`, `memory-leak`)

## Success Criteria

To complete this challenge, demonstrate:

1. At least 3 GitHub issues with `[Customer Issue]` in the title exist in the repository
2. The `issue-triager` subagent ran and posted a structured triage comment on each issue
3. Each comment includes: a classification, analysis of the issue, and suggested next steps
4. Labels were added to each issue that reflect the classification
5. Issues **without** `[Customer Issue]` in the title were skipped by the agent
6. **Explain to your coach** — what is the business value of automating issue triage? What are the risks? How would you validate the agent's classifications are accurate over time?

## Learning Resources

- [Azure SRE Agent — scheduled tasks](https://learn.microsoft.com/en-us/azure/sre-agent/scheduled-tasks)
- [GitHub Issues API](https://docs.github.com/en/rest/issues/issues)
- [GitHub Labels API](https://docs.github.com/en/rest/issues/labels)

## Tips

- The `[Customer Issue]` prefix is **case-sensitive** in the agent's prompt. Use exactly that format.
- The agent will **skip issues that already have a Grubify SRE Agent Bot comment** — this makes the triage idempotent. If you want to test re-triage, delete the bot comment or create a new issue.
- If the agent misclassifies an issue, that's a great debrief discussion point — not a failure. Classification accuracy depends on description quality and knowledge-base content.
- You can test with one issue first, then create more if the first triage looks correct.
