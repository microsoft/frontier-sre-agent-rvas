[< Previous Solution](./Solution-17.md) | **[Home](./README.md)** | [Next Solution >](./Solution-19.md)

# Coach Guide — Challenge 18: Subscription Cost Optimization Review

## Purpose

- Teach FinOps-style, evidence-backed cost review with business context, not blind “downsize everything” advice.
- This challenge is also a governance showcase: powerful analysis, zero resource modification.
- Expected time: 25–30 minutes.

## Mini-Lecture (5–7 min before challenge)

- Name the specialist and cadence: `cost-optimization-agent`, task `cost-optimization-review`, cron `0 7 * * 1`.
- Explain the evidence stack: workload cost profiles + Resource Graph inventory + Cost Management Query API + Azure Monitor utilization + Azure Advisor.
- Highlight the design principle: recommendations only; no write tools by design.
- Good whiteboard sequence: inventory → spend → utilization → Advisor → de-duplicate → prioritized savings table.

## Expected Student Output

- Agent produces a prioritized savings table with multiple recommendations and trade-offs.
- Recommendations reference workload context from cost knowledge docs.
- At least one orphaned/idle resource opportunity is surfaced.
- Student can drill into evidence for the top recommendation.

## Common Issues and Hints

- **Symptom:** Cost query permissions fail up front. **Fix:** confirm Cost Management read access before starting the challenge.
- **Symptom:** Output is generic Advisor paraphrase. **Fix:** press for utilization data and knowledge-doc context.
- **Symptom:** Agent suggests immediate deletes/resizes. **Fix:** remind students the agent is read-only and should recommend only.
- **Symptom:** Duplicate recommendations appear. **Fix:** ask the student to explain how Advisor and inventory findings should be de-duplicated.

## Debrief Discussion Guide

- Why is read-only the right default for cost optimization? → Financial and reliability risk from accidental downsizing or deletion.
- Why are workload cost profiles essential? → Technical savings without business context are often bad recommendations.
- What org change would be needed before enabling writes? → Trust, approvals, rollback, and ownership agreements.

## Success Criteria Notes

- Be strict on evidence and read-only posture.
- Accept some variation in recommendation count if the environment is small, but look for distinct categories.
- If Cost Management permissions are missing, use that as a governance teaching moment rather than letting the challenge drift.
