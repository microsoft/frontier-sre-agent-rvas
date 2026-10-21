# Optional scheduled task: weekly quota headroom sweep

Create this in Scheduled tasks. Quotas tighten as usage grows, so a weekly sweep gives lead time to request increases before work is blocked.

- Name: Weekly quota and limit sweep
- Schedule: weekly, for example every Monday at 07:30.
- Response agent: the quota_limit_watch custom agent, or the main agent.
- Autonomy: Review.

## Task instructions

Run a quota and limit headroom check across the subscriptions this agent can read.

1. Use the quota-limit-watch skill.
2. Run quota_scan.py to read the compute, network, and storage usage counters in the regions each subscription uses, and flag counters at or above the threshold.
3. Produce the self contained HTML report and post the file link with a short summary: counters near the limit, the Critical count, and the tightest counters with region and quota name.
4. If a previous run exists in memory, add a short note on counters that moved up a band since the last sweep, and any that newly crossed the threshold.

Before a known launch or migration, lower the threshold argument for an earlier warning. Do not request or change any quota.
