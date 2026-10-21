# Optional scheduled task: monthly tag compliance sweep

Create this in Scheduled tasks. New resources arrive untagged, so a monthly sweep keeps ownership and chargeback data clean.

- Name: Monthly tag governance sweep
- Schedule: monthly, for example the first business day at 09:30.
- Response agent: the tag_governance_compliance custom agent, or the main agent.
- Autonomy: Review.

## Task instructions

Run a tag governance review across the subscriptions this agent can read.

1. Use the tag-governance-compliance skill.
2. Run tag_compliance.py with required tags and the approved type support mapping. Match names case insensitively only, retain separators and fail blank values. Unknown tag support is Not assessed; unsupported types are excluded.
3. Produce the self contained HTML report and post the file link with a short summary: compliance percent, resources missing an owner, the most common missing tag, and the top subscriptions by gap.
4. If a previous run exists in memory, note whether compliance percent rose or fell and call out any subscription that regressed.

Do not set or change any tag. Recommend the fixes and enforcing the standard with Azure Policy for a human to apply.

Use only approved scope and explicit identity selection from SKILL.md. Empty or inaccessible scope is Not assessed, not 100 percent. Compare percentages only with the same assessed denominator and standard.
