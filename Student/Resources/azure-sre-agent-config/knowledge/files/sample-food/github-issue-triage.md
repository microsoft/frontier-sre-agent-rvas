# Sample Food Ordering App GitHub Issue Triage Reference

Reference material for issue triage on the Sample Food Ordering App repository: the classification
taxonomy, the comment format, and the boundaries that must not be crossed. The ordered triage steps
belong to the `github-issue-triage` skill; this document supplies the vocabulary that skill applies.

## Scope

- Repository: `lpassaretta_microsoft/grubify`, the repository connected to this agent under `codeRefs/grubify`.
- Issue focus: customer issues, bugs, performance reports, memory pressure, frontend/API failures, deployment failures.

## Classification

| Label | Use when |
| --- | --- |
| `bug` | Observable app behavior is wrong or an endpoint fails. |
| `performance` | Latency, memory, CPU, or scaling symptoms are reported. |
| `frontend` | UI, React, API base URL, or browser-side behavior is involved. |
| `api` | .NET API endpoint, cart, menu, checkout, or server exception is involved. |
| `infrastructure` | Container Apps, container image or registry, identity, revision, ingress, or Terraform is involved. |
| `needs-repro` | Issue lacks steps, timestamp, or affected endpoint. |

## Triage Comment Template

```text
Thanks for the report. Initial SRE triage:

- Classification: <bug/performance/frontend/api/infrastructure>
- Affected component: <component>
- Evidence requested or found: <logs/request-id/timestamp/repro>
- Suggested next step: <action>

If this maps to a live incident, include UTC timestamp, endpoint/path, user impact, and any request ID so we can correlate with Container Apps logs and Application Insights.
```

## Guardrails

- Do not close issues automatically.
- Do not label security-sensitive issues publicly without human review.
- Do not claim VNet Flow Logs visibility for Container Apps workload traffic.

