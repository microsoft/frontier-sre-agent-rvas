"""sre-usecase-builder-kit - turn a use-case spec into a tested Azure SRE Agent Python tool and the 4 Builder blocks.

Operations (parameter `operation`):
  catalog      compact index of recipes, source types, operators and spec fields; spec_json=<recipe|source type|spec|
               operators|all> returns the details of that topic (e.g. the full spec of a recipe to copy)
  environment  what the agent managed identity can see: subscriptions, Log Analytics workspaces, storage accounts,
               Azure roles and Microsoft Graph app roles already granted
  probe        build the tool from `spec_json` and run it LIVE in discover mode: real columns, field check, permission fixes
  scaffold     validate `spec_json`, generate the tool, lint it, run its self_test (network blocked), run a live check
               when the agent identity is available, then write the 4 Builder blocks + setup guide to the thread
  brand        spec_json={"website": "https://www.customer.com"} (or logo_url): reads the customer's site, proposes logo,
               colours and font, caches the logo for scaffold and returns a branded sample report (HTML + PDF) to show
  get          spec_json='<name>/<part>[/<page>]' returns a generated part page by page (answer, tool, config, skill,
               subagent, task, permissions, tests, setup, code, spec)
  lint         static safety and contract checks for any Python tool passed in `code`
Every answer fits the ~4,000-character tool-result budget of Azure SRE Agent; long content is paged or saved to files.
The kit is read-only: it never creates, changes or deletes Azure resources, permissions or Builder objects.
"""
import ast
import base64
import contextlib
import difflib
import hashlib
import io
import json
import os
import pprint
import re
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

KIT_VERSION = "3.1.1"
ARM = "https://management.azure.com"


def main(operation: str = "catalog", spec_json: str = "", code: str = "") -> dict:
    """Entry point. Kept at the top so the Builder Test playground detects the parameters; the logic is _kit_main."""
    return _kit_main(operation, spec_json, code)


# While embedded, the template's main() is renamed so Builder only detects the kit's own main().
TEMPLATE = r'''__TEMPLATE__'''.replace("\ndef __TEMPLATE_MAIN__(", "\ndef main(")

SEVERITIES = ["critical", "high", "medium", "low", "info"]
TOOL_NAME_MAX = 36  # Tool Name limit of the SRE Agent portal; a generated tool is named run-<name>
NAME_MAX = TOOL_NAME_MAX - len("run-")
OPERATORS = {
    "eq": "equals value (case-insensitive text)", "ne": "differs from value", "in": "is one of value[list]",
    "not_in": "is not one of value[list]", "contains": "contains value (text)", "regex": "matches regex value",
    "gt": "number > value", "gte": "number >= value", "lt": "number < value", "lte": "number <= value",
    "empty": "is empty or missing", "not_empty": "has a value", "expired": "date is in the past",
    "expires_within_days": "date is within the next value days (includes already expired)",
    "older_than_days": "date is older than value days", "newer_than_days": "date is within the last value days",
}
NO_VALUE_OPS = {"empty", "not_empty", "expired"}
AGGREGATIONS = {"count": "rows (after optional where)", "distinct": "distinct values of field", "sum": "sum of field",
                "avg": "average of field", "max": "max of field", "min": "min of field"}
CRON_PRESETS = {"hourly": "0 * * * *", "daily": "0 7 * * *", "weekdays": "0 7 * * 1-5", "weekly": "0 7 * * 1",
                "monthly": "0 7 1 * *"}

