**[Home](../README.md)**

# Coach Index — Azure SRE Agent RVAS

This index links each student challenge to the corresponding coach guide. Solutions include mini-lectures, expected agent behavior, common failure modes, and debrief discussion guides.

## Challenges & Solutions

| # | Challenge | Solution | Topic | Type |
|---|-----------|----------|-------|------|
| 00 | [Challenge 00 — Prerequisites & Lab Setup](../Student/Challenge-00.md) | [Solution 00](./Solution-00.md) | Terraform deploy + SRE Agent config + GitHub OAuth | Setup |
| 01 | [Challenge 01 — Skills & Knowledge Docs](../Student/Challenge-01.md) | [Solution 01](./Solution-01.md) | Write a skill YAML + knowledge doc, apply, verify in portal | Config |
| 02 | [Challenge 02 — Subagents & Incident Filters](../Student/Challenge-02.md) | [Solution 02](./Solution-02.md) | Write a subagent + incident filter, verify routing | Config |
| 03 | [Challenge 03 — Connectors, Repos & Scheduled Tasks](../Student/Challenge-03.md) | [Solution 03](./Solution-03.md) | Connector chain, repo link, scheduled task, manual trigger | Config |
| 04 | [Challenge 04 — Autonomous App Incident Response](../Student/Challenge-04.md) | [Solution 04](./Solution-04.md) | Grubify 5xx → `aca-app-incident-handler` | Scenario |
| 05 | [Challenge 05 — Code Correlation & GitHub Integration](../Student/Challenge-05.md) | [Solution 05](./Solution-05.md) | Code analysis + GitHub PR via OAuth | Scenario |
| 06 | [Challenge 06 — Proactive Workflow Automation](../Student/Challenge-06.md) | [Solution 06](./Solution-06.md) | Scheduled triage → `issue-triager` | Scenario |
| 07 | [Challenge 07 — IaaS Service Recovery](../Student/Challenge-07.md) | [Solution 07](./Solution-07.md) | NGINX down → `iaas-vm-incident-handler` + run-command | Scenario |
| 08 | [Challenge 08 — Network Diagnostics (Interactive)](../Student/Challenge-08.md) | [Solution 08](./Solution-08.md) | UDR asymmetry → VNet Flow Logs interactive diagnosis | Scenario |
| 09 | [Challenge 09 — Autonomous NSG Remediation](../Student/Challenge-09.md) | [Solution 09](./Solution-09.md) | NSG deny → autonomous NSG rule removal | Scenario |

## Incident Routing Architecture

```
Azure Monitor Alert
        │
        ├─ titleContains "food"  ──────────► sample-food-http-errors filter ──► aca-app-incident-handler
        ├─ titleContains "nginx" ──────────► web-tier-nginx filter             ──► iaas-vm-incident-handler
        └─ everything else       ──────────► network-observability-review filter ──► network-traffic-analyst
```

## Key Subagent Capabilities

| Subagent | Write Commands | GitHub | Scheduled | Mode |
|----------|---------------|--------|-----------|------|
| `aca-app-incident-handler` | ✅ (ACA) | ✅ (OAuth) | — | Autonomous |
| `iaas-vm-incident-handler` | ✅ (run-command) | — | — | Autonomous |
| `network-traffic-analyst` | ✅ (NSG, route) | — | — | Autonomous/Interactive |
| `issue-triager` | — | ✅ (labels, comments) | ✅ | Autonomous |
| `cost-optimization-agent` | — | — | ✅ | Scheduled |
| `azure-resource-config-auditor` | — | — | — | On-demand |

## Coach-Only Resources

- [Operations Runbook](./Solutions/Solution-Demo-Runbook-02.md) — step-by-step script triggers, restore procedures, talk tracks
- [Infrastructure Guide](./Solutions/Solution-How-To-Deploy-All-00.md) — `make deploy` walkthrough, TF variable reference
- [SRE Agent Config](./Solutions/azure-sre-agent-config/README.md) — connector status, subagent inventory, config apply commands
- [Architecture Docs](./Solutions/docs/) — VNet Flow Logs, Traffic Analytics, Grubify architecture

## Coach Mode in Web UI

Open `web/index.html` and press **Shift+C** to toggle coach mode (solution guides become visible). Persists across page reloads within the same browser session.
