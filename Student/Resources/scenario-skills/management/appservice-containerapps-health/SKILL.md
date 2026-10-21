---
name: appservice-containerapps-health
description: Use when the user asks about App Service or Web App health, Container Apps health, web tier reliability, scaling and health probes, Always On, HTTPS and TLS enforcement, or a web workload best practices check. Reviews the App Service sites and plans and the Container Apps the agent can read for scaling, health probes, transport security, and plan tier, scores each finding by severity, and produces a self contained HTML web tier health report.
tools:
  - RunAzCliReadCommands
  - RunInTerminal
  - SaveFileToBlob
metadata:
  category: management
---

# App Service and Container Apps Health

This skill reviews the web tier this agent can read: App Service sites and plans, and Azure Container Apps. It checks scaling and health probes, transport security (HTTPS and minimum TLS), Always On, and plan tier, scores each finding by severity, and produces a single self contained HTML report. The web tier is usually the front door, so a few settings decide whether it scales under load, fails a probe cleanly, and refuses insecure traffic. It runs on demand or as a scheduled sweep.

## When to use this skill

Use this skill when the user asks to:

- Review App Service, Web App, or Container Apps health and best practices.
- Check scaling, health probes, or transport security on the web tier.
- Prepare a web workload for a launch or a load event.

## Operating principles

- Read only. This skill reads configuration. It never scales, restarts, or reconfigures a site or an app; it recommends the change.
- Approved read scope. It reads configuration across the subscriptions this agent can read. If a read is denied, it records the scope as not assessed and continues. See references/permissions-and-scope.md.
- Evidence first. It flags an explicit configuration gap, and records absent configuration as Not assessed rather than guessing or silently passing.

## Workflow

The scan tool (tools/appservice_review.py) and the shared report renderer (tools/report_render.py) are bundled with this skill. Run them with RunInTerminal using the Python in the agent runtime. The collector uses the configured identity; the local renderer does not authenticate to Azure.

### Phase 1: Review the web tier

1. Run python tools/appservice_review.py with RunInTerminal. It reads App Service sites and plans and Container Apps with Azure Resource Graph, evaluates each against the checks in references/checks-catalog.md, assigns a severity per finding, and prints a report_data object as JSON.
2. For a site that needs a closer look at its configuration, pull the detail by hand with the commands in the checks catalog.

### Validation boundary

Configure the selected managed identity using `AZURE_CLIENT_ID`, or explicitly `SRE_IDENTITY_MODE=system-assigned`. Only `SRE_IDENTITY_MODE=developer` opts in to local credentials. Confirm the approved scope before collection; playbook instructions do not enforce host authorization.

Resource Graph may omit `siteConfig`. Read `sites/config` web before concluding that TLS, Always On or Health Check is disabled. Check plan and regional applicability. Container probe coverage is per container and per Startup, Liveness and Readiness type. Portal defaults for the main ingress container do not establish defaults on sidecars, GPU profiles or API deployments; absent explicit probes are Unknown, not proof that effective probes are absent.

Reports expose `assessment_status` and `sources`. Missing configuration or failed collection prevents Complete; empty scope is Not assessed. Check definition count is not a count of successful resource checks. This review does not run probes, inspect runtime health, test dependency readiness or prove workload redundancy.

### Phase 2: Produce the report

1. Pipe the scan into the renderer: python tools/appservice_review.py | python tools/report_render.py with RunInTerminal. It writes the self contained HTML report and returns the path. Store it with SaveFileToBlob for a link.
2. Present the report, then a short inline summary: sites and apps reviewed, those with High findings, the most common gap, and the top items to address.

## Expected output

- Primary: a self contained HTML web tier health report, covering findings by severity and by category, and the full table naming the setting and the recommended change per site or app.
- Inline: sites and apps reviewed, those with High findings, and the top issues.
- Every finding names the resource, the category, the setting, a severity, and the recommended change. Nothing is reconfigured; recommendations are for a human to apply.

## Sources

- [Container Apps health probes](https://learn.microsoft.com/en-us/azure/container-apps/health-probes), portal defaults checked 2026-10-21.
- [App Service Health Check](https://learn.microsoft.com/en-us/azure/app-service/monitor-instances-health-check).

Tests use offline fixtures and mocked reads. No deployed app was queried.

## Assessment and customer sharing

Confirm the explicit customer scope and UTC window before collection. Accessible resources are not automatically approved scope. For a tool that enumerates all visible subscriptions, use an identity restricted to the approved scope or the related skill's scoped commands.

Follow [assessment states and limits](./references/assessment-contract.md), [permissions](./references/permissions-and-scope.md), and [customer sharing review](./references/customer-sharing.md), bundled during deployment. The shared renderer produces a sanitized draft by default; `--include-identifiers` requires an explicitly approved customer audience. Review custom exports with the same checklist.

Configure the host using [governance settings](./references/governance.json). General terminal access is not inherently read only. Never apply changes, schedule work, upload files or send messages without separate explicit approval.

## Approval boundary

Confirm explicit customer scope and the intended identity. Host authorization must enforce the bundled governance policy; general terminal access is not inherently read only. Changes, deployment, scheduling, uploads and messages require separate explicit approval. Preserve denied, missing and truncated evidence as unassessed, never healthy.