SOURCE_TYPES = {
    "log_analytics": {
        "required": ["workspace_id", "query"], "optional": ["max_rows", "sample_rows"], "permission": "log_analytics",
        "notes": "workspace_id = workspace customerId GUID (operation environment lists them). KQL. Use ago({days}d) "
                 "for the lookback window. Project only the columns you need and give them stable names.",
    },
    "resource_graph": {
        "required": ["query"], "optional": ["subscriptions", "explode", "max_rows", "sample_rows"], "permission": "reader",
        "notes": "Azure Resource Graph KQL (tables resources, advisorresources, healthresources, securityresources, "
                 "patchassessmentresources, servicehealthresources). Paged automatically. Omit subscriptions = all visible.",
    },
    "graph": {
        "required": ["path"], "optional": ["advanced_query", "explode", "max_rows", "sample_rows"], "permission": "graph",
        "notes": "Microsoft Graph GET path such as v1.0/applications?$select=... Paged by @odata.nextLink. Use explode to "
                 "turn an array property (passwordCredentials) into one row per element (fields become prop.child; parents with an empty array are dropped).",
    },
    "arm": {
        "required": ["path"], "optional": ["explode", "max_rows", "sample_rows"], "permission": "reader",
        "notes": "Azure Resource Manager GET path starting with /subscriptions/... and including ?api-version=. Paged by nextLink.",
    },
    "cost_management": {
        "required": ["scope"], "optional": ["group_by", "body", "sample_rows"], "permission": "cost",
        "notes": "scope = /subscriptions/<id> or /subscriptions/<id>/resourceGroups/<rg>. Default body: ActualCost for the "
                 "lookback window grouped by group_by (ResourceGroupName, ServiceName, ResourceId, MeterCategory...). "
                 "Columns: Cost, <group_by>, Currency.",
    },
    "adx": {
        "required": ["cluster_url", "database", "query"], "optional": ["max_rows", "sample_rows"], "permission": "adx",
        "notes": "Azure Data Explorer KQL. cluster_url like https://<cluster>.<region>.kusto.windows.net",
    },
    "sharepoint_file": {
        "required": ["folder"], "one_of": [["site_id", "site_url"]],
        "optional": ["file", "pattern", "sheet", "header_row", "all_sheets", "delimiter", "json_path", "max_rows", "sample_rows"],
        "permission": "sharepoint_read",
        "notes": "Reads the most recently modified file in folder that matches file/pattern (default *.xlsx) in memory: "
                 ".xlsx/.xlsm (openpyxl), .csv (; or , detected) or .json. site_url like https://contoso.sharepoint.com/sites/Ops. "
                 "folder is relative to the default document library root, e.g. Informes/ADFS.",
    },
    "blob_file": {
        "required": ["account", "container"], "optional": ["prefix", "file", "pattern", "sheet", "header_row", "all_sheets",
                                                          "delimiter", "json_path", "max_rows", "sample_rows"],
        "permission": "blob_read",
        "notes": "Reads the newest blob under prefix matching file/pattern (default *.csv). Same formats as sharepoint_file.",
    },
}

GRAPH_ROLES = [
    (r"(applications|serviceprincipals)", "Application.Read.All"), (r"users/[^/]+/authentication", "UserAuthenticationMethod.Read.All"),
    (r"users", "User.Read.All"), (r"groups", "GroupMember.Read.All"), (r"auditlogs/signins", "AuditLog.Read.All + Directory.Read.All"),
    (r"auditlogs", "AuditLog.Read.All"), (r"(rolemanagement|directoryroles)", "RoleManagement.Read.Directory"),
    (r"security/alerts", "SecurityAlert.Read.All"), (r"security/incidents", "SecurityIncident.Read.All"),
    (r"devicemanagement", "DeviceManagementManagedDevices.Read.All"), (r"devices", "Device.Read.All"),
    (r"reports", "Reports.Read.All"), (r"(identity/conditionalaccess|policies)", "Policy.Read.All"),
    (r"identityprotection", "IdentityRiskyUser.Read.All"), (r"sites", "Sites.Selected"), (r"domains", "Domain.Read.All"),
    (r"(organization|subscribedskus)", "Organization.Read.All"),
]

