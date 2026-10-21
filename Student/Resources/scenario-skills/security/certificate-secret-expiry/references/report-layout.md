# Report layout

This skill renders with the shared generator, tools/report_render.py, from a report_data object the scan tool prints, so the report is one pipe:

```
python tools/expiry_scan.py | python tools/report_render.py
```

## report_data this skill emits

- title: "Certificate and Secret Expiry". subtitle: certificates, secrets, and credentials by days to expiry.
- meta: window is the horizon in days, scope is the count of subscriptions scanned, source is "Key Vault, App Service, Graph".
- summary_cards: expiring within the horizon and already expired (excluding disabled items), certificates, secrets and credentials, unknown expiry and disabled records.
- charts: items by severity, and items by time bucket (Expired, within 14 days, 15 to 30 days, 31 days to horizon).
- findings: columns item, item_id, kind, source, subscription, state, expires, days_left, recommendation, severity. Rows are sorted soonest first with unknown expiry last. Missing expiry has days_left=null and an explicit unknown label. Disabled items are Low severity and remain distinguishable from active expiry risks.
- method_notes: the horizon used, any source not assessed (a vault or Graph that denied the read), and the note that embedded gateway certificates are not enumerated.
- assessment_status: Complete, Partial or Not assessed. Empty unknown scope is Not assessed; missing expiry, denied sources and unapproved directory coverage are never Complete.
- sources: objects with title and url. Application registration credentials are not all service principal credentials. Graph reads are off without a separate approved object selection or explicit tenant application enumeration consent.

## Sections the renderer produces

1. Header with title, horizon, scope, and generation time.
2. Summary cards led by expired and expiring counts.
3. Overview charts: by severity and by time bucket.
4. Findings table, sortable and filterable, sorted soonest first, severity as a coloured pill.
5. Method and limits.

Days remaining drives everything: the sort, the severity, and the time buckets. A negative value means already expired.

## Sources

- [Owned checks, metadata permissions and Graph sources](checks-catalog.md)
