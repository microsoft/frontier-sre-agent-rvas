# Optional: file tracking issues

Off by default. Only do this if the user explicitly asks to create issues. The primary output is the HTML report.

## Targets

- GitHub: requires the GitHub connector.
- Azure DevOps: requires the Azure DevOps connector.

## Deduplication

Before creating an issue, search existing open issues for the same fingerprint and skip if found.

- Fingerprint: the resource id plus the dimension, for example /subscriptions/.../disks/abc|orphaned-disk.
- Put the fingerprint in the issue body on a line that reads Fingerprint: <value>, and label issues with cost-optimization so the search is cheap.

## Individual issue

Title: [COST-OPT] <resource type> <short description> <monthly saving> per month

Body:

- Summary: the recommendation and why.
- Monthly saving, risk rating, and priority band.
- Evidence: current configuration and the metric or field that proves the opportunity.
- Proposed change: the read only finding plus the change a human would make. Do not auto apply.
- Fingerprint line for dedup.

## EPIC issue

Title: [EPIC] Azure FinOps Cost Optimization <total monthly saving> per month potential

Body:

- Executive summary: scope analyzed, total savings, findings by priority.
- A checklist linking the individual issues, grouped by priority band.
- A note that figures are estimates to validate before acting.

Reuse the templates and the priority score from the az-cost-optimize skill for wording and structure.