RECIPES = [
    {"name": "vm-heartbeat-gaps", "use": "Weekly report of machines (Azure VMs and Arc servers) that stopped sending heartbeats.",
     "spec": {
         "name": "vm-heartbeat-gaps", "title": "Machines without heartbeat", "language": "en",
         "description": "Detect Azure VMs and Arc-enabled servers that stopped reporting to Log Analytics, before users notice.",
         "sources": [{"id": "heartbeat", "type": "log_analytics", "workspace_id": "<workspace customerId>",
                      "query": "Heartbeat\n| where TimeGenerated > ago({days}d)\n| summarize LastHeartbeat = max(TimeGenerated), "
                               "OSType = take_any(OSType), ComputerEnvironment = take_any(ComputerEnvironment), "
                               "ResourceGroup = take_any(ResourceGroup) by Computer\n| extend HoursSilent = round((now() - LastHeartbeat) / 1h, 1)"}],
         "rules": [{"id": "silent_24h", "dataset": "heartbeat", "severity": "high", "title": "No heartbeat for more than 24 h",
                    "when": {"field": "HoursSilent", "op": "gt", "value": 24}, "message": "{Computer} silent for {HoursSilent} h (last {LastHeartbeat})"},
                   {"id": "silent_1h", "dataset": "heartbeat", "severity": "medium", "title": "No heartbeat for 1-24 h",
                    "when": {"all": [{"field": "HoursSilent", "op": "gt", "value": 1}, {"field": "HoursSilent", "op": "lte", "value": 24}]},
                    "message": "{Computer} silent for {HoursSilent} h"}],
         "kpis": [{"id": "machines", "label": "Machines reporting in window", "dataset": "heartbeat"},
                  {"id": "silent", "label": "Silent > 1 h", "dataset": "heartbeat", "good": "down",
                   "where": {"field": "HoursSilent", "op": "gt", "value": 1}}],
         "tables": [{"title": "Silent machines", "dataset": "heartbeat", "columns": ["Computer", "OSType", "ComputerEnvironment", "ResourceGroup", "LastHeartbeat", "HoursSilent"],
                     "sort": "HoursSilent", "desc": True, "where": {"field": "HoursSilent", "op": "gt", "value": 1}}],
         "charts": [{"title": "Silent machines by resource group", "dataset": "heartbeat", "by": "ResourceGroup", "where": {"field": "HoursSilent", "op": "gt", "value": 1}},
                    {"title": "Machines by operating system", "dataset": "heartbeat", "by": "OSType"}],
         "labels": {"HoursSilent": "Hours silent", "ComputerEnvironment": "Environment", "LastHeartbeat": "Last heartbeat"},
         "keys": {"heartbeat": ["Computer"]}, "schedule": "weekdays"}},
    {"name": "entra-app-secrets-expiry", "use": "Entra ID app registrations with client secrets expired or expiring soon.",
     "spec": {
         "name": "entra-app-secrets-expiry", "title": "Entra app secrets expiring", "language": "en",
         "description": "Find app registration client secrets that are expired or expire within 30 days so owners rotate them before outages.",
         "sources": [{"id": "secrets", "type": "graph", "explode": "passwordCredentials",
                      "path": "v1.0/applications?$select=id,appId,displayName,passwordCredentials&$top=999"}],
         "derive": [{"name": "days_left", "dataset": "secrets", "field": "passwordCredentials.endDateTime", "type": "days_until"}],
         "rules": [{"id": "expired", "dataset": "secrets", "severity": "critical", "title": "Secret expired",
                    "when": {"field": "passwordCredentials.endDateTime", "op": "expired"},
                    "message": "{displayName}: secret '{passwordCredentials.displayName}' expired {passwordCredentials.endDateTime}"},
                   {"id": "expiring_30d", "dataset": "secrets", "severity": "high", "title": "Secret expires within 30 days",
                    "when": {"all": [{"field": "days_left", "op": "gte", "value": 0}, {"field": "days_left", "op": "lte", "value": 30}]},
                    "message": "{displayName}: secret '{passwordCredentials.displayName}' expires in {days_left} days"}],
         "kpis": [{"id": "apps", "label": "Apps with secrets", "dataset": "secrets", "agg": "distinct", "field": "appId"},
                  {"id": "expired", "label": "Expired secrets", "dataset": "secrets", "good": "down",
                   "where": {"field": "passwordCredentials.endDateTime", "op": "expired"}},
                  {"id": "expiring", "label": "Expiring in 30 days", "dataset": "secrets", "good": "down",
                   "where": {"all": [{"field": "days_left", "op": "gte", "value": 0}, {"field": "days_left", "op": "lte", "value": 30}]}}],
         "tables": [{"title": "Secrets by expiry", "dataset": "secrets", "columns": ["displayName", "appId", "passwordCredentials.displayName", "passwordCredentials.endDateTime", "days_left"],
                     "sort": "days_left", "where": {"field": "days_left", "op": "lte", "value": 90}}],
         "charts": [{"title": "Secrets by days to expiry", "dataset": "secrets", "by": "days_left", "buckets": [0, 30, 90]},
                    {"title": "Apps with most secrets", "dataset": "secrets", "by": "displayName", "limit": 8}],
         "labels": {"displayName": "Application", "passwordCredentials.displayName": "Secret", "passwordCredentials.endDateTime": "Expires", "days_left": "Days left"},
         "keys": {"secrets": ["appId", "passwordCredentials.keyId"]}, "schedule": "weekly"}},
    {"name": "advisor-high-impact", "use": "Azure Advisor high-impact recommendations across all visible subscriptions.",
     "spec": {
         "name": "advisor-high-impact", "title": "Azure Advisor high-impact recommendations", "language": "en",
         "description": "Track high-impact Advisor recommendations (reliability, security, cost, performance) and what changed since last week.",
         "sources": [{"id": "advisor", "type": "resource_graph",
                      "query": "advisorresources\n| where type == 'microsoft.advisor/recommendations'\n| extend Category = tostring(properties.category), "
                               "Impact = tostring(properties.impact), Problem = tostring(properties.shortDescription.problem), "
                               "Resource = tostring(properties.resourceMetadata.resourceId), Updated = tostring(properties.lastUpdated)\n"
                               "| project id, subscriptionId, resourceGroup, Category, Impact, Problem, Resource, Updated"}],
         "rules": [{"id": "high_security_reliability", "dataset": "advisor", "severity": "high", "title": "High impact security/reliability",
                    "when": {"all": [{"field": "Impact", "op": "eq", "value": "High"}, {"field": "Category", "op": "in", "value": ["Security", "HighAvailability"]}]},
                    "message": "{Category}: {Problem} ({resourceGroup})"},
                   {"id": "high_other", "dataset": "advisor", "severity": "medium", "title": "High impact cost/performance",
                    "when": {"all": [{"field": "Impact", "op": "eq", "value": "High"}, {"field": "Category", "op": "in", "value": ["Cost", "Performance", "OperationalExcellence"]}]},
                    "message": "{Category}: {Problem} ({resourceGroup})"}],
         "kpis": [{"id": "total", "label": "Recommendations", "dataset": "advisor", "good": "down"},
                  {"id": "high", "label": "High impact", "dataset": "advisor", "good": "down", "where": {"field": "Impact", "op": "eq", "value": "High"}}],
         "tables": [{"title": "High impact", "dataset": "advisor", "columns": ["Category", "Problem", "resourceGroup", "Resource", "Updated"],
                     "sort": "Category", "where": {"field": "Impact", "op": "eq", "value": "High"}}],
         "charts": [{"title": "Recommendations by category", "dataset": "advisor", "by": "Category"},
                    {"title": "Resource groups with most recommendations", "dataset": "advisor", "by": "resourceGroup", "limit": 8}],
         "keys": {"advisor": ["id"]}, "schedule": "weekly"}},
    {"name": "sharepoint-excel-register", "use": "Excel register kept in SharePoint (certificates, contracts, licences) with expiry dates.",
     "spec": {
         "name": "certificate-register", "title": "Certificate register", "language": "en",
         "description": "Read the team's certificate Excel in SharePoint, flag expired and soon-to-expire items and keep a history of changes.",
         "sources": [{"id": "register", "type": "sharepoint_file", "site_url": "https://<tenant>.sharepoint.com/sites/<site>",
                      "folder": "<library folder, e.g. Shared Documents/Certificates>", "pattern": "*.xlsx", "header_row": 1}],
         "derive": [{"name": "days_left", "dataset": "register", "field": "ExpiryDate", "type": "days_until"}],
         "rules": [{"id": "expired", "dataset": "register", "severity": "critical", "title": "Expired", "when": {"field": "ExpiryDate", "op": "expired"},
                    "message": "{Certificate} ({Owner}) expired {ExpiryDate}"},
                   {"id": "expiring", "dataset": "register", "severity": "high", "title": "Expires within 30 days",
                    "when": {"all": [{"field": "days_left", "op": "gte", "value": 0}, {"field": "days_left", "op": "lte", "value": 30}]},
                    "message": "{Certificate} ({Owner}) expires in {days_left} days"},
                   {"id": "no_owner", "dataset": "register", "severity": "low", "title": "No owner", "when": {"field": "Owner", "op": "empty"},
                    "message": "{Certificate} has no owner"}],
         "kpis": [{"id": "items", "label": "Items in register", "dataset": "register"},
                  {"id": "expiring", "label": "Expired or < 30 days", "dataset": "register", "good": "down", "where": {"field": "days_left", "op": "lte", "value": 30}}],
         "tables": [{"title": "Next expiries", "dataset": "register", "columns": ["Certificate", "Owner", "ExpiryDate", "days_left"], "sort": "days_left", "limit": 30}],
         "charts": [{"title": "Items by days to expiry", "dataset": "register", "by": "days_left", "buckets": [0, 30, 90]},
                    {"title": "Items by owner", "dataset": "register", "by": "Owner"}],
         "labels": {"days_left": "Days left", "ExpiryDate": "Expiry date"},
         "keys": {"register": ["Certificate"]},
         "publish": {"sharepoint": {"site_url": "https://<tenant>.sharepoint.com/sites/<site>", "folder": "<folder for reports>"}},
         "history": "sharepoint", "schedule": "weekly"}},
    {"name": "cost-by-resource-group", "use": "Cost of the last N days per resource group with threshold alerts and week-over-week change.",
     "spec": {
         "name": "cost-by-resource-group", "title": "Cost by resource group", "language": "en",
         "description": "Show actual cost per resource group for the lookback window, flag the groups above budget and the change versus last report.",
         "sources": [{"id": "cost", "type": "cost_management", "scope": "/subscriptions/<subscription id>", "group_by": "ResourceGroupName"}],
         "rules": [{"id": "over_budget", "dataset": "cost", "severity": "high", "title": "Resource group above 1,000 in window",
                    "when": {"field": "Cost", "op": "gt", "value": 1000}, "message": "{ResourceGroupName}: {Cost} {Currency}"}],
         "kpis": [{"id": "total", "label": "Total cost", "dataset": "cost", "agg": "sum", "field": "Cost", "good": "down"},
                  {"id": "groups", "label": "Resource groups with cost", "dataset": "cost"}],
         "tables": [{"title": "Top resource groups", "dataset": "cost", "columns": ["ResourceGroupName", "Cost", "Currency"], "sort": "Cost", "desc": True, "limit": 25}],
         "charts": [{"title": "Cost by resource group", "dataset": "cost", "by": "ResourceGroupName", "agg": "sum", "field": "Cost", "limit": 10}],
         "keys": {"cost": ["ResourceGroupName"]}, "lookback_days": 30, "schedule": "weekly"}},
    {"name": "activity-deletes", "use": "Who deleted Azure resources in the window (audit).",
     "spec": {
         "name": "azure-delete-audit", "title": "Azure delete operations", "language": "en",
         "description": "List successful delete operations in the Azure Activity Log with caller and resource, to audit unexpected deletions.",
         "sources": [{"id": "deletes", "type": "log_analytics", "workspace_id": "<workspace customerId>",
                      "query": "AzureActivity\n| where TimeGenerated > ago({days}d)\n| where OperationNameValue endswith '/DELETE' and ActivityStatusValue == 'Success'\n"
                               "| project TimeGenerated, Caller, Operation = OperationNameValue, ResourceGroup, Resource = tostring(split(_ResourceId, '/')[-1]), "
                               "SubscriptionId, CorrelationId"}],
         "rules": [{"id": "rg_delete", "dataset": "deletes", "severity": "high", "title": "Resource group deleted",
                    "when": {"field": "Operation", "op": "contains", "value": "RESOURCEGROUPS/DELETE"}, "message": "{Caller} deleted {Resource} at {TimeGenerated}"},
                   {"id": "any_delete", "dataset": "deletes", "severity": "info", "title": "Resource deleted",
                    "when": {"not": {"field": "Operation", "op": "contains", "value": "RESOURCEGROUPS/DELETE"}}, "message": "{Caller} deleted {Resource} ({Operation})"}],
         "kpis": [{"id": "deletes", "label": "Delete operations", "dataset": "deletes"},
                  {"id": "callers", "label": "Distinct callers", "dataset": "deletes", "agg": "distinct", "field": "Caller"}],
         "tables": [{"title": "Deletes", "dataset": "deletes", "columns": ["TimeGenerated", "Caller", "Operation", "ResourceGroup", "Resource"], "sort": "TimeGenerated", "desc": True}],
         "charts": [{"title": "Deletes by caller", "dataset": "deletes", "by": "Caller"},
                    {"title": "Deletes by resource group", "dataset": "deletes", "by": "ResourceGroup"}],
         "keys": {"deletes": ["CorrelationId", "Resource"]}, "lookback_days": 7, "schedule": "daily"}},
]

