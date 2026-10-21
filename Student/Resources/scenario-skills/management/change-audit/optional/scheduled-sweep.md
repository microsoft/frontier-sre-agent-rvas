# Optional scheduled task: weekly change audit

Create this in Scheduled tasks. A weekly audit keeps a running record of what changed and whether it hurt, which shortens the next incident.

- Name: Weekly change audit
- Schedule: weekly, for example every Monday at 07:00.
- Response agent: the change_audit custom agent, or the main agent.
- Autonomy: Review.

## Task instructions

Run a change audit across the subscriptions this agent can read.

1. Use the change-audit skill.
2. Run change_scan.py over a seven day window to read the Activity Log, separate changes from resource health events, and correlate each degradation with the changes that preceded it.
3. Produce the self contained HTML report and post the file link with a short summary: changes linked to a degradation, deletes, failed changes, and the busiest changers.
4. If a previous run exists in memory, note any resource that shows a repeated pattern of a change followed by a degradation.

Do not roll back or re apply any change. The report is for a human to judge and act on.
