# Optional scheduled task: weekly alert hygiene sweep

Create this in Scheduled tasks. A weekly review keeps the pager trustworthy by catching noise before it trains people to ignore alerts.

- Name: Weekly alert hygiene sweep
- Schedule: weekly, for example every Friday at 16:00, so tuning lands before the weekend on call.
- Response agent: the alert_hygiene_review custom agent, or the main agent.
- Autonomy: Review.

## Task instructions

Run an alert hygiene review across the subscriptions this agent can read.

1. Use the alert-hygiene-review skill.
2. Run alert_hygiene.py over seven days to measure fire count, monitor resolution, user closure, timestamp proven rapid resolution and current New state separately. Closure does not prove inaction.
3. Produce a sanitized draft with assessment status, noisy rules, measured rapid resolutions, disabled rules and collection caps. Obtain sharing approval before publishing a link.
4. If a previous run exists in memory, add a short note on whether the noisiest rules changed and whether total fires rose or fell.

Do not change or disable any alert rule. Provide tuning recommendations only, for a human to apply.
