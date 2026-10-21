# Optional scheduled task: monthly AKS reliability sweep

Create this in Scheduled tasks. Cluster configuration and supported versions drift, so a monthly sweep keeps the fleet current.

- Name: Monthly AKS reliability sweep
- Schedule: monthly, for example the first business day at 10:00.
- Response agent: the aks_reliability_review custom agent, or the main agent.
- Autonomy: Review.

## Task instructions

Run an AKS reliability review across the subscriptions this agent can read.

1. Use the aks-reliability-review skill.
2. Run aks_review.py to evaluate each cluster against the reliability and operational checks.
3. Produce the self contained HTML report and post the file link with a short summary: clusters reviewed, clusters with High findings, the most common gap, and the top clusters to address.
4. If a previous run exists in memory, call out clusters that fell below the supported Kubernetes floor since the last sweep.

Do not upgrade, scale, or reconfigure any cluster. Provide recommendations only, for a human to apply.
