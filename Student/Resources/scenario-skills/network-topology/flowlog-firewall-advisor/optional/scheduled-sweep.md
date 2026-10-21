# Optional scheduled task: monthly egress and lateral movement review

Create this in Scheduled tasks. What a workload talks to drifts as it is deployed
and changed, and the drift is invisible until something breaks or something leaks.

A monthly cadence is deliberate. This review is only as good as the window behind
it, and a month is the shortest window that reliably contains a monthly batch job.
A weekly sweep would report a smaller estate every time and look tidier while being
less true.

- Name: Monthly egress and lateral movement review
- Schedule: monthly, for example the first Monday at 06:00.
- Response agent: the flowlog_firewall_advisor custom agent, or the main agent.
- Autonomy: Review.

## Task instructions

Review what the virtual networks this agent can read are actually talking to.

1. Use the flowlog-firewall-advisor skill.
2. Run `flowlog_firewall_advisor.py --discover` to find the workspaces receiving
   VNet flow logs. Report any virtual network with flow logs but no Traffic
   Analytics, because it cannot be analysed and its absence is not a clean result.
3. Run `--coverage` and confirm the workspace holds the full window before
   analysing. Report any narrowing and any stale ingestion.
4. Run the analysis over the last 30 days, produce the self contained HTML report,
   and post the file link with a short summary: critical and high findings, the
   policy budget consumed, and the count of connections excluded because they are
   already blocked.
5. If a previous run exists in memory, call out what changed: new egress
   destinations, newly reachable management or database ports, and any connection
   that used to be blocked and is now permitted.

Point 5 is the reason this task exists. A single run describes an estate; the
difference between two runs describes a change, and a change to what a workload
reaches is the signal worth acting on.

Do not create, change, or delete any rule, policy, or firewall. Provide proposals
only, for a human to review.