SPEC_FIELDS = {
    "name": f"kebab-case use-case name, 3-{NAME_MAX} chars (tool = run-<name>, at most {TOOL_NAME_MAX} chars; skill and subagent = <name>)",
    "title": "report title shown in HTML and chat", "description": "one sentence: what it detects and why it matters (business value)",
    "language": "es | en (report language; the subagent answers in the user's language)", "client": "optional customer/team label",
    "audience": "optional: who reads the report", "accent": "legacy single colour; prefer brand.primary",
    "brand": "optional report identity {name, website, logo_url, primary, accent, dark, font: plex|nunito|fira, hero: auto|brand|dark|light}. "
             "Call operation=brand with the customer website first; scaffold embeds the official logo and colours. Without brand: Azure SRE Agent design",
    "charts": "optional list of {title, dataset, by, agg=count|sum|avg|max|min|distinct, field?, where?, limit=8, buckets?: [0,30,90], unit?} "
              "- bar charts grouped by a column (1-3 per report: by resource group, owner, OS, category, expiry window...)",
    "labels": "optional {column: display name} for table headers and finding chips (default: humanised column names)",
    "pdf": "auto (default; landscape when a table has more than 6 columns) | portrait | landscape | none - PDF printed from the HTML",
    "lookback_days": "default 7 (1-366)", "max_rows_per_source": "default 50000",
    "sources": "list of {id, type, ...type fields}; id = snake_case dataset name used by rules/kpis/tables",
    "derive": "optional list of {name, dataset, field, type: days_until|days_since} computed columns",
    "kpis": "list of {id, label, dataset, agg=count, field?, where?, good: up|down, unit?}",
    "rules": "list of {id, dataset, severity, title, when: condition, message: '{field} text', show: [fields]}",
    "tables": "optional list of {title, dataset, columns, sort, desc, limit=50, where}",
    "keys": "{dataset: [fields that identify one row]} - REQUIRED for stable comparison with the previous run",
    "publish": "optional {sharepoint: {site_url|site_id, folder}, blob: {account, container, prefix}}",
    "history": "none | sharepoint | blob (default = the publish target, so the next run compares with this one)",
    "schedule": "cron (5 fields, UTC) or preset: " + ", ".join(CRON_PRESETS),
    "condition": "{field, op, value} or {all: [...]} / {any: [...]} / {not: {...}}",
}


