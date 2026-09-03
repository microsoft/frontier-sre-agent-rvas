[< Previous Solution](./Solution-15.md) | **[Home](./README.md)** | [Next Solution >](./Solution-17.md)

# Coach Guide — Challenge 16: Daily Network Health Report

## Purpose

- Demonstrate proactive operations: the agent scans for patterns before a specific incident is raised.
- This is also the clearest reuse case for `network-traffic-analyst` beyond break/fix work.
- Expected time: 20 minutes.

## Mini-Lecture (3–5 min before challenge)

- Name the scheduled task exactly: `daily-network-observability-health`, cron `0 6 * * *`, agent `network-traffic-analyst`, mode `Autonomous`.
- Explain the five report dimensions students should hear: denied flows, top talkers, missing VNet coverage, unusual ports, ingestion delays.
- Connect it to earlier labs: historical artifacts from NSG/UDR faults may still appear inside a 24-hour window.
- Clarify that the task's safety comes from its narrative-only prompt ("Do not change resources") and the subagent having no write path invoked for this task — not from an `agentMode: Review` gate, since this task is configured `Autonomous`.

## Expected Student Output

- Manual `/agent network-traffic-analyst` run produces a structured 24-hour report over `NTANetAnalytics`.
- Report discusses all three VNets and mentions missing coverage if any are absent.
- Student can read the scheduled task in the portal and explain schedule, mode, and assigned specialist.
- Student can articulate why the same specialist serves both proactive and reactive paths.

## Common Issues and Hints

- **Symptom:** Report is raw KQL dump. **Fix:** ask for a decision-ready narrative report.
- **Symptom:** Missing coverage is not addressed. **Fix:** coach should ask explicitly whether hub, app spoke, and data spoke all produced records.
- **Symptom:** Student thinks scheduled task should remediate. **Fix:** remind them this one says “Do not change resources” in its prompt — that's the safety control here, since the task mode is `Autonomous`, not `Review`.

## Debrief Discussion Guide

- How is a scheduled report trigger different from an incident filter trigger? → Cron vs alert.
- Why reuse one network specialist for both paths? → Shared domain context and less duplication.
- What is the value of a narrative report over a dashboard? → It highlights what matters without manual interpretation.

## Success Criteria Notes

- Be strict on all five dimensions appearing.
- Accept manual triggering of the scheduled task or equivalent direct specialist prompt.
- If the lab is new and data is thin, allow a shorter lookback but preserve the structure.
