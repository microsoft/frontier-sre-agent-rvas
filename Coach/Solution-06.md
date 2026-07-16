[< Previous Solution](./Solution-05.md) | **[Home](./README.md)** | [Next Solution >](./Solution-07.md)

# Coach Guide — Challenge 03: Proactive Workflow Automation

## Purpose

This challenge shifts the frame from **reactive** (incidents trigger the agent) to **proactive** (the agent runs on a schedule and works through a backlog). The `issue-triager` subagent and `triage-grubify-issues` scheduled task demonstrate that SRE Agent work doesn't stop when the alerts go quiet.

Expected time: **15 minutes** (issue creation + manual trigger + observation).

## Mini-Lecture (5 min before challenge)

Cover:
- The scheduled task model: `cronExpression`, `agentMode: Autonomous`, and how the agent is prompted automatically at each tick
- The `issue-triager` subagent: classification categories (Bug, Performance, Feature Request, Question), sub-categories, label conventions, and the `🤖 **Grubify SRE Agent Bot**` comment format
- The idempotency contract: the agent skips issues that already have a bot comment — safe to re-run
- Why `[Customer Issue]` prefix: the agent filters by title to avoid triaging internal/infra issues

## Issue Creation Guidance

Provide these example issue descriptions if students are stuck:

**Bug example:**
```
Title: [Customer Issue] App crashes when adding items to cart
Body: When I tap "Add to Cart" on the Grubify mobile app, the page reloads and shows a blank screen. 
This started happening yesterday around 5 PM. I'm using Chrome on Android. 
I tried clearing the cache but the issue persists. Order ID: 12345.
```

**Performance example:**
```
Title: [Customer Issue] Orders are extremely slow during peak hours
Body: Between 12 PM and 2 PM, placing an order takes 30+ seconds. 
Outside of peak hours it's fine (under 3 seconds). I'm on a fast connection (100 Mbps).
This has been happening for the past week.
```

**Feature request example:**
```
Title: [Customer Issue] Please add a dark mode to the app
Body: The Grubify app is very bright at night. A dark mode option in settings would make 
it much more comfortable to use. Many other delivery apps have this feature.
```

## Expected Agent Behavior

For each `[Customer Issue]` issue without a bot comment:
1. Reads issue title + body
2. Classifies: Bug / Performance / Feature Request / Question
3. For bugs: selects sub-category (api-bug, frontend-bug, infrastructure, memory-leak)
4. Adds labels (classification + severity if applicable)
5. Posts comment: `🤖 **Grubify SRE Agent Bot** — [classification] — [analysis] — [next steps] — [status indicator]`
6. Skips issues without `[Customer Issue]` in title
7. Skips issues that already have a bot comment

## Common Issues and Hints

### "Run now" button not visible in portal
- The scheduled task UI may require the task to be in `enabled` state. If disabled, run `sre-agent-config.sh apply --target scheduled-tasks --name triage-grubify-issues` to re-enable
- Alternative: trigger via portal chat: "Run the Grubify issue triage now"

### Agent skips all issues
- Verify `[Customer Issue]` appears literally in the issue title (case-sensitive)
- Verify the issues are in `microsoft/frontier-sre-agent-rvas` (the repo linked to the `grubify` connector)

### Agent creates labels that don't exist in the repo
- The agent may try to create labels like `api-bug` that don't exist. This is a GitHub API behavior: label creation requires additional permissions. If it fails, the agent posts the comment without the label — this is acceptable

### Classification seems wrong
- Intentional discussion point — the agent is classifying based on its knowledge base and the issue text. Weak descriptions produce weak classifications. Use this to discuss prompt quality and runbook calibration

## Debrief Discussion Guide (10 min)

1. **How accurate were the classifications?** — Compare what the agent decided vs. what the team would have decided. Note discrepancies
2. **What would it take to run this in production?** — GitHub App with correct permissions, label taxonomy standardized, runbook for edge cases (spam, unclear issues)
3. **What's the risk of fully automated triage?** — Misclassification at scale, customer perception of bot comments, escalation path for the agent's mistakes

## Success Criteria Notes

- Accept any triage comment that includes classification + analysis + next steps, even if labels failed to attach
- The idempotency check (skipping already-triaged issues) is a key success indicator — make sure the student verifies this
- Students who only create 1 issue should go back and create at least 2 more for a meaningful comparison
