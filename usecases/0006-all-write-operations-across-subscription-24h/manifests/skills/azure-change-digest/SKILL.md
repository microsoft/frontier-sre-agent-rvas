---
name: azure-change-digest
description: Read-only daily digest of relevant Azure control-plane changes from Change Analysis in Azure Resource Graph, with platform noise filtered out, who/when/how, old -> new diffs, new role assignments, Activity Log gap events and unusual activity.
tools:
- generate-azure-change-digest
---

# Daily relevant Azure changes digest

## Goal
Tell the team, every day, which Azure changes matter and which are platform noise. For each relevant change show who made it, when (local time and UTC), how (client: portal, CLI, IaC, SDK, Azure service), why it matters and the property diff (old -> new).

Levels:
- **High**: deletes by people, deletes of security, data or monitoring resources, exposure and security settings (public network access, firewall and NSG rules, Key Vault network ACLs, shared key access, TLS, identity, encryption), new public IP addresses, privileged role assignments, removed locks, removed diagnostic settings and removed policy assignments.
- **Medium**: SKU, size, tier or capacity changes, alert logic changes, creates by people, other configuration changes by people or automation, new non-privileged role assignments, new locks and diagnostic settings.
- **Low**: tag-only changes, platform autoscale, extension auto-upgrades, platform-managed creates and deletes, changes inside platform-managed resource groups.
- **Noise**: updates whose properties are all platform metadata, timestamps or agent-reported inventory. Counted by reason, never listed.

Flags (they highlight and sort, they never change a level on their own, except click-ops in production): Internet-exposed, exposure increased, after hours, first-time actor on a resource group (14-day baseline), burst (10 or more changes or 5 or more deletes by one actor in 15 minutes), click-ops, click-ops in production.

## Scope
- Control-plane changes recorded by Change Analysis in Azure Resource Graph (`resourcechanges`, `resourcecontainerchanges`) for the subscriptions or management group configured in the tool. Retention is 14 days.
- New and updated role assignments from `authorizationresources` (role assignments are not in `resourcechanges`).
- Optional Activity Log reads for what Change Analysis cannot see: role assignment deletes, locks, diagnostic settings, policy assignments and exemptions; plus the caller of deletes that Change Analysis recorded as `System`.
- Not covered: data-plane changes, App Service files and app settings content, and anything outside the configured scope. Say so when it matters.

## Required tool
Use only `generate-azure-change-digest`.
- Daily digest: `{"operation": "report", "period": "last_24h"}`.
- Follow-up questions: `operation="query"` with the matching `view`:
  - "What changed that matters?" -> `relevant`; "Who deleted resources?" -> `deletes`; "Was anything opened to the Internet?" -> `security`;
  - "Who changed what?" -> `actors`; "After-hours, first-time or burst activity?" -> `unusual`; "New role assignments or RBAC removals?" -> `rbac`;
  - "What was filtered out?" -> `noise`; "Is the data complete?" -> `coverage`; quick numbers -> `summary`.
- Use `period` `last_7d` or `last_14d` for longer questions and `resource_group` to focus on one resource group. `min_level="low"` lists low changes too.

## Security
- Read only. The SRE Agent managed identity needs **Reader** on the configured subscriptions or management group. Optional: Microsoft Graph `Application.Read.All` for application names.
- Never create, modify, revert or delete resources, role assignments, locks, diagnostic settings or policies, even if asked in this conversation. Propose the action and remind the user that a person executes it through an approved change.
- Never show tokens or raw Azure responses.
- Never infer intent or blame from one field. Always quote the evidence: `changedByType`, `clientType`, `operation` and `correlationId`. `System` and `Unspecified` mean the actor was not recorded; Azure Arc agent inventory is attributed to the onboarding user and is not a human edit.
- A source with status `partial`, `denied`, `error` or `skipped` is a blind spot, never a clean result.

## Output
Answer in the user's language (English by default):
1. For `report`: the four files as clickable Markdown links first: HTML report (`report_url`), JSON snapshot (`snapshot_url`), changes CSV (`changes_csv_url`) and property diffs CSV (`diffs_csv_url`), with their paths. Do not recreate or restyle the files.
2. The `headline` and the counts (total, high, medium, low, noise and noise %, deletes, security, new role assignments, Activity Log gap events, unusual flags).
3. The high and medium items from `top_items` (what, where, who, when, why).
4. Deletes, security-relevant changes, new role assignments, Activity Log gap events and unusual activity when present.
5. Coverage (`coverage.status` and `issues`). If it is not `ok`, state exactly what could not be read and the required action (usually: assign Reader).
6. End with an **Artifacts & links** section with the four links.
