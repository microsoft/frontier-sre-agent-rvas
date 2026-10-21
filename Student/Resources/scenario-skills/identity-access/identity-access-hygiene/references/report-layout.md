# Report layout

This skill renders with the shared generator, tools/report_render.py, from a report_data object the scan tool prints, so the report is one pipe and matches the look and feel of every other report in this repository:

```
python tools/identity_access.py | python tools/report_render.py
```

## report_data this skill emits

- title: "Identity and Access Hygiene". subtitle: privileged access across the estate.
- meta: window is "Point in time", scope is the count of subscriptions scanned, source is "Azure role assignments".
- summary_cards: privileged findings, service principals with high privilege, classic administrators, subscriptions scanned.
- charts: findings by severity, and findings by role (Owner, User Access Administrator, Role Based Access Control Administrator, Contributor).
- findings: columns principal, principal_type, assignment_id, role, scope, scope_kind, subscription, recommendation, severity. Full principal, role definition and assignment ids are retained, along with custom permission evidence. Subscription ids remain stable; display names are supplemental.
- method_notes: the Owner sprawl threshold, the note that display names need a Microsoft Entra read, and any scope not assessed.
- assessment_status: Complete, Partial or Not assessed for the declared configuration checks. Failed collections are Partial, and empty unknown scope is Not assessed.
- sources: objects with title and url. Redundancy, inactivity, effective access and tenant sign ins are explicitly outside this analyzer.

## Sections the renderer produces

1. Header with title, scope, source, and generation time.
2. Summary cards led by privileged findings.
3. Overview charts: by severity and by role.
4. Findings table, sortable and filterable, severity as a coloured pill.
5. Method and limits.

Owner sprawl, high privilege service principals, and classic administrators are the High severity items worth acting on first.

## Sources

- [Owned checks and source URLs](checks-catalog.md)
