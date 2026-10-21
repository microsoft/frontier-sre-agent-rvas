# Optional scheduled task: monthly Well-Architected scorecard

Create this in Scheduled tasks. A monthly scorecard tracks the five pillar scores over time and shows whether posture is improving.

- Name: Monthly Well-Architected scorecard
- Schedule: monthly, for example the first business day at 07:30.
- Response agent: the well_architected_review custom agent, or the main agent.
- Autonomy: Review.

## Task instructions

Run a Well-Architected review across the subscriptions this agent can read.

1. Use the well-architected-review skill.
2. Run waf_assess.py to run the curated checks across all five pillars and score each pillar.
3. Produce the self contained HTML scorecard and post the file link with a short summary: the five pillar scores and ratings, the weakest pillar, and which deep dive skill to run next.
4. If a previous run exists in memory, add a short month over month note on how each pillar score changed.

Do not change any resource. The scorecard is a roll up; route the detail to the dedicated pillar skills.
