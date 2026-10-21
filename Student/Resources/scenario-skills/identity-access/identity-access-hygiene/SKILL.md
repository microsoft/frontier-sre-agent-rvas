---
name: identity-access-hygiene
description: Use when the user asks about identity hygiene, access reviews, least privilege, role assignments, Owner sprawl, overprivileged principals, service principals with high privilege, classic administrators, or standing access. Reads Azure role assignments across the subscriptions the agent can read, flags privileged access risks, and produces a self contained HTML access hygiene report.
tools:
  - RunAzCliReadCommands
  - RunInTerminal
  - SaveFileToBlob
metadata:
  category: identity-access
---

# Identity and Access Hygiene

This skill reviews privileged assignment configuration in approved subscriptions. It flags Owner sprawl, service principals holding known privileged roles, Owner grants to users, classic administrators and unresolved principals needing confirmation. Custom and unresolved roles are review candidates. It does not implement redundant assignment or identity inactivity analysis, determine effective privilege, or prove that an identity has been deleted.

## When to use this skill

Use this skill when the user asks to:

- Review identity hygiene, access, or least privilege.
- Find Owner sprawl, overprivileged service principals, or standing privileged access.
- Prepare for an access review or find classic administrators to retire.

## Operating principles

- Read only. This skill reads role assignments. It never grants, changes, or removes access; it reports the risk and the recommended change.
- Approved read scope. It reads assignments across the subscriptions this agent can read. Principal display names and guest status need Microsoft Entra, so the report shows the principal id and type and notes where a directory read would add detail. See references/permissions-and-scope.md.
- Evidence first. Every finding names the principal (id and type), the role, the scope, a severity, and the recommended change.
- Preserve the full principal id, assignment id, role definition id and assignment scope. An unknown principal is not a removal recommendation. Confirm identity, dependencies and permission need with the owner.
- No tenant sign in read is assumed or performed. Missing observed control plane operations does not establish that a role is unneeded; data plane operations and infrequent use may not be represented.
- Approve scope before collection. This is a playbook gate, not host authorization enforcement. Select identity explicitly using `AZURE_CLIENT_ID`, `SRE_IDENTITY_MODE=system-assigned`, or an explicitly approved local `SRE_IDENTITY_MODE=developer` run. No silent credential fallback.

## Workflow

The scan tool (tools/identity_access.py) and the shared report renderer (tools/report_render.py) are bundled with this skill. Run them with RunInTerminal using the Python in the agent runtime. The collector uses the configured identity; the local renderer does not authenticate to Azure.

### Phase 1: Read the privileged assignments

1. Run python tools/identity_access.py with RunInTerminal only after scope approval. It reads role assignments, role definitions and classic administrators. Known roles use configuration checks; custom roles and unresolved definitions require review of Actions, NotActions, DataActions, NotDataActions, conditions and inherited permissions. It does not classify every custom permission combination as privileged or safe. Failed reads and empty unknown scope are explicitly reported.
2. Owner sprawl at subscription scope, service principals holding Owner, and classic administrators are the items worth acting on first.

### Phase 2: Produce the report

1. Pipe the scan into the renderer: python tools/identity_access.py | python tools/report_render.py with RunInTerminal. It writes the self contained HTML report and returns the path. Store it with SaveFileToBlob for a link.
2. Present the report, then a short inline summary: subscriptions with Owner sprawl, service principals with high privilege, classic administrators, and any scope not assessed.

## Scenario coverage

This skill implements its documented checks, not every related scenario. Use the related skills for their complete evidence workflows. See [scenario routing](./references/scenarios.md).


## Expected output

- Primary: a self contained HTML access hygiene report, covering findings by severity and by role, and the full table naming the principal, role, scope, and recommended change.
- Inline: Owner sprawl, high privilege service principals, and classic administrators.
- Every finding names the principal (id and type), the role, the scope, a severity, and the recommended change. Nothing is changed; recommendations are for a human to apply, ideally with just in time access through Privileged Identity Management.

## Sources

- [Owned checks and coverage limits](references/checks-catalog.md)
- [Role definition permissions](https://learn.microsoft.com/azure/role-based-access-control/role-definitions)

## Assessment and customer sharing

Confirm the explicit customer scope and UTC window before collection. Accessible resources are not automatically approved scope. For a tool that enumerates all visible subscriptions, use an identity restricted to the approved scope or the related skill's scoped commands.

Follow [assessment states and limits](./references/assessment-contract.md), [permissions](./references/permissions-and-scope.md), and [customer sharing review](./references/customer-sharing.md), bundled during deployment. The shared renderer produces a sanitized draft by default; `--include-identifiers` requires an explicitly approved customer audience. Review custom exports with the same checklist.

Configure the host using [governance settings](./references/governance.json). General terminal access is not inherently read only. Never apply changes, schedule work, upload files or send messages without separate explicit approval.

## Approval boundary

Confirm explicit customer scope and the intended identity. Host authorization must enforce the bundled governance policy; general terminal access is not inherently read only. Changes, deployment, scheduling, uploads and messages require separate explicit approval. Preserve denied, missing and truncated evidence as unassessed, never healthy.
