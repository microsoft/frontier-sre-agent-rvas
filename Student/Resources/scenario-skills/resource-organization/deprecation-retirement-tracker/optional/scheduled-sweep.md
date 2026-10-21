# Optional scheduled task: monthly deprecation sweep

Create this in Scheduled tasks. Retirements are announced continuously, so a monthly sweep keeps the migration backlog current and gives lead time.

- Name: Monthly deprecation and retirement sweep
- Schedule: monthly, for example the first business day at 09:00.
- Response agent: the deprecation_retirement_tracker custom agent, or the main agent.
- Autonomy: Review.

## Task instructions

Run a deprecation and retirement review across the subscriptions this agent can read.

1. Use the deprecation-retirement-tracker skill.
2. Run deprecation_scan.py to find end of life runtimes, retired tiers, classic resources, old Kubernetes versions, and end of life OS images, then corroborate the highest severity items against Azure Service Health planned retirements.
3. Produce the self contained HTML report and post the file link with a short summary: retired and end of life items, items by category, and the top items to plan first.
4. If a previous run exists in memory, call out anything newly retired or newly within a year of end of support since the last sweep.

Do not migrate or upgrade anything. Provide a planning backlog only, for a human to schedule.
