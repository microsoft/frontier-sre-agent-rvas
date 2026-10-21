# Optional scheduled task: monthly FinOps sweep

Create this in Scheduled tasks. It runs the FinOps review on a schedule and posts the report.

- Name: Monthly FinOps cost optimization sweep
- Schedule: monthly, for example the first business day at 08:00.
- Response agent: the finops_cost_optimizer custom agent, or the main agent if you did not create the custom agent.
- Autonomy: Review. Cost recommendations should wait for human approval.

## Task instructions

Run a FinOps cost optimization review across the subscriptions this agent can read.

1. Use the finops-cost-optimizer skill.
2. Narrow scope by amortized spend over the last 30 days, then detect waste across the seven dimensions and enumerate idle and orphaned termination candidates with Azure Resource Graph.
3. Rank findings by estimated monthly savings, and rank termination candidates by confidence to terminate.
4. Produce separate reports per currency. Reconcile the analyzed subscription baseline, Advisor and candidate duplicates and alternative commitments before showing realizable monthly savings. Otherwise show individual estimates only. Report source windows, actual versus amortized basis, collection gaps and assessment status.
5. If a previous run exists in memory, add a short month over month note on how analyzed spend, estimated savings, and the candidate count changed.

Do not change or delete any resource. Confidence is review priority, never permission to delete. Names alone prove neither nonproduction nor idleness. Use approved scope and explicit identity selection from SKILL.md; operator commands require a separate request and the usual owner and change approvals.
