# Optional scheduled task: monthly data platform sweep

Create this in Scheduled tasks. Database configuration drifts as new services are created, so a monthly sweep keeps the data tier posture visible.

- Name: Monthly data platform sweep
- Schedule: monthly, for example the first business day at 10:30.
- Response agent: the data_platform_review custom agent, or the main agent.
- Autonomy: Review.

## Task instructions

Run a data platform review across the subscriptions this agent can read.

1. Use the data-platform-review skill.
2. Run data_platform_review.py to evaluate SQL, PostgreSQL and MySQL Flexible Server, and Cosmos DB against the reliability checks.
3. Produce the self contained HTML report and post the file link with a short summary: services with findings, services with High findings, the most common gap by engine, and the top items to address.
4. If a previous run exists in memory, call out any new database created without high availability, geo redundant backup, or zone redundancy since the last sweep.

Do not change any database configuration. Provide recommendations only, for a human to apply.
