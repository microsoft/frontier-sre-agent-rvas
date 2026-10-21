# Optional scheduled task: monthly web tier health sweep

Create this in Scheduled tasks. Web apps are created and reconfigured often, so a monthly sweep keeps the front door healthy.

- Name: Monthly web tier health sweep
- Schedule: monthly, for example the first business day at 11:00.
- Response agent: the appservice_containerapps_health custom agent, or the main agent.
- Autonomy: Review.

## Task instructions

Run a web tier health review across the subscriptions this agent can read.

1. Use the appservice-containerapps-health skill.
2. Run appservice_review.py to evaluate App Service sites and plans and Container Apps against the health checks.
3. Produce the self contained HTML report and post the file link with a short summary: resources reviewed, resources with High findings, the most common gap, and the top items to address.
4. If a previous run exists in memory, call out any new site or app that does not enforce HTTPS or cannot scale out since the last sweep.

Do not scale, restart, or reconfigure any site or app. Provide recommendations only, for a human to apply.