def _catalog():
    return {"kit_version": KIT_VERSION, "spec_fields": SPEC_FIELDS, "source_types": SOURCE_TYPES,
            "rule_operators": OPERATORS, "kpi_aggregations": AGGREGATIONS, "derive_types": ["days_until", "days_since"],
            "severities": SEVERITIES, "cron_presets": CRON_PRESETS,
            "message_placeholders": "Use {Column} in rule messages; dotted names like {passwordCredentials.endDateTime} work.",
            "query_placeholders": "{days}, {since_iso}, {now_iso}, {since_date} are replaced at run time.",
            "graph_least_privilege": {pattern: role for pattern, role in GRAPH_ROLES},
            "recipes": RECIPES,
            "workflow": ["environment (once per thread)", "write spec from the closest recipe", "probe if you are unsure of columns",
                         "scaffold (lint + self_test + live check + 4 blocks)", "fix errors and scaffold again (max 3)"]}


def _catalog_index():
    """Compact catalog that fits in one tool answer; details come from catalog + spec_json=<topic>."""
    return {
        "status": "OK", "kit_version": KIT_VERSION,
        "next": "Call catalog again with spec_json=<recipe name> to get its full spec (copy it and adapt). "
                "Other topics: spec (every field + condition syntax), operators, <source type> (notes), all.",
        "recipes": [{"name": r["name"], "source": r["spec"]["sources"][0]["type"], "use": r["use"]} for r in RECIPES],
        "source_types": {t: {"required": v["required"] + ([" | ".join(g) for g in v.get("one_of", [])]), "permission": v["permission"]}
                         for t, v in SOURCE_TYPES.items()},
        "spec_fields": list(SPEC_FIELDS),
        "rule_operators": list(OPERATORS), "kpi_aggregations": list(AGGREGATIONS), "derive_types": ["days_until", "days_since"],
        "severities": SEVERITIES, "schedule_presets": list(CRON_PRESETS),
        "workflow": ["catalog", "catalog <recipe>", "environment", "brand <website> (when a customer is named)", "write spec", "probe (optional)", "scaffold", "get <name>/<part>"],
    }


