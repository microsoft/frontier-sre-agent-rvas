# Optional scheduled task: monthly observability coverage sweep

Create this in Scheduled tasks. New resources arrive without monitoring wiring, so a monthly sweep keeps coverage from drifting.

- Name: Monthly observability coverage sweep
- Schedule: monthly, for example the first business day at 08:30.
- Response agent: the observability_coverage_gap custom agent, or the main agent.
- Autonomy: Review.

## Task instructions

Run an observability coverage review across the subscriptions this agent can read.

1. Use the observability-coverage-gap skill.
2. Run observability_gap.py to inspect resource API diagnostic settings and enabled alert candidates with actions, types and scopes. A local workspace or action group is not required.
3. Produce a draft report with assessment status, verified configuration gaps and unknown resources. Review sanitization and sharing approval before publishing a link.
4. Compare previous runs only over the same assessed scope. Do not call resources blind solely because diagnostic settings were absent or collection failed.

Do not create any monitoring wiring. Provide recommendations only, for a human to apply.
