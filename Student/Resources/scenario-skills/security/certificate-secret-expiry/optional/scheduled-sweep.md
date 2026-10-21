# Optional scheduled task: weekly expiry sweep

Create this in Scheduled tasks. This is the highest value cadence in the set: a weekly sweep with a 60 day horizon gives ample lead time to renew before anything expires.

- Name: Weekly certificate and secret expiry sweep
- Schedule: weekly, for example every Monday at 06:30.
- Response agent: the certificate_secret_expiry custom agent, or the main agent.
- Autonomy: Review.

## Task instructions

Run a certificate and secret expiry review across what this agent can read.

1. Use the certificate-secret-expiry skill.
2. Run expiry_scan.py with a 60 day horizon for metadata only. Explicitly report missing expiry and disabled states. Graph is off unless approved application object ids are supplied, or tenant application enumeration consent was explicitly granted for this schedule. ARM scope does not authorize directory enumeration. Service principal credentials remain outside this collector.
3. Produce the self contained HTML report and post the file link with a short summary: expired items, items expiring within 14 days, the soonest five with their dates, and any source not assessed.
4. If a previous run exists in memory, call out anything that newly entered the 14 day window since the last sweep.

Do not renew or rotate anything. Provide renewal recommendations only, for a human to act on. Raise the horizon argument ahead of a known renewal season for more lead time.

Use the approved scope and explicit identity selection described in SKILL.md. Never read secret values. Report unapproved or inaccessible sources as Not assessed and preserve collection limits, including pagination caps.
