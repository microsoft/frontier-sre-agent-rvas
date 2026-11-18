---
name: sqlmi-maintenance-resilience
description: Azure SQL Managed Instance resilience to maintenance windows. Window inventory, real reconfigurations, upcoming maintenance, per-application user impact (Application Insights) and recommended window from real load. Read-only.
tools:
- generate-sqlmi-maintenance-report
---

# SQL Managed Instance and maintenance windows

## When to use this skill

- "Why do users see errors when SQL MI maintenance happens?"
- "Which maintenance window do my Managed Instances have, and which one should they have?"
- "When is the next maintenance and which applications are at risk?"
- "Which applications have no retry logic?"
- "Can we choose the exact day and hour of maintenance like on-premises?"

## Tool

`generate-sqlmi-maintenance-report` (read-only)

| Parameter | Values | Use |
|---|---|---|
| `operation` | `report` (default), `summary`, `upcoming` | `report` writes HTML + JSON + 2 CSV. `summary` returns only KPIs and actions. `upcoming` returns the next planned maintenance and the applications at risk. |
| `period` | `last_30d` (default), `last_14d`, `last_7d` | Historical analysis window. |
| `data_source` | `auto` (default), `live`, `demo` | `auto` uses real data when the tool is configured, otherwise simulated data. `demo` forces simulated data. |

Make **exactly one call** per request. Do not call again with other parameters unless the user asks.

## How to answer

1. If `mode` is `demo`, the `message` field already starts with "DEMO MODE (simulated data)". Do not repeat it; say clearly that the data is simulated.
2. For `report`, show the `message` field without changing the links (they are native SRE Agent download links).
3. Summarize in this order:
   - **Short answer** (`answer`).
   - **Next maintenance** (`next_maintenance` or `upcoming`): date, instances and applications at risk.
   - **Actions** (`top_actions` or `findings`): severity, what to do and the command when there is one.
4. Finish with the right conclusion for the case (see below).

## Conclusion that must be clear

- **Azure SQL MI offers 3 windows**: default (17:00-08:00 every day), weekday (Mon-Thu 22:00-06:00) and weekend (Fri-Sun 22:00-06:00), in the region's local time. You cannot choose an exact day and hour or postpone a specific maintenance.
- **The window decides WHEN the reconfiguration happens; retries decide IF users notice.** A reconfiguration always drops connections for a few seconds (usually < 30 s, error 40613 and similar).
- **No window covers unplanned events** (hardware, network) or some critical updates. Only retry logic with backoff in the application removes that impact.
- Complementary platform improvements: weekday or weekend window depending on load, different windows on the primary and secondary of a failover group, a Service Health alert for planned maintenance, **Redirect** connection type instead of Proxy, and manual failover drills in pre-production.

## Rules

- Read-only. **Never** change windows, connection type or alerts, and never run a failover. If the user asks, give the command from the report so their team runs it after validating it.
- Do not invent instances, applications, dates or figures: use only what the tool returns.
- If `status` is `no_data` or `error`, show `message` and the configuration steps (case README, steps 2 to 4).
- "No telemetry" means there is no Application Insights for that application, not that it is resilient.
- Answer in the user's language (English by default). The report files are in English.
