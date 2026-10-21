---
name: certificate-secret-expiry
description: Use when the user asks about expiring certificates, expiring secrets, certificate or secret rotation, "what is about to expire", Key Vault expiry, TLS certificate expiry, or service principal or app registration credential expiry. Enumerates Key Vault certificates and secrets, App Service certificates, and application credentials, ranks them by days to expiry, and produces a self contained HTML expiry report.
tools:
  - RunAzCliReadCommands
  - RunInTerminal
  - SaveFileToBlob
metadata:
  category: security
---

# Certificate and Secret Expiry

This skill reads expiry metadata for Key Vault certificates and secrets, App Service certificates and explicitly approved application registrations. Application registrations are not all service principal objects or credentials. Missing expiry and disabled items are reported distinctly, not silently omitted or counted as active expiry risks.

## When to use this skill

Use this skill when the user asks to:

- Find certificates, secrets, or credentials that are expiring or expired.
- Plan certificate and secret rotation with enough lead time.
- Check Key Vault, App Service, or application credential expiry.

## Operating principles

- Read only. This skill reads expiry metadata. It never renews, rotates, or changes a certificate or secret; it reports what needs renewing and by when.
- Source specific permissions. ARM Reader covers accessible inventory, not Key Vault metadata or Graph directory reads. Key Vault Reader reads item metadata on RBAC vaults without secret contents or key material; access policy vaults need certificate and secret list permissions. Never request secret values. Graph application permission `Application.Read.All` with administrator consent permits the application read; technical permission is not customer consent to enumerate the directory.
- Evidence first. Every finding names the item, its kind, where it lives, the expiry date, the days remaining, and the recommended action.
- Graph reads are off by default. Pass `--application-ids <approved-object-ids>` for approved applications. Use `--allow-tenant-directory` only after explicit approval for tenant application enumeration. Never infer that approval from ARM subscription scope or existing Graph permissions. Service principal credentials remain Not assessed.
- Select identity explicitly using `AZURE_CLIENT_ID`, `SRE_IDENTITY_MODE=system-assigned`, or an explicitly approved local `SRE_IDENTITY_MODE=developer` run. No silent credential fallback. Scope approval is a playbook gate, not enforcement of host access.

## Workflow

The scan tool (tools/expiry_scan.py) and the shared report renderer (tools/report_render.py) are bundled with this skill. Run them with RunInTerminal using the Python in the agent runtime. The collector uses the configured identity; the local renderer does not authenticate to Azure.

### Phase 1: Enumerate expiring items

1. Run python tools/expiry_scan.py [horizon_days] with RunInTerminal after approving the source scopes. It reads App Service and Key Vault list metadata only. Graph requires the separate explicit selection above. The horizon defaults to 60 days. Expired and expiring items are shown, plus missing expiry and disabled state evidence. Managed certificate backing secrets may appear separately; counts are item records, not distinct outage risks. Continuation limits and failures make the report Partial or Not assessed, never healthy by omission.
2. For any source the tool notes it could not read (a vault that denied the data plane read, or Graph without the directory permission), record it as not assessed rather than a failure.

### Phase 2: Produce the report

1. Pipe the scan into the renderer: python tools/expiry_scan.py | python tools/report_render.py with RunInTerminal. It writes the self contained HTML report and returns the path. Store it with SaveFileToBlob for a link.
2. Present the report, then a short inline summary: items already expired, items expiring within 14 days, the soonest five with their dates, and any source not assessed.

## Scenario coverage

This skill implements its documented checks, not every related scenario. Use the related skills for their complete evidence workflows. See [scenario routing](./references/scenarios.md).


## Expected output

- Primary: a self contained HTML expiry report, covering items by urgency and by time bucket, and the full table sorted soonest first with the days remaining and the recommended action per item.
- Inline: expired items, items expiring within 14 days, and the soonest five.
- Every finding names the item, its kind, its location, the expiry date, the days remaining, and the recommended action. Nothing is renewed or rotated; recommendations are for a human to act on.

## Sources

- [Key Vault metadata permissions](https://learn.microsoft.com/azure/key-vault/general/rbac-guide)
- [Application registration enumeration and permissions](https://learn.microsoft.com/graph/api/application-list)
- [Owned source coverage and metadata checks](references/checks-catalog.md)

## Assessment and customer sharing

Confirm the explicit customer scope and UTC window before collection. Accessible resources are not automatically approved scope. For a tool that enumerates all visible subscriptions, use an identity restricted to the approved scope or the related skill's scoped commands.

Follow [assessment states and limits](./references/assessment-contract.md), [permissions](./references/permissions-and-scope.md), and [customer sharing review](./references/customer-sharing.md), bundled during deployment. The shared renderer produces a sanitized draft by default; `--include-identifiers` requires an explicitly approved customer audience. Review custom exports with the same checklist.

Configure the host using [governance settings](./references/governance.json). General terminal access is not inherently read only. Never apply changes, schedule work, upload files or send messages without separate explicit approval.

## Approval boundary

Confirm explicit customer scope and the intended identity. Host authorization must enforce the bundled governance policy; general terminal access is not inherently read only. Changes, deployment, scheduling, uploads and messages require separate explicit approval. Preserve denied, missing and truncated evidence as unassessed, never healthy.
