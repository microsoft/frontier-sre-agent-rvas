---
name: operations-digest-live
description: Read-only periodic Azure Operations Executive and Technical Digest consolidating native alerts, Service Health events, control-plane/extension anomalies, Log Analytics telemetry anomalies, and prioritized recommended actions.
tools:
- generate-operations-digest-report
---

# Periodic Azure Operations, Incidents, Anomalies, and Recommended Actions Digest

Use ONLY `generate-operations-digest-report`. The operator must explicitly
select that single tool and this skill for `operations-digest-live`; do not
enable inherited tools, shell, exec, generic Python, remediation connectors, or
write operations.

## Scope, identity, and monthly/on-demand cadence

The code contains fixed administrator constants: `SUBSCRIPTION_ID`,
`MANAGED_IDENTITY_CLIENT_ID`, `APPROVED_LOG_WORKSPACES`, `CLIENT_NAME`,
`CLIENT_LOGO_DATA_URI`, `CLIENT_LOGO_ALT`, and `OUTPUT_DIRECTORY`. Tool
parameters cannot alter subscription scope, managed identity, Log Analytics
workspace GUIDs, endpoints, KQL queries, or filesystem paths.

- If the fixed configuration still contains `<PLACEHOLDER>` values, the tool
  stops before any authentication or network call with `status="error"` and
  `error.code="configuration_required"` (`artifact_status="not_written"`).
- Scheduled automation runs **monthly** on day 1 at 08:30 UTC (`30 8 1 * *`)
  using the default `period="previous_month"`.
- On-demand runs additionally support `period="last_30d"`, `period="last_7d"`
  (weekly rolling window), and `period="last_24h"` (daily operational shift).

## Five read-only Azure evidence streams

1. **`arg_alerts_incidents`**: Queries `alertsmanagementresources`
   (`microsoft.alertsmanagement/alerts`) for active, acknowledged, or resolved
   Azure Monitor alerts (`Sev0`..`Sev4`) overlapping the window.
2. **`arm_service_health`**: Queries
   `Microsoft.ResourceHealth/events?api-version=2022-10-01` for `ServiceIssue`
   and `PlannedMaintenance` events overlapping the window.
3. **`arg_posture_anomalies` & `arg_guest_extensions`**: Queries Azure Resource
   Graph across Azure VMs, Azure Arc machines (`Expired`/`Disconnected` agents),
   VM/Arc guest extensions (`provisioningState == "Failed"` such as
   `MDE.Windows` or `AADLoginForWindows`), stopped/degraded AKS clusters,
   Container Apps, App Services, Storage accounts, and Key Vaults. Never reads
   `settings` or `protectedSettings`.
4. **`logs_telemetry_anomalies`**: Queries approved Log Analytics workspaces
   (`InsightsMetrics`, `Perf`, `Heartbeat` via
   `https://api.loganalytics.io/v1/workspaces/{workspace_id}/query`) for CPU,
   memory, and disk pressure spikes, statistical outliers, and heartbeat silence
   gaps.
5. **`arm_advisor_recommendations`**: Queries cached
   `Microsoft.Advisor/recommendations` and synthesizes a prioritized
   **Recommended Actions** ledger linked to exact
   incident, anomaly, and Advisor IDs across three horizons (`Immediate <24h`,
   `Short term 1-7 days`, `Monthly cycle`).

## Report and four-file native delivery

For a report, make **exactly one call** with `operation="report"` and the
requested `period` (`"previous_month"`, `"last_30d"`, `"last_7d"`, or
`"last_24h"`), leaving all query-only filters at their defaults. **Immediately
render all four generated files**:

- `report_path` / `report_url`: `ops-digest-<timestamp>-<hash>.html`
- `snapshot_path` / `snapshot_url`: `ops-digest-<timestamp>-<hash>-snapshot.json`
- `incidents_csv_path` / `incidents_csv_url`: `ops-digest-<timestamp>-<hash>-incidents.csv`
- `actions_csv_path` / `actions_csv_url`: `ops-digest-<timestamp>-<hash>-actions.csv`

When `sharing_mode="native_ui"`, render all four unchanged `*_url` values as
native Markdown links/file widgets in the same response. Never invent or reuse a
thread UUID or host prefix. When `sharing_mode="local_files_only"`, expose the
unchanged actual `*_path` values and note that `cwd` is outside the native
runtime thread root.

The HTML report, CSVs, and snapshot text are in English. Answer in the user's
language (English by default).

## Grounded questions

Use `operation="query"` with `view` in `summary`, `incidents`, `anomalies`,
`actions`, `resources`, `advisor`, or `coverage`, plus optional `category`,
`severity`, `resource_name`, `limit`, and `offset`. Always disclose exact
`total_matched`, `returned`, `has_more`, `next_offset`, and `transport_capped`
under the 3,500-byte JSON budget.