def _catalog_detail(topic):
    topic = (topic or "").strip().strip('"').lower()
    recipe = next((r for r in RECIPES if r["name"] == topic or r["spec"]["name"] == topic), None)
    if recipe:
        types = {s["type"] for s in recipe["spec"]["sources"]}
        return {"status": "OK", "recipe": recipe["name"], "use": recipe["use"], "spec": recipe["spec"],
                "source_notes": {t: SOURCE_TYPES[t]["notes"] for t in types},
                "next": "Copy spec, replace <placeholders> with values from environment, adapt rules/kpis, then scaffold."}
    if topic in SOURCE_TYPES:
        out = dict(SOURCE_TYPES[topic], status="OK", source_type=topic)
        if topic == "graph":
            out["graph_least_privilege"] = {pattern: role for pattern, role in GRAPH_ROLES}
        return out
    if topic == "spec":
        return {"status": "OK", "spec_fields": SPEC_FIELDS,
                "message_placeholders": "Use {Column} in rule messages; dotted names like {passwordCredentials.endDateTime} work.",
                "query_placeholders": "{days}, {since_iso}, {now_iso}, {since_date} are replaced at run time."}
    if topic in ("operators", "rule_operators"):
        return {"status": "OK", "rule_operators": OPERATORS, "no_value_operators": sorted(NO_VALUE_OPS), "kpi_aggregations": AGGREGATIONS,
                "cron_presets": CRON_PRESETS, "severities": SEVERITIES}
    if topic == "all":
        try:
            folder = Path.cwd() / "sre-usecase-builder"
            folder.mkdir(parents=True, exist_ok=True)
            path = folder / "catalog-full.json"
            path.write_text(json.dumps(_catalog(), ensure_ascii=False, indent=1), encoding="utf-8")
            link = _thread_link(path)
        except OSError:
            link = None
        return {"status": "OK", "full_catalog": link,
                "message": "The full catalog is saved to full_catalog. Prefer catalog with a single topic; each fits in one answer.",
                "topics": [r["name"] for r in RECIPES] + list(SOURCE_TYPES) + ["spec", "operators"]}
    return {"status": "INVALID", "message": f"Unknown catalog topic '{topic}'.",
            "topics": [r["name"] for r in RECIPES] + list(SOURCE_TYPES) + ["spec", "operators", "all"]}
