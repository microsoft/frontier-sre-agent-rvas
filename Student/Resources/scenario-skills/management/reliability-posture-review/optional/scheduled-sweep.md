# Optional scheduled task: monthly reliability sweep

Create this in Scheduled tasks. It runs the reliability review on a schedule and posts the scorecard.

- Name: Monthly reliability posture sweep
- Schedule: monthly, for example the first business day at 08:00.
- Response agent: the reliability_posture_review custom agent, or the main agent if you did not create the custom agent.
- Autonomy: Review. Reliability changes should wait for human approval.

## Task instructions

Run a reliability posture review across the subscriptions this agent can read.

1. Use the reliability-posture-review skill.
2. Run reliability_scan.py to find single points of failure and redundancy gaps with Azure Resource Graph, then confirm severity against the scoring method.
3. Produce the self contained HTML scorecard and post the file link with a short summary: resources with findings, findings by severity, the top subscriptions, and the highest severity items.
4. If a previous run exists in memory, add a short month over month note on how the Critical and High count changed.

Do not change any resource. Provide configuration recommendations only, for a human to apply.
