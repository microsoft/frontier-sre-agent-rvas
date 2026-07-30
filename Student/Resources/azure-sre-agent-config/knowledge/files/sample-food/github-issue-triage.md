# Sample Food Ordering App GitHub Issue Triage Runbook

Use this runbook when GitHub OAuth/source tools are connected to Azure SRE Agent and the team wants issue triage for the Sample Food Ordering App repository.

## Scope

- Repository: `microsoft/frontier-sre-agent-rvas` (the Grubify application source is under `Student/Resources/grubify/`), or the repo configured in Terraform output `sample_food_app_source_repo`.
- Issue focus: customer issues, bugs, performance reports, memory pressure, frontend/API failures, deployment failures.

## Classification

| Label | Use when |
| --- | --- |
| `bug` | Observable app behavior is wrong or an endpoint fails. |
| `performance` | Latency, memory, CPU, or scaling symptoms are reported. |
| `frontend` | UI, React, API base URL, or browser-side behavior is involved. |
| `api` | .NET API endpoint, cart, menu, checkout, or server exception is involved. |
| `infrastructure` | Container Apps, ACR, identity, revision, ingress, or Terraform is involved. |
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

