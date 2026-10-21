# Optional scheduled task: monthly recurring incident review

Create this in Scheduled tasks. A monthly review of repeat offenders keeps reliability investment aimed at the workloads that actually keep breaking.

- Name: Monthly recurring incident review
- Schedule: monthly, for example the first business day at 09:00.
- Response agent: the recurring_incident_patterns custom agent, or the main agent.
- Autonomy: Review.

## Task instructions

Run a recurring incident review across the subscriptions this agent can read.

1. Use the recurring-incident-patterns skill.
2. Run pattern_scan.py over a thirty day window to aggregate fired alerts and resource health degradations by resource and rank the repeat offenders.
3. Produce a sanitized draft with assessment status, aligned queried UTC windows, resource signal counts and any pagination cap or failure. Do not label alert plus health signal counts as distinct incidents. Obtain sharing approval before publishing a link.
4. If a previous run exists in memory, note which offenders are new this month and which have improved or worsened.

The report directs reliability investment; a human decides and acts. It changes nothing.
