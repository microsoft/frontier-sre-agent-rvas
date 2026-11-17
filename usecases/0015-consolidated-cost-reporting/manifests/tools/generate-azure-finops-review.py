# generate-azure-finops-review
# Python tool for Azure SRE Agent: classic monthly FinOps review of the whole Azure environment.
# Sources (all read-only): Cost Management Query API (3 queries per subscription, plus 1 for the project tag),
# Consumption budgets and tag keys, Azure Resource Graph (resource groups and tags, idle and orphaned resources,
# Azure Advisor cost recommendations). Cost is also shown per project, from a project tag it detects or you set.
# READ ONLY. The SRE Agent managed identity needs Reader on the configured subscriptions (or management group);
# Reader includes cost and budget reads at subscription scope (Cost Management Reader is the cost-only alternative).
# It never creates, modifies or deletes anything, and adds no Azure cost (no exports, storage or Log Analytics).
# BEFORE PASTING IT into the Builder, replace <YOUR_MANAGED_IDENTITY_CLIENT_ID> and <YOUR_SUBSCRIPTION_ID> in the
# CONFIGURE block. A Client ID or a Subscription ID is not a secret. operation=self_test needs no configuration.
# Version 1.1 - November 2026

import base64
import calendar
import csv
import hashlib
import html
import io
import json
import math
import os
import re
import ssl
import tempfile
import time
import unicodedata
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, unquote, urlsplit
from urllib.request import HTTPRedirectHandler, HTTPSHandler, Request, build_opener
from uuid import UUID, uuid4

# ============================== CONFIGURE ==============================
MANAGED_IDENTITY_CLIENT_ID = "<YOUR_MANAGED_IDENTITY_CLIENT_ID>"
SUBSCRIPTION_IDS = ["<YOUR_SUBSCRIPTION_ID>"]        # or leave empty and set MANAGEMENT_GROUP_ID
MANAGEMENT_GROUP_ID = ""                              # every subscription under it (up to MAX_SUBSCRIPTIONS)
CLIENT_NAME = ""                                      # optional organization name shown in the report header
COST_METRIC = "AmortizedCost"                         # AmortizedCost (reservations spread over usage) or ActualCost (invoice view)
TREND_MONTHS = 6                                      # full months in the monthly trend, plus the month to date
ALLOCATION_TAGS = ["costcenter", "owner", "environment"]  # tags every cost should carry (case-insensitive), up to 5
TAG_INHERITANCE = True                                # a resource group or subscription tag also counts for its resources
PROJECT_TAG_KEYS = []                                 # tag key(s) that name the project, in priority order; empty = detect it
PROJECT_RG_RULES = []                                 # optional ("regex on the resource group name", "Project") pairs for untagged groups
ANOMALY_MIN_DAILY_DELTA = 20.0                        # minimum daily increase (billing currency) before a day is unusual
MOM_MIN_DELTA = 100.0                                 # minimum month-over-month increase for a service or resource group jump
SNAPSHOT_MAX_AGE_DAYS = 90                            # disk snapshots older than this are listed for review
EXCLUDED_RESOURCE_GROUPS = []                         # regexes; idle-resource and Advisor findings in them are not listed
LOGO_DATA_URI = ""                                    # optional data:image/svg+xml;base64,... logo for the report header
MAX_SUBSCRIPTIONS = 25
MAX_COLLECTION_SECONDS = 420
OUTPUT_DIRECTORY = "finops-review-reports"            # fixed child folder of the working directory
FILE_PREFIX = "finops-review"                         # report file names: <prefix>-<month>-<timestamp>-<id>
# =======================================================================

TOOL_NAME = "generate-azure-finops-review"
TOOL_VERSION = "1.1"
ARM = "https://management.azure.com"
ARG_API_VERSION = "2024-04-01"
COST_API_VERSION = "2025-03-01"
BUDGET_API_VERSION = "2023-05-01"
SIDECAR_TOKEN_ISSUER = "adc-msi-sidecar"
TRANSPORT_BYTES = 3500
ARTIFACT_BYTES = 4_800_000
HTTP_BYTES = 16_000_000
MAX_HTTP_REQUESTS = 300
MAX_ARG_PAGES = 60
MAX_COST_PAGES = 20
MAX_COST_ROWS = 100_000
MAX_RETRY_WAIT = 65
DATA_LATENCY_DAYS = 2
DAILY_DAYS = 60
BASELINE_DAYS = 14
ANOMALY_DAY_PCT = 25
MOM_MIN_PCT = 20
OPERATIONS = ("report", "query", "self_test")
VIEWS = ("summary", "actions", "anomalies", "budgets", "savings", "resources", "projects", "allocation", "coverage")
PROJECT_VARIANTS = 25
SEV_RANK = {"critical": 5, "high": 4, "medium": 3, "low": 2, "info": 1}
SEVERITIES = ("critical", "high", "medium", "low", "info")
SEP, EMDASH, TIMES = " \u00b7 ", "\u2014", " \u00d7"
GUID_RX = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
PLACEHOLDER_RX = re.compile(r"^\s*<[^>]*>\s*$")
TAG_RX = re.compile(r"^[A-Za-z0-9 _.:/\-]{1,64}$")
PROJECT_KEY_RX = re.compile(r"^(?=.*\S)[^<>%&\\?/,\x00-\x1f\x7f]{1,128}$")
PROJECT_NAME_RX = re.compile(r"^(?=.*\S)[^<>\x00-\x1f\x7f]{1,64}$")
# tag names that usually identify a project (EN/ES/CA), by strength; matched without accents, case or separators
PROJECT_WORDS = ((3, ("project", "proyecto", "projecte")),
                 (2, ("application", "aplicacion", "aplicacio", "app", "workload", "service", "servicio", "servei", "product", "producto", "producte")),
                 (1, ("costcenter", "centrocoste", "centrocostes", "centrodecoste", "centrodecostes", "centredecost", "ceco", "cc", "businessunit",
                      "unidaddenegocio", "bu", "department", "departamento", "departament", "team", "equipo", "equip")))
PROJECT_SOURCES = ("resource", "rg", "managed", "sub", "cost", "rule", "none")
LOGO_RX = re.compile(r"^data:image/(svg\+xml|png|jpeg|webp);base64,[A-Za-z0-9+/=]+$")
COMMITMENT_SERVICES = frozenset({"virtual machines", "azure app service", "sql database", "sql managed instance",
                                 "azure kubernetes service", "azure cosmos db", "azure database for postgresql",
                                 "azure database for mysql", "azure synapse analytics", "azure dedicated host",
                                 "container instances", "azure container apps", "azure functions", "redis cache",
                                 "azure databricks", "azure cache for redis", "app service", "azure vmware solution"})
LEARN_TITLES = {
    "https://learn.microsoft.com/rest/api/cost-management/query/usage": "Cost Management Query API",
    "https://learn.microsoft.com/azure/cost-management-billing/costs/manage-automation": "Cost Management automation and rate limits",
    "https://learn.microsoft.com/rest/api/consumption/budgets/list": "Consumption Budgets API",
    "https://learn.microsoft.com/azure/advisor/advisor-cost-recommendations": "Azure Advisor cost recommendations",
    "https://learn.microsoft.com/azure/governance/resource-graph/overview": "Azure Resource Graph",
    "https://learn.microsoft.com/azure/cost-management-billing/costs/enable-tag-inheritance": "Tag inheritance in Cost Management",
    "https://learn.microsoft.com/azure/azure-resource-manager/management/tag-resources": "Tags to organize Azure resources",
    "https://learn.microsoft.com/azure/sre-agent/overview": "Azure SRE Agent",
}
LEARN_SOURCES = [
    "https://learn.microsoft.com/rest/api/cost-management/query/usage",
    "https://learn.microsoft.com/azure/cost-management-billing/costs/manage-automation",
    "https://learn.microsoft.com/rest/api/consumption/budgets/list",
    "https://learn.microsoft.com/azure/advisor/advisor-cost-recommendations",
    "https://learn.microsoft.com/azure/governance/resource-graph/overview",
    "https://learn.microsoft.com/azure/cost-management-billing/costs/enable-tag-inheritance",
    "https://learn.microsoft.com/azure/azure-resource-manager/management/tag-resources",
    "https://learn.microsoft.com/azure/sre-agent/overview",
]
LEARN_TAG_INHERITANCE = "https://learn.microsoft.com/azure/cost-management-billing/costs/enable-tag-inheritance"

# ------------------------- report copy (one table, so the report can be translated) -------------------------
# @@TEXT-BEGIN@@
TEXT = {
    "_lang": "en", "_dec": ".", "_grp": ",", "_pct": "{v}%",
    "_months": ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"],
    "_mon": ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
    "_wd": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
    "_day_fmt": "{d} {mon} {y}", "_dayshort_fmt": "{d} {mon}", "_month_fmt": "{month} {y}",
    "product": "Azure SRE Agent", "doc_title": "Azure FinOps review", "read_only": "Read-only", "print": "Print / PDF",
    "skip": "Skip to content", "sections": "Sections", "internal": "Internal use",
    "h1": "Azure FinOps review: {month}", "h1_short": "FinOps review {month}",
    "metric_AmortizedCost": "Amortized cost", "metric_ActualCost": "Actual cost",
    "metric_note_AmortizedCost": "Reservations and savings plans are spread over the days they cover.",
    "metric_note_ActualCost": "Costs as invoiced: reservation purchases appear on the day they are bought.",
    "live": "Live data \u00b7 complete coverage", "live_partial": "Live data \u00b7 partial coverage", "simulated": "SIMULATED data (self-test)", "generated": "Generated {v} UTC",
    "chip_scope": "{n} subscriptions", "chip_scope_one": "1 subscription", "chip_mg": "Management group {v}",
    "chip_window": "{a} \u2192 {b}", "chip_partial": "Partial coverage", "chip_complete": "Complete coverage",
    "lead_month": "{month} cost <b>{cost}</b>, {change} {prev}.",
    "lead_change_up": "up <b>{pct}</b> on", "lead_change_down": "down <b>{pct}</b> on", "lead_change_flat": "flat on",
    "lead_change_none": "with no cost recorded in",
    "lead_forecast_budget": " {month} is heading for <b>{f}</b>, {pct} of the budget.",
    "lead_forecast_nobudget": " {month} is heading for <b>{f}</b> (no budget set).", "lead_forecast_partial": " {month} is heading for <b>{f}</b>; {n} of {k} budgets are forecast to overrun.", "lead_forecast_partial_one": " {month} is heading for <b>{f}</b>; 1 of {k} budgets is forecast to overrun.",
    "lead_savings": " <b>{n}</b> savings opportunities add up to about <b>{s}</b> a month.", "lead_savings_one": " <b>1</b> savings opportunity is worth about <b>{s}</b> a month.",
    "lead_savings_none": " No direct savings were found this month.",
    "lead_nodata": "Cost data could not be read for any subscription, so totals are not shown. See Coverage.",
    "verdict": "Verdict", "v_action": "Action required", "v_review": "Review recommended", "v_ok": "On track", "v_nodata": "Incomplete data",
    "vd_budgets": "{n} budgets forecast over", "vd_budgets_one": "1 budget forecast over", "vd_nobudget": "{n} subscriptions without a budget", "vd_nobudget_one": "1 subscription without a budget", "vd_savings": "{v}/month to recover", "vd_anom": "{n} anomalies", "vd_anom_one": "1 anomaly", "vd_untagged": "{v} of the cost untagged", "v_nothing": "No findings above low severity.",
    "v_partial": "Partial coverage: {v}", "v_nodata_detail": "No cost data could be read. Check the identity's Reader role.",
    "dist": "Findings by severity", "sev_critical": "Critical", "sev_high": "High", "sev_medium": "Medium", "sev_low": "Low", "sev_info": "Info",
    "kpi_month": "{month} cost", "kpi_month_sub": "{delta} vs {prev}", "kpi_month_sub_none": "no cost recorded in {prev}",
    "kpi_mtd": "Month to date", "kpi_mtd_sub": "through {d} \u00b7 {delta} vs same days of {prev}", "kpi_mtd_sub_nodelta": "through {d}",
    "kpi_forecast": "{month} forecast", "kpi_forecast_budget": "{pct} of the {b} budget", "kpi_forecast_nobudget": "run-rate \u00b7 no budget set", "kpi_forecast_partial": "{n} of {k} budgets forecast over", "kpi_forecast_partial_one": "1 of {k} budgets forecast over",
    "kpi_savings": "Savings identified", "kpi_savings_sub": "a month \u00b7 {n} opportunities", "kpi_savings_sub_one": "a month \u00b7 1 opportunity", "kpi_savings_unit": "/month",
    "kpi_alloc": "Cost without {tag}", "kpi_alloc_all": "Cost not fully tagged", "kpi_alloc_sub": "{v} of {total} in {month}",
    "kpi_alloc_none": "no allocation tags configured",
    "kpi_anom": "Anomalies", "anom_days": "{n} unusual days", "anom_days_one": "1 unusual day", "anom_jumps": "{n} jumps", "anom_jumps_one": "1 jump", "anom_new": "{n} new", "anom_new_one": "1 new",
    "nav_actions": "Actions", "nav_trend": "Trend", "nav_breakdown": "Where it goes", "nav_changes": "What changed",
    "nav_budgets": "Budgets", "nav_savings": "Savings", "nav_allocation": "Allocation", "nav_register": "Register", "nav_coverage": "Coverage",
    "s_actions": "What to do this month", "s_actions_sub": "The prioritised list for the cost owner: biggest savings and risks first. The agent never applies them; a person decides and acts.",
    "s_trend": "Trend", "s_trend_sub": "Monthly cost over the last {n} full months plus this month, and the daily cost of the last {d} days with unusual days marked.",
    "s_breakdown": "Where the money goes", "s_breakdown_sub": "{month} cost by subscription, resource group, service, region and resource, with the change on {prev}.",
    "s_changes": "What changed", "s_changes_sub": "Unusual days, month-over-month jumps and new services, found with simple statistics you can explain to finance.",
    "s_budgets": "Budgets and forecast", "s_budgets_sub": "Every budget on the reviewed scopes with what is spent and what Azure forecasts, and the subscriptions with no budget.",
    "s_savings": "Savings", "s_savings_sub": "Azure Advisor cost recommendations, idle and orphaned resources, and how much compute runs on commitments. Estimates are per month.",
    "s_allocation": "Allocation readiness", "s_allocation_sub": "How much of {month}'s cost carries the tags used to charge it back: {tags}.",
    "s_register": "Findings register", "s_register_sub": "Every finding of this review in one list. Search, filter, sort and export the rows you need.",
    "s_coverage": "Coverage, sources and method", "s_coverage_sub": "What was read, how completely, and how each number is calculated.",
    "act_saving": "Est. saving", "act_where": "Where", "act_none": "Nothing to do this month: no findings above low severity.",
    "per_month": "{v}/month", "no_saving": "\u2014",
    "monthly_h": "Monthly cost", "monthly_sub": "Full months plus {month} to date; the outlined bar is the forecast for the whole month.",
    "mtd_label": "to date", "fc_label": "forecast", "no_cost": "no cost",
    "daily_h": "Daily cost, last {n} days", "daily_sub": "Unusual days are coloured. The line is the typical day (median of the previous {b} days). The last {l} days are still being completed by Cost Management.",
    "daily_typical": "Typical day", "daily_unusual": "Unusual day", "daily_partial": "Still settling", "daily_before": "Before {month}",
    "by_sub": "By subscription", "by_rg": "By resource group", "by_rg_sub": "Top {n} of {t} resource groups.",
    "by_service": "By service", "by_service_sub": "Top {n} of {t} services.", "by_region": "By region", "top_res": "Top resources",
    "top_res_sub": "The {n} most expensive resources in {month}, with the change on {prev}.",
    "others": "Other {n}", "col_resource": "Resource", "col_type": "Type", "col_region": "Region", "col_cost": "{month}", "col_prev": "{month}",
    "col_change": "Change", "col_share": "Share", "new_badge": "new", "gone_badge": "stopped", "open_portal": "Open in the Azure portal", "open_short": "Open", "new_tab": "opens in a new tab", "scope_all": "Whole scope", "disks_only": "disks only",
    "no_rg": "(no resource group)", "sub_level": "(subscription level)", "unknown_region": "Unassigned",
    "unusual_days": "Unusual days", "unusual_days_sub": "Days more than {pct} above the typical day and at least {min} higher, also compared with the same weekday a week before.",
    "ud_typical": "typical {v}", "ud_driver": "Driven by {v}", "ud_driver_l": "driven by {v}", "ud_none": "No unusual days in {month} or this month so far.",
    "jumps": "Month-over-month jumps", "jumps_sub": "Services and resource groups that grew at least {pct} and {min} from {prev} to {month}.",
    "jumps_none": "No service or resource group grew beyond the thresholds.",
    "new_services": "New this month", "new_services_sub": "Services and resource groups with cost in {month} and none in the three months before.",
    "new_none": "Nothing new compared with the three months before.", "kind_service": "Service", "kind_rg": "Resource group", "kind_sub": "Subscription",
    "pace_h": "Month-to-date pace", "pace_txt": "The first {k} days of {month} cost {a}, {delta} compared with the first {k} days of {prev} ({b}).",
    "budget_name": "Budget", "budget_scope": "Scope", "budget_amount": "Amount", "budget_spent": "Spent", "budget_forecast": "Azure forecast",
    "budget_status": "Status", "budget_alerts": "Alerts", "budget_grain": "{v}", "budget_none": "No budgets are defined on the reviewed scopes.",
    "bs_over": "Over budget", "bs_forecast_over": "Forecast over", "bs_risk": "At risk", "bs_ok": "On track",
    "nobudget_h": "Subscriptions with no budget", "nobudget_sub": "A forecast overrun would go unnoticed. A suggested amount is 110% of this month's forecast, rounded up.",
    "nobudget_none": "Every reviewed subscription has a subscription-level budget.", "nobudget_suggest": "Suggested monthly budget",
    "alerts_actual": "actual {v}", "alerts_forecast": "forecast {v}", "alerts_none": "no alerts",
    "sv_total": "Estimated savings", "sv_total_sub": "a month, without double counting: commitments count once, the best option per resource.",
    "sv_commit": "Commitments", "sv_rightsize": "Advisor recommendations", "sv_idle": "Idle and orphaned resources",
    "commit_h": "Commitment coverage", "commit_txt": "{pct} of {month}'s commitment-eligible compute ({elig}) ran on reservations or savings plans.",
    "commit_none": "No commitment-eligible compute cost in {month}.",
    "commit_util": "Reservation and savings plan utilization: not evaluated. It needs Reservations Reader and Savings plan Reader at tenant level; the cost split above only needs Reader.",
    "commit_best": "Advisor's best commitment option: {v} a month ({t}).", "commit_alt": "Alternatives, not additive: {v}.",
    "pm_OnDemand": "On demand", "pm_Reservation": "Reservations", "pm_SavingsPlan": "Savings plans", "pm_Spot": "Spot",
    "advisor_h": "Azure Advisor cost recommendations", "advisor_sub": "{n} recommendations. Advisor's monthly estimate, or the resource's cost last month when Advisor gives none.", "advisor_sub_one": "1 recommendation. Advisor's monthly estimate, or the resource's cost last month when Advisor gives none.", "also_advisor": "Advisor agrees", "advisor_link": "Azure Advisor", "commit_opts": "Advisor's commitment options",
    "advisor_none": "Azure Advisor has no cost recommendations for these subscriptions.",
    "idle_h": "Idle and orphaned resources", "idle_sub": "Found in Azure Resource Graph. The saving is what the resource cost in {month}.",
    "idle_none": "No idle or orphaned resources were found.", "col_check": "Check", "col_detail": "Detail", "col_saving": "Saving",
    "chk_unattached_disk": "Unattached disk", "chk_unused_public_ip": "Unassociated public IP", "chk_stopped_vm": "VM stopped, not deallocated",
    "chk_deallocated_vm": "Deallocated VM", "chk_empty_plan": "Empty App Service plan", "chk_orphaned_nic": "Orphaned network interface",
    "chk_old_snapshot": "Old disk snapshot", "chk_idle_load_balancer": "Load balancer without backends", "chk_idle_nat_gateway": "NAT gateway without subnets",
    "alloc_tag": "Coverage by tag", "alloc_tag_sub": "Share of {month}'s cost ({total}) that carries each tag.", "alloc_untagged": "Untagged cost", "alloc_all": "All {n} tags",
    "alloc_rg_h": "Resource groups with the most untagged cost", "alloc_rg_sub": "Cost in {month} on resources missing at least one required tag.",
    "alloc_rg_none": "Every resource group's cost carries the required tags.",
    "alloc_inherit_on": "Resource group and subscription tags count for the resources inside (TAG_INHERITANCE = True).",
    "alloc_inherit_off": "Only tags on the resource itself count (TAG_INHERITANCE = False).",
    "alloc_notres": "{v} of cost is not linked to a resource (purchases, Marketplace or support) or the resource no longer exists; it is counted as untagged.",
    "alloc_none": "No allocation tags are configured (ALLOCATION_TAGS is empty).",
    "reg_search": "Search findings", "reg_all_sev": "All severities", "reg_all_cat": "All categories", "reg_clear": "Clear",
    "reg_export": "Export CSV", "reg_count": "{v} shown of {t} findings", "reg_count_f": "{v} shown of {m} matching ({t} in total)", "reg_none": "No findings match these filters.", "reg_more": "Show more", "show_more": "Show {n} more", "show_more_one": "Show 1 more",
    "col_sev": "Severity", "col_cat": "Category", "col_finding": "Finding", "col_scope": "Scope", "col_evidence": "Evidence",
    "cat_budget": "Budget", "cat_anomaly": "Anomaly", "cat_savings": "Savings", "cat_commitment": "Commitment", "cat_allocation": "Allocation",
    "cat_governance": "Governance", "cat_hygiene": "Hygiene", "cat_data": "Data quality",
    "cov_source": "Source", "cov_status": "Status", "cov_records": "Records", "cov_seconds": "Seconds", "cov_notes": "Notes",
    "st_complete": "Complete", "st_partial": "Partial", "st_denied": "Denied", "st_error": "Error", "st_skipped": "Skipped",
    "st_not_configured": "Not configured", "st_simulated": "Simulated",
    "src_containers": "Subscriptions and resource groups (Resource Graph)", "src_cost_monthly": "Monthly cost by resource group and service",
    "src_cost_daily": "Daily cost by service and pricing model", "src_cost_resources": "Cost by resource, service and region (3 months)",
    "src_budgets": "Budgets (Consumption API)", "src_tags": "Resource tags (Resource Graph)", "src_idle": "Idle and orphaned resources (Resource Graph)",
    "src_advisor": "Azure Advisor cost recommendations (Resource Graph)",
    "method_h": "Method", "method_items": [
        "{metric}: {metric_note} Currency: {currency}. Months are calendar months in UTC.",
        "Cost Management needs up to {lat} days to settle: the forecast and the unusual-day checks use days up to {through}.",
        "Forecast = cost of the month so far + the average of the last 7 settled days \u00d7 the days left. Budget status uses Azure's own budget forecast.",
        "Unusual day: more than {pct} above the median of the previous {b} days, at least {min} higher, and at least 20% above the same weekday a week before.",
        "Month-over-month jump: at least {mpct} and {mmin} more than the previous month. New: cost this month and none in the three months before.",
        "Savings are monthly estimates and are not added twice: reservations and savings plans are alternatives, so only the best option counts, and each resource counts once.",
        "Allocation: cost of {month} by resource, joined with the resource's tags in Azure Resource Graph today.",
        "Projects: each resource takes the first project found in its own tag, its resource group's tag (or the tag of the resource that manages the group), its subscription's tag, its cost records' tag and the resource group name rules; the rest is Unallocated. Today's tags apply to every month.",
    ],
    "notcov_h": "Not covered", "notcov_items": [
        "Reservation and savings plan utilization (needs tenant-level Reservations Reader and Savings plan Reader).",
        "Marketplace invoices outside Azure Cost Management, and credits or refunds applied at billing-account level.",
        "Usage inside resources (for example idle databases or oversized clusters) beyond what Azure Advisor reports.",
    ],
    "throttle_note": "Cost Management limited the request rate {n} times; the tool waited and retried ({s} s in total).",
    "learn_h": "Microsoft Learn", "footer": "Generated by Azure SRE Agent \u00b7 {tool} {ver} \u00b7 read-only \u00b7 {gen}",
    "csv_findings": "findings", "csv_costs": "cost-by-resource", "file_snapshot": "snapshot",
    # finding titles and actions (also used in the CSV and the agent answer)
    "f_budget_over": "Over budget: {name}", "f_budget_forecast": "Forecast over budget: {name}",
    "f_budget_risk": "Budget at {pct} already: {name}", "f_budget_risk_fc": "Close to the budget at month end: {name}",
    "f_budget_ev": "{spent} spent and {fc} forecast against {amount} ({grain}).",
    "a_budget": "Review the drivers in What changed and agree a correction or a new amount with the budget owner.",
    "f_nobudget": "No budget on subscription {name}", "f_nobudget_ev": "This month's forecast is {fc}.",
    "a_nobudget": "Create a monthly budget of about {amount} with alerts at 80% and 100% actual and 100% forecast.",
    "f_day": "Unusual cost on {d}", "f_day_ev": "{cost} against a typical {typ} ({pct}), {drivers}.",
    "a_day": "Check what started on that day for {driver} (deployments, scale-out, data transfer) and confirm it is expected.",
    "f_jump": "{kind} {name} grew {pct} month over month", "f_jump_ev": "{prev} in {pm} \u2192 {cost} in {m} ({delta}).",
    "a_jump": "Confirm the growth is planned with the owner of {name}; if not, find the resources behind it in Top resources.",
    "f_new": "New {kind_l}: {name}", "f_new_ev": "{cost} in {m}, nothing in the three months before.",
    "a_new": "Confirm {name} is a planned new workload and has an owner and a budget.",
    "f_idle": "{check}: {name}", "a_idle_unattached_disk": "Snapshot it if the data matters, then delete the disk.",
    "a_idle_unused_public_ip": "Delete the public IP or attach it to the workload that needs it.",
    "a_idle_stopped_vm": "Deallocate the VM (Stop in the portal) or delete it: a VM stopped from the OS still pays for compute.",
    "a_idle_deallocated_vm": "Confirm it is still needed; if not, delete the VM and its disks. Its disks keep billing while it is deallocated.",
    "a_idle_empty_plan": "Delete the empty plan or scale it to the Free tier.", "a_idle_orphaned_nic": "Delete the unused network interface (no cost, less clutter).",
    "a_idle_old_snapshot": "Delete snapshots that are no longer part of a backup or recovery plan.",
    "a_idle_idle_load_balancer": "Delete the load balancer or add the backends it should serve.",
    "a_idle_idle_nat_gateway": "Delete the NAT gateway or associate it with the subnets that need outbound access.",
    "f_advisor": "Advisor: {problem} ({name})", "a_advisor": "Review it in Azure Advisor and apply it if it fits the workload.",
    "f_commit": "Compute runs on demand: {pct} covered by commitments", "f_commit_ev": "{od} of on-demand commitment-eligible compute in {m}. {best}",
    "a_commit": "Review Advisor's reservation and savings plan options with finance before buying; choose one of them, not both.",
    "f_alloc": "{pct} of the cost has no {tag} tag", "f_alloc_multi": "{pct} of the cost misses at least one allocation tag ({tags})",
    "f_alloc_ev": "{v} of {total} in {m}.", "top_services": "the services that grew", "term_1y": "1 year", "term_3y": "3 years",
    "per_month_unit": "/month",
    "a_alloc": "Tag the resource groups listed under Allocation readiness, starting with {rg}, or enable tag inheritance in Cost Management.",
    "f_cov": "Data incomplete: {v}", "a_cov": "Grant Reader on the scope (or wait for throttling to clear) and run the review again.",
    "ev_monthly": "{v} a month",
    "grain_Monthly": "Monthly", "grain_Quarterly": "Quarterly", "grain_Annually": "Annually", "grain_BillingMonth": "Billing month",
    "grain_BillingQuarter": "Billing quarter", "grain_BillingAnnual": "Billing year",
    "advisor_impact": "Advisor impact {v}", "impact_v": "Impact {v}", "advisor_est": "Advisor: {v}", "imp_High": "High", "imp_Medium": "Medium", "imp_Low": "Low",
    "k8s_volume": "Kubernetes volume", "col_action": "Action", "col_resource_id": "Resource ID", "col_link": "Link", "filtered": "filtered",
    "tbl": "Table", "scrolls": "(scrolls sideways)",
    # projects
    "nav_projects": "Projects", "s_projects": "Cost by project",
    "s_projects_sub": "{month} cost per project with the change on {prev}, this month so far, savings and findings. {pct} of the cost is allocated to a project.",
    "pf_label": "Project", "pf_all": "All projects", "pf_clear": "Show all projects", "pf_note": "Whole environment: not filtered by project",
    "pf_chip": "Project:", "pf_banner": "Showing project {name}: {cost} in {month} ({share} of the cost) and {n} findings.",
    "pf_banner_one": "Showing project {name}: {cost} in {month} ({share} of the cost) and 1 finding.",
    "pf_scope": "Actions, Where the money goes, Savings and the Findings register show this project. The figures at the top and the sections marked Whole environment are not filtered.",
    "col_project": "Project", "col_mtd": "{month} to date", "col_psavings": "Savings a month", "col_findings": "Findings",
    "proj_unallocated": "Unallocated", "proj_unalloc_sub": "No project tag or rule matches these resources.",
    "proj_res": "{n} resources", "proj_res_one": "1 resource", "proj_rgs": "{n} resource groups", "proj_rgs_one": "1 resource group", "proj_top": "top: {v}",
    "proj_total": "All projects", "proj_more": "Other {n} projects", "proj_pick": "Filter the report by project {name}",
    "proj_none": "No cost could be linked to resources in {month}, so there is nothing to show per project.",
    "sv_total_sub_p": "a month for this project: Advisor recommendations and idle resources, each resource counted once.",
    "advisor_none_p": "Azure Advisor has no cost recommendations for this project's resources.", "idle_none_p": "No idle or orphaned resources were found in this project.",
    "proj_share_h": "Share of {month}'s cost", "proj_share_sub": "Choose a project in the table or in the Project menu to filter the report.",
    "pd_change": "vs {prev}", "pd_mtd": "{month} to date", "pd_savings": "savings a month", "pd_services": "Top services", "pd_rgs": "Top resource groups",
    "pd_resources": "Top resources", "pd_findings": "{n} findings", "pd_findings_one": "1 finding", "act_none_p": "No actions for this project this month.",
    "pid_h": "How projects are identified", "pid_tag": "Project tag", "pid_chip_detected": "Detected automatically", "pid_chip_configured": "Set in PROJECT_TAG_KEYS",
    "pid_chip_parameter": "Set for this run (project_tag)", "pid_chip_none": "No project tag found",
    "pid_why_detected": "Chosen because its name means {meaning}, it covers {cov} of {month}'s cost and it has {n} values.",
    "pid_why_detected_cost": "Chosen because its name means {meaning}; it was found only in the cost records.",
    "pid_why_configured": "Set in the CONFIGURE block of the tool. Tags cover {cov} of {month}'s cost.",
    "pid_why_parameter": "Requested for this run. Tags cover {cov} of {month}'s cost.",
    "pid_why_none": "No tag name in the reviewed scope looks like a project, application, cost center or team.",
    "meaning_3": "project", "meaning_2": "application, workload, service or product", "meaning_1": "cost center, business unit, department or team",
    "pid_order": "Each resource takes the first match, in this order (share of {month}'s cost):",
    "pid_lvl_resource": "Tag on the resource", "pid_lvl_rg": "Tag on its resource group", "pid_lvl_managed": "Tag on the resource that manages its group (AKS, Databricks)",
    "pid_lvl_sub": "Tag on its subscription", "pid_lvl_cost": "Tag on its cost records", "pid_lvl_rule": "Resource group name rules (PROJECT_RG_RULES)",
    "pid_lvl_none": "Unallocated", "pid_cost_off": "not read", "pid_no_rules": "none set",
    "pid_past": "Today's tags are applied to every month, so earlier months are allocated the same way.",
    "pid_cand": "Tags that could name the project", "pid_cand_sub": "Found in this review, best match first.",
    "col_tag": "Tag", "col_found": "Found on", "col_coverage": "Covers", "col_values": "Values", "pid_in_use": "in use", "not_measured": "not measured",
    "where_resource": "resources", "where_rg": "resource groups", "where_sub": "subscriptions", "where_cost": "cost records",
    "pid_override": "To confirm or change it, set PROJECT_TAG_KEYS = [\"{tag}\"] in the tool, or ask the agent to use another tag for one run (project_tag). "
                    "PROJECT_RG_RULES maps resource group names to projects where there is no tag.",
    "pid_override_none": "Set PROJECT_TAG_KEYS to the tag that names your projects, or map resource group names to projects with PROJECT_RG_RULES.",
    "pid_inherit": "For chargeback in Azure itself, enable tag inheritance in Cost Management so cost records carry the tags of their resource group and subscription.",
    "rule_arrow": "{p} \u2192 {v}",
    "f_proj_none": "No project tag found", "f_proj_none_ev": "No tag name in the reviewed scope looks like a project, application, cost center or team; {pct} of {m}'s cost has no project.",
    "a_proj_none": "Agree a project tag with the teams (for example Project), set it on the resource groups and add it to PROJECT_TAG_KEYS; PROJECT_RG_RULES can map resource group names meanwhile.",
    "f_proj_low": "Only {pct} of the cost is allocated to a project ({tag} tag)", "f_proj_low_ev": "{v} of {total} in {m} has no project, mostly in {rgs}.",
    "a_proj_low": "Tag those resource groups with {tag} (or add PROJECT_RG_RULES) and enable tag inheritance in Cost Management so cost records carry it.",
    "src_cost_tag_keys": "Tag keys in cost records (Consumption API)", "src_cost_project": "Cost by resource and project tag (cost records)",
    "optional": "optional", "csv_projects": "cost-by-project",
    "cov_skipped": "{n} subscriptions not read (MAX_SUBSCRIPTIONS).", "cov_other_cur": "Excluded from totals (other billing currency): {v}",
    "cov_invisible": "Not visible to the identity (no Reader): {v}", "cov_stats": "{n} read-only requests \u00b7 {s} s", "cov_identity": "identity: {v}",
    "id_verified": "verified token", "id_unmatched": "token not matched to the configured identity (continuing)", "id_unreadable": "unreadable token (continuing)",
    "id_self_test": "self-test (no identity)", "f_skipped": "{n} subscriptions not read (MAX_SUBSCRIPTIONS = {max})",
    "_types": {"microsoft.compute/virtualmachines": "Virtual machine", "microsoft.compute/disks": "Managed disk",
        "microsoft.compute/snapshots": "Disk snapshot", "microsoft.network/publicipaddresses": "Public IP address",
        "microsoft.network/azurefirewalls": "Azure Firewall", "microsoft.network/bastionhosts": "Bastion",
        "microsoft.network/applicationgateways": "Application gateway", "microsoft.network/loadbalancers": "Load balancer",
        "microsoft.network/natgateways": "NAT gateway", "microsoft.network/networkinterfaces": "Network interface",
        "microsoft.network/virtualnetworkgateways": "VPN gateway", "microsoft.network/firewallpolicies": "Firewall policy",
        "microsoft.web/serverfarms": "App Service plan", "microsoft.web/sites": "App Service", "microsoft.storage/storageaccounts": "Storage account",
        "microsoft.containerservice/managedclusters": "AKS cluster", "microsoft.containerregistry/registries": "Container registry",
        "microsoft.compute/virtualmachinescalesets": "VM scale set", "microsoft.operationalinsights/workspaces": "Log Analytics workspace",
        "microsoft.sql/servers/databases": "SQL database", "microsoft.sql/managedinstances": "SQL managed instance",
        "microsoft.cognitiveservices/accounts": "AI services account", "microsoft.app/containerapps": "Container app",
        "microsoft.dashboard/grafana": "Managed Grafana", "microsoft.recoveryservices/vaults": "Recovery Services vault",
        "microsoft.keyvault/vaults": "Key Vault", "microsoft.documentdb/databaseaccounts": "Cosmos DB account",
        "microsoft.hybridcompute/machines": "Arc-enabled server", "microsoft.security/pricings": "Defender plan",
        "microsoft.monitor/accounts": "Azure Monitor workspace", "microsoft.insights/components": "Application Insights",
        "microsoft.cdn/profiles": "Front Door / CDN profile", "microsoft.datafactory/factories": "Data factory",
        "microsoft.network/virtualnetworks": "Virtual network", "microsoft.network/privateendpoints": "Private endpoint"},
}
# @@TEXT-END@@


def t(key, **kw):
    value = TEXT.get(key, key)
    if isinstance(value, str) and kw:
        try:
            return value.format(**kw)
        except (KeyError, IndexError, ValueError):
            return value
    return value


def tn(key, n, **kw):
    """Plural-aware lookup: uses key + '_one' when n == 1 and that key exists."""
    return t(key + "_one" if n == 1 and key + "_one" in TEXT else key, n=n, **kw)


class FinOpsError(RuntimeError):
    def __init__(self, code, message, source="review", http_status=None):
        super().__init__(message)
        self.code = code
        self.source = source
        self.http_status = http_status

    def public(self):
        return {"code": self.code, "message": str(self), "source": self.source, "http_status": self.http_status}


# ------------------------- small helpers -------------------------
def utc_now():
    return datetime.now(timezone.utc).replace(microsecond=0)


def iso(dt):
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if dt else ""


def clean(value, limit=400):
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    text_value = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", str(value)).strip()
    return text_value if len(text_value) <= limit else text_value[:limit - 1] + "\u2026"


def is_guid(value):
    return isinstance(value, str) and bool(GUID_RX.match(value.strip()))


def num(value):
    try:
        out = float(value)
    except (TypeError, ValueError):
        return 0.0
    return out if math.isfinite(out) else 0.0


def r2(value):
    return round(num(value) + 0.0, 2)


def month_key(d):
    return f"{d.year:04d}-{d.month:02d}"


def add_months(d, n):
    y, m = divmod(d.year * 12 + (d.month - 1) + n, 12)
    return date(y, m + 1, 1)


def month_end(d):
    return date(d.year, d.month, calendar.monthrange(d.year, d.month)[1])


def parse_day(value):
    text_value = str(value or "").strip()
    match = re.match(r"^(\d{4})-?(\d{2})-?(\d{2})", text_value)
    if not match:
        return None
    try:
        return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
    except ValueError:
        return None


def median(values):
    vals = sorted(values)
    if not vals:
        return 0.0
    mid = len(vals) // 2
    return vals[mid] if len(vals) % 2 else (vals[mid - 1] + vals[mid]) / 2


def kql_text(value):
    if not isinstance(value, str) or re.search(r"['\"\\\r\n]", value):
        raise FinOpsError("unsafe_query_value", "Refused to embed an unsafe value in a Resource Graph query.", "query")
    return "'" + value + "'"


def split_id(resource_id):
    """(subscription, resource group, provider type, name) from an ARM ID, all lower case except the name."""
    parts = [p for p in (resource_id or "").split("/") if p]
    low = [p.lower() for p in parts]
    sub = parts[low.index("subscriptions") + 1].lower() if "subscriptions" in low and low.index("subscriptions") + 1 < len(parts) else ""
    rg = parts[low.index("resourcegroups") + 1] if "resourcegroups" in low and low.index("resourcegroups") + 1 < len(parts) else ""
    rtype, name = "", parts[-1] if parts else ""
    if "providers" in low:
        i = len(low) - 1 - low[::-1].index("providers")
        tail = parts[i + 1:]
        if tail:
            segs = [tail[0]] + [tail[k] for k in range(1, len(tail), 2)]
            rtype = "/".join(segs).lower()
            name = tail[-1] if len(tail) % 2 == 0 else tail[-1]
    return sub, rg, rtype, name


def portal_link(resource_id):
    return "https://portal.azure.com/#@/resource" + quote(resource_id or "", safe="/-_.()")


# ------------------------- configuration and parameters -------------------------
SELF_TEST_RULES = [(r"^rg-dev-(apps|build)", "Developer tools")]


def project_settings(strict=True):
    """PROJECT_TAG_KEYS and PROJECT_RG_RULES. strict=False (self_test) drops invalid entries instead of failing."""
    raw_keys = PROJECT_TAG_KEYS if isinstance(PROJECT_TAG_KEYS, (list, tuple)) else None
    valid = raw_keys is not None and len(raw_keys) <= 5 and all(isinstance(k, str) and PROJECT_KEY_RX.match(k.strip()) for k in raw_keys)
    if not valid and strict:
        raise FinOpsError("configuration_required", "PROJECT_TAG_KEYS must be a list of up to 5 tag names, or empty to detect the project tag.", "configuration")
    keys = []
    for k in raw_keys or []:
        if isinstance(k, str) and PROJECT_KEY_RX.match(k.strip()) and k.strip().casefold() not in [x.casefold() for x in keys]:
            keys.append(k.strip())
    raw_rules = PROJECT_RG_RULES if isinstance(PROJECT_RG_RULES, (list, tuple)) else None
    ok, rules = raw_rules is not None and len(raw_rules) <= 30, []
    for rule in raw_rules or []:
        good = (isinstance(rule, (list, tuple)) and len(rule) == 2 and all(isinstance(x, str) for x in rule) and 0 < len(rule[0]) <= 200
                and bool(PROJECT_NAME_RX.match(rule[1].strip())))
        try:
            rx = re.compile("(?i)" + rule[0]) if good else None
        except re.error:
            good = False
        if not good:
            ok = False
            continue
        rules.append((rx, rule[1].strip()))
    if not ok and strict:
        raise FinOpsError("configuration_required", "PROJECT_RG_RULES must be a list of up to 30 (\"regex\", \"project name\") pairs.", "configuration")
    return keys[:5], rules[:30]


def validate_config(self_test=False):
    if self_test:
        return {"client_id": "00000000-0000-0000-0000-000000000000", "subscriptions": [], "management_group": "",
                "client_name": CLIENT_NAME.strip() if isinstance(CLIENT_NAME, str) else "", "metric": COST_METRIC if COST_METRIC in ("AmortizedCost", "ActualCost") else "AmortizedCost",
                "tags": [t_.lower() for t_ in ALLOCATION_TAGS if isinstance(t_, str) and TAG_RX.match(t_)][:5] if isinstance(ALLOCATION_TAGS, (list, tuple)) else [],
                "inheritance": bool(TAG_INHERITANCE), "rg_patterns": [], "logo": LOGO_DATA_URI if isinstance(LOGO_DATA_URI, str) and LOGO_RX.match(LOGO_DATA_URI or "") else "",
                "project_keys": [], "project_source": "", "project_rules": [(re.compile("(?i)" + p_), n_) for p_, n_ in SELF_TEST_RULES]}
    client = MANAGED_IDENTITY_CLIENT_ID
    if not isinstance(client, str) or PLACEHOLDER_RX.match(client) or not is_guid(client):
        raise FinOpsError("configuration_required", "Configuration required: set MANAGED_IDENTITY_CLIENT_ID in the CONFIGURE block to the Client ID "
                          "(GUID) of the Azure SRE Agent managed identity. It is not a secret. operation=self_test runs without it.", "configuration")
    mg = MANAGEMENT_GROUP_ID.strip() if isinstance(MANAGEMENT_GROUP_ID, str) else None
    if mg is None or (mg and not re.fullmatch(r"[A-Za-z0-9_().\-]{1,90}", mg)):
        raise FinOpsError("configuration_required", "MANAGEMENT_GROUP_ID must be empty or a management group ID.", "configuration")
    if not isinstance(SUBSCRIPTION_IDS, (list, tuple)):
        raise FinOpsError("configuration_required", "SUBSCRIPTION_IDS must be a list of subscription IDs.", "configuration")
    subscriptions, placeholders = [], 0
    for value in SUBSCRIPTION_IDS:
        if isinstance(value, str) and PLACEHOLDER_RX.match(value):
            placeholders += 1
            continue
        if not is_guid(value):
            raise FinOpsError("configuration_required", "Every SUBSCRIPTION_IDS entry must be a subscription ID (GUID).", "configuration")
        if value.strip().lower() not in subscriptions:
            subscriptions.append(value.strip().lower())
    if placeholders and not mg:
        raise FinOpsError("configuration_required", "Configuration required: replace <YOUR_SUBSCRIPTION_ID> in SUBSCRIPTION_IDS (or leave the list "
                          "empty and set MANAGEMENT_GROUP_ID).", "configuration")
    if not subscriptions and not mg:
        raise FinOpsError("configuration_required", "Configure at least one subscription in SUBSCRIPTION_IDS or a MANAGEMENT_GROUP_ID.", "configuration")
    if COST_METRIC not in ("AmortizedCost", "ActualCost"):
        raise FinOpsError("configuration_required", "COST_METRIC must be AmortizedCost or ActualCost.", "configuration")
    if not isinstance(ALLOCATION_TAGS, (list, tuple)) or len(ALLOCATION_TAGS) > 5 or not all(isinstance(x, str) and TAG_RX.match(x) for x in ALLOCATION_TAGS):
        raise FinOpsError("configuration_required", "ALLOCATION_TAGS must be a list of up to 5 tag names.", "configuration")
    for name, value, low, high in (("TREND_MONTHS", TREND_MONTHS, 2, 12), ("SNAPSHOT_MAX_AGE_DAYS", SNAPSHOT_MAX_AGE_DAYS, 7, 3650),
                                   ("MAX_SUBSCRIPTIONS", MAX_SUBSCRIPTIONS, 1, 100), ("MAX_COLLECTION_SECONDS", MAX_COLLECTION_SECONDS, 60, 840)):
        if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
            raise FinOpsError("configuration_required", f"{name} must be an integer from {low} to {high}.", "configuration")
    for name, value in (("ANOMALY_MIN_DAILY_DELTA", ANOMALY_MIN_DAILY_DELTA), ("MOM_MIN_DELTA", MOM_MIN_DELTA)):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 10_000_000:
            raise FinOpsError("configuration_required", f"{name} must be a number of 0 or more.", "configuration")
    rg_patterns = []
    if not isinstance(EXCLUDED_RESOURCE_GROUPS, (list, tuple)) or len(EXCLUDED_RESOURCE_GROUPS) > 50:
        raise FinOpsError("configuration_required", "EXCLUDED_RESOURCE_GROUPS must be a list of up to 50 regexes.", "configuration")
    for pattern in EXCLUDED_RESOURCE_GROUPS:
        if not isinstance(pattern, str) or not pattern or len(pattern) > 200:
            raise FinOpsError("configuration_required", "EXCLUDED_RESOURCE_GROUPS entries must be short regexes.", "configuration")
        try:
            rg_patterns.append(re.compile("(?i)" + pattern))
        except re.error as exc:
            raise FinOpsError("configuration_required", "Invalid regex in EXCLUDED_RESOURCE_GROUPS.", "configuration") from exc
    if not isinstance(CLIENT_NAME, str) or len(CLIENT_NAME) > 80 or re.search(r"[\x00-\x1f\x7f<>]", CLIENT_NAME):
        raise FinOpsError("configuration_required", "CLIENT_NAME must be plain text of up to 80 characters.", "configuration")
    if not isinstance(LOGO_DATA_URI, str) or (LOGO_DATA_URI and (len(LOGO_DATA_URI) > 400_000 or not LOGO_RX.match(LOGO_DATA_URI))):
        raise FinOpsError("configuration_required", "LOGO_DATA_URI must be empty or a data:image/...;base64 URI under 400 KB.", "configuration")
    if not isinstance(OUTPUT_DIRECTORY, str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,62}", OUTPUT_DIRECTORY):
        raise FinOpsError("configuration_required", "OUTPUT_DIRECTORY must be a single lowercase folder name.", "configuration")
    project_keys, project_rules = project_settings()
    return {"client_id": client.strip().lower(), "subscriptions": subscriptions, "management_group": mg, "client_name": CLIENT_NAME.strip(),
            "metric": COST_METRIC, "tags": list(dict.fromkeys(x.strip().lower() for x in ALLOCATION_TAGS)), "inheritance": bool(TAG_INHERITANCE),
            "rg_patterns": rg_patterns, "logo": LOGO_DATA_URI, "project_keys": project_keys, "project_source": "configured" if project_keys else "",
            "project_rules": project_rules}


def validate_parameters(operation="report", view="summary", limit=15, project="", project_tag=""):
    operation = (operation or "report").strip().lower() if isinstance(operation, str) else operation
    if operation not in OPERATIONS:
        raise FinOpsError("invalid_parameter", "operation must be one of: report, query, self_test.", "parameters")
    view = (view or "summary").strip().lower() if isinstance(view, str) else view
    if view not in VIEWS:
        raise FinOpsError("invalid_parameter", "view must be one of: " + ", ".join(VIEWS) + ".", "parameters")
    if limit is None:
        limit = 15
    if isinstance(limit, str) and re.fullmatch(r"\s*\d{1,3}\s*", limit):
        limit = int(limit)
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 50:
        raise FinOpsError("invalid_parameter", "limit must be an integer from 1 to 50.", "parameters")
    project = "" if project is None else project
    if not isinstance(project, str) or (project.strip() and not PROJECT_NAME_RX.match(project.strip())):
        raise FinOpsError("invalid_parameter", "project must be a project name of up to 64 characters (or empty for all projects).", "parameters")
    project_tag = "" if project_tag is None else project_tag
    keys = []
    if not isinstance(project_tag, str) or len(project_tag) > 300:
        raise FinOpsError("invalid_parameter", "project_tag must be a tag name, or up to 5 comma-separated tag names.", "parameters")
    for key in project_tag.split(","):
        key = key.strip()
        if not key:
            continue
        if not PROJECT_KEY_RX.match(key):
            raise FinOpsError("invalid_parameter", "project_tag must be a tag name, or up to 5 comma-separated tag names.", "parameters")
        if key.casefold() not in [k.casefold() for k in keys]:
            keys.append(key)
    if len(keys) > 5:
        raise FinOpsError("invalid_parameter", "project_tag accepts up to 5 tag names.", "parameters")
    if operation != "query" and (view != "summary" or limit != 15 or project.strip()):
        raise FinOpsError("invalid_combination", "view, limit and project apply only to operation=query; operation=report always writes the complete review "
                          "(its HTML has a project filter).", "parameters")
    return {"operation": operation, "view": view, "limit": limit, "project": project.strip(), "project_tag": keys}


def review_periods(now):
    today = now.date()
    month_start = today.replace(day=1)
    review_start = add_months(month_start, -1)
    prev_start = add_months(month_start, -2)
    daily_start = min(today - timedelta(days=DAILY_DAYS - 1), review_start - timedelta(days=BASELINE_DAYS))
    complete = today - timedelta(days=DATA_LATENCY_DAYS)
    return {"today": today, "month_start": month_start, "month_end": month_end(month_start), "review_start": review_start,
            "review_end": month_start - timedelta(days=1), "prev_start": prev_start, "prev_end": review_start - timedelta(days=1),
            "trend_start": add_months(month_start, -TREND_MONTHS), "daily_start": daily_start, "complete": complete,
            "review_month": month_key(review_start), "prev_month": month_key(prev_start), "current_month": month_key(month_start)}


# ------------------------- identity and read-only HTTP -------------------------
def normalize_sidecar_claims(claims):
    """Azure SRE Agent sandbox tokens come from the identity sidecar (iss adc-msi-sidecar) with tid/clientId/scp instead of aud/appid."""
    if not isinstance(claims, dict) or claims.get("iss") != SIDECAR_TOKEN_ISSUER:
        return claims
    scope = claims.get("scp") if isinstance(claims.get("scp"), str) else ""
    audience = scope[:-len("/.default")] if scope.endswith("/.default") else scope
    return dict(claims, appid=claims.get("clientId") or claims.get("cid") or None, aud=audience or None)


def claim_check(token, client_id):
    """Informational only: never fails the run (the sandbox proxy swaps placeholder tokens at egress)."""
    try:
        part = token.split(".")[1]
        claims = normalize_sidecar_claims(json.loads(base64.urlsafe_b64decode(part + "=" * (-len(part) % 4))))
    except Exception:
        return "unreadable token (continuing)"
    if not isinstance(claims, dict):
        return "unreadable token (continuing)"
    client = str(claims.get("appid") or claims.get("azp") or "").lower()
    audience = str(claims.get("aud") or "").rstrip("/").lower()
    ok = client == client_id.lower() and audience in ("https://management.azure.com", "https://management.core.windows.net")
    return ("verified " if ok else "not matched to the configured identity (continuing): ") + ("sidecar token" if claims.get("iss") == SIDECAR_TOKEN_ISSUER else "token")


class Identity:
    def __init__(self, client_id):
        try:
            from azure.identity import ManagedIdentityCredential
        except ImportError as exc:
            raise FinOpsError("dependency_missing", "azure-identity is required; it is available in the Azure SRE Agent Python runtime.", "identity") from exc
        self.client_id = client_id
        self.credential = ManagedIdentityCredential(client_id=client_id)
        self.cached = None
        self.check = ""

    def token(self):
        if self.cached and self.cached[1] > time.time() + 120:
            return self.cached[0]
        try:
            access = self.credential.get_token(ARM + "/.default")
        except Exception as exc:
            raise FinOpsError("authentication_failed", f"The managed identity could not get a token for Azure Resource Manager ({type(exc).__name__}). "
                              "Check MANAGED_IDENTITY_CLIENT_ID.", "identity") from exc
        self.check = claim_check(access.token, self.client_id)
        expires = getattr(access, "expires_on", None)
        self.cached = (access.token, expires if isinstance(expires, (int, float)) else time.time() + 300)
        return access.token

    def close(self):
        try:
            self.credential.close()
        except Exception:
            pass


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


ARM_POST_PATHS = (re.compile(r"^/providers/microsoft\.resourcegraph/resources$"),
                  re.compile(r"^/subscriptions/[0-9a-f-]{36}/providers/microsoft\.costmanagement/query$"))
ARM_GET_PATHS = (re.compile(r"^/subscriptions/[0-9a-f-]{36}/providers/microsoft\.consumption/budgets$"),
                 re.compile(r"^/subscriptions/[0-9a-f-]{36}/providers/microsoft\.consumption/tags$"),
                 re.compile(r"^/providers/microsoft\.management/managementgroups/[a-z0-9_().\-]{1,90}/providers/microsoft\.consumption/budgets$"))
RETRYABLE = (429, 500, 502, 503, 504)


class Reader:
    """Read-only HTTPS client: fixed allowlist, no redirects, TLS verification, throttling-aware retries and a time budget."""

    def __init__(self, token_source, deadline, opener=None):
        self.token_source = token_source
        self.deadline = deadline
        self.requests = 0
        self.throttled = 0
        self.waited = 0.0
        self.transport_errors = 0
        if opener is None:
            context = ssl.create_default_context()
            if context.verify_mode != ssl.CERT_REQUIRED or not context.check_hostname:
                raise FinOpsError("unsafe_tls", "TLS certificate and host name verification are mandatory.", "http")
            opener = build_opener(NoRedirect(), HTTPSHandler(context=context))
        self.opener = opener

    @staticmethod
    def check_url(method, url):
        parts = urlsplit(url)
        path = unquote(parts.path).lower()
        if (parts.scheme != "https" or (parts.scheme + "://" + parts.netloc.lower()) != ARM or parts.username or parts.password or parts.fragment
                or "\\" in parts.path or any(seg in (".", "..") for seg in path.split("/")) or len(url) > 8192):
            raise FinOpsError("unsafe_endpoint", "Request URL failed the HTTPS path safety rules.", "http")
        allowed = ARM_POST_PATHS if method == "POST" else ARM_GET_PATHS if method == "GET" else ()
        if not any(rx.match(path) for rx in allowed):
            raise FinOpsError("unsafe_endpoint", f"{method} {parts.path} is outside the read-only allowlist.", "http")

    def remaining(self):
        return self.deadline - time.monotonic()

    def request(self, method, url, source, body=None, attempts=5):
        self.check_url(method, url)
        payload = None if body is None else json.dumps(body).encode("utf-8")
        retried_transport = False
        for attempt in range(attempts):
            if self.remaining() <= 3:
                raise FinOpsError("collection_deadline", f"Collection budget of {MAX_COLLECTION_SECONDS} s reached; the remaining reads were skipped.", "collection")
            if self.requests >= MAX_HTTP_REQUESTS:
                raise FinOpsError("request_cap", "HTTP request cap reached; the remaining reads were skipped.", "collection")
            self.requests += 1
            headers = {"Authorization": "Bearer " + self.token_source(), "Accept": "application/json"}
            if payload is not None:
                headers["Content-Type"] = "application/json"
            try:
                with self.opener.open(Request(url, data=payload, method=method, headers=headers), timeout=max(5.0, min(60.0, self.remaining()))) as response:
                    raw = response.read(HTTP_BYTES + 1)
            except HTTPError as exc:
                hdrs = exc.headers or {}
                waits = [int(v) for k, v in hdrs.items() if k.lower().endswith("retry-after") and re.fullmatch(r"\s*\d{1,5}\s*", str(v))]
                try:
                    detail = exc.read(2000).decode("utf-8", "replace")
                except Exception:
                    detail = ""
                exc.close()
                if exc.code in RETRYABLE and attempt < attempts - 1:
                    wait = min(MAX_RETRY_WAIT, max(waits) + 1 if waits else 4 * (attempt + 1))
                    if self.remaining() > wait + 8:
                        self.throttled += exc.code == 429
                        self.waited += wait
                        time.sleep(wait)
                        continue
                code = "access_denied" if exc.code in (401, 403) else "throttled" if exc.code == 429 else "http_error"
                hint = " (the identity needs Reader on this scope)" if exc.code in (401, 403) else ""
                message = re.search(r'"message"\s*:\s*"([^"]{1,220})', detail)
                raise FinOpsError(code, f"{method} returned HTTP {exc.code}{hint}." + (f" {message.group(1)}" if message and exc.code not in (401, 403) else ""),
                                  source, exc.code) from None
            except (URLError, TimeoutError, ssl.SSLError, OSError) as exc:
                self.transport_errors += 1
                if not retried_transport and self.transport_errors <= 3 and attempt < attempts - 1 and self.remaining() > 70:
                    retried_transport = True
                    time.sleep(2)
                    continue
                raise FinOpsError("transport_failed", f"Network or TLS error during a read-only request ({type(exc).__name__}).", source) from None
            if len(raw) > HTTP_BYTES:
                raise FinOpsError("response_cap", "Response exceeded the byte safety cap.", source)
            try:
                decoded = json.loads(raw) if raw.strip() else {}
            except (ValueError, UnicodeDecodeError):
                raise FinOpsError("invalid_json", "Source returned malformed JSON.", source) from None
            if not isinstance(decoded, dict):
                raise FinOpsError("invalid_shape", "Source returned an unexpected JSON shape.", source)
            return decoded
        raise FinOpsError("http_error", "Bounded HTTP retries exhausted.", source)


def receipt(source_id, label, scope=""):
    return {"id": source_id, "label": label, "scope": scope, "status": "complete", "pages": 0, "records": 0, "seconds": 0.0, "notes": "", "errors": []}


def fail_receipt(rec, exc, has_rows=False):
    rec["status"] = "partial" if has_rows else ("skipped" if exc.code in ("collection_deadline", "request_cap")
                                                else "denied" if exc.http_status in (401, 403) else "error")
    rec["errors"].append(exc.public())
    return rec


def arg_scope(config, subs=None):
    if subs:
        return {"subscriptions": list(subs)}
    if config["management_group"]:
        return {"managementGroups": [config["management_group"]]}
    return {"subscriptions": config["subscriptions"]}


def arg_query(reader, scope, query, rec, key="id"):
    """POST Azure Resource Graph with $skipToken paging, page cap and duplicate-id guard."""
    url = ARM + "/providers/Microsoft.ResourceGraph/resources?api-version=" + ARG_API_VERSION
    rows, seen, skip = [], set(), None
    started = time.monotonic()
    try:
        for _ in range(MAX_ARG_PAGES):
            options = {"$top": 1000, "resultFormat": "objectArray"}
            if skip:
                options["$skipToken"] = skip
            payload = reader.request("POST", url, rec["id"], body=dict(scope, query=query, options=options))
            rec["pages"] += 1
            data = payload.get("data")
            if not isinstance(data, list) or any(not isinstance(r, dict) for r in data):
                raise FinOpsError("invalid_shape", "Resource Graph returned an unexpected data shape.", rec["id"])
            for row in data:
                row_id = str(row.get(key) or "").lower()
                if row_id and row_id in seen:
                    continue
                seen.add(row_id)
                rows.append(row)
            skip = payload.get("$skipToken")
            if not skip:
                break
        else:
            rec["status"] = "partial"
            rec["notes"] = f"Stopped after {MAX_ARG_PAGES} pages."
    except FinOpsError as exc:
        fail_receipt(rec, exc, bool(rows))
    rec["records"] = len(rows)
    rec["seconds"] = round(rec["seconds"] + time.monotonic() - started, 1)
    return rows


def cost_query(reader, sub, body, rec):
    """POST the Cost Management Query API for one subscription, following properties.nextLink."""
    url = f"{ARM}/subscriptions/{sub}/providers/Microsoft.CostManagement/query?api-version={COST_API_VERSION}"
    rows, columns = [], None
    started = time.monotonic()
    try:
        for _ in range(MAX_COST_PAGES):
            payload = reader.request("POST", url, rec["id"], body=body, attempts=6)
            rec["pages"] += 1
            props = payload.get("properties") or {}
            cols = [str(c.get("name") or "") for c in props.get("columns") or [] if isinstance(c, dict)]
            data = props.get("rows") or []
            if not isinstance(data, list) or (data and not cols):
                raise FinOpsError("invalid_shape", "Cost Management returned an unexpected shape.", rec["id"])
            columns = columns or cols
            rows.extend(dict(zip(cols, r)) for r in data if isinstance(r, list))
            if len(rows) > MAX_COST_ROWS:
                raise FinOpsError("row_cap", f"Row cap ({MAX_COST_ROWS}) reached; results are partial.", rec["id"])
            url = props.get("nextLink")
            if not url:
                break
        else:
            rec["status"] = "partial"
            rec["notes"] = f"Stopped after {MAX_COST_PAGES} pages."
    except FinOpsError as exc:
        fail_receipt(rec, exc, bool(rows))
    rec["records"] += len(rows)
    rec["seconds"] = round(rec["seconds"] + time.monotonic() - started, 1)
    return rows if rec["status"] in ("complete", "partial") else None


def cost_body(metric, start, end, granularity, grouping):
    """grouping: dimension names, or (type, name) pairs such as ("TagKey", "Project")."""
    body = {"type": metric, "timeframe": "Custom",
            "timePeriod": {"from": start.isoformat() + "T00:00:00Z", "to": end.isoformat() + "T23:59:59Z"},
            "dataset": {"aggregation": {"totalCost": {"name": "Cost", "function": "Sum"}},
                        "grouping": [{"type": g[0], "name": g[1]} if isinstance(g, tuple) else {"type": "Dimension", "name": g} for g in grouping]}}
    if granularity:
        body["dataset"]["granularity"] = granularity
    return body


def get_tag_keys(reader, sub, rec):
    """Tag keys present in the subscription's cost records (Consumption Tags API, read-only)."""
    url, keys = f"{ARM}/subscriptions/{sub}/providers/Microsoft.Consumption/tags?api-version={BUDGET_API_VERSION}", []
    started = time.monotonic()
    try:
        for _ in range(5):
            payload = reader.request("GET", url, rec["id"])
            rec["pages"] += 1
            props = payload.get("properties") if isinstance(payload.get("properties"), dict) else {}
            for item in props.get("tags") or []:
                key = clean((item or {}).get("key"), 128) if isinstance(item, dict) else ""
                if key and PROJECT_KEY_RX.match(key):
                    keys.append(key)
            url = props.get("nextLink") or payload.get("nextLink")
            if not url:
                break
    except FinOpsError as exc:
        fail_receipt(rec, exc, bool(keys))
    rec["records"] += len(keys)
    rec["seconds"] = round(rec["seconds"] + time.monotonic() - started, 1)
    return keys


def get_budgets(reader, path, rec):
    url, rows = ARM + path + "?api-version=" + BUDGET_API_VERSION, []
    started = time.monotonic()
    try:
        for _ in range(10):
            payload = reader.request("GET", url, rec["id"])
            rec["pages"] += 1
            rows.extend(v for v in payload.get("value") or [] if isinstance(v, dict))
            url = payload.get("nextLink")
            if not url:
                break
    except FinOpsError as exc:
        fail_receipt(rec, exc, bool(rows))
    rec["records"] += len(rows)
    rec["seconds"] = round(rec["seconds"] + time.monotonic() - started, 1)
    return rows


# ------------------------- Resource Graph queries (read-only) -------------------------
Q_CONTAINERS = ("resourcecontainers | where type =~ 'microsoft.resources/subscriptions' or type =~ 'microsoft.resources/subscriptions/resourcegroups' "
                "| project id=tolower(id), type=tolower(type), name, subscriptionId=tolower(subscriptionId), resourceGroup, tags, managedBy, "
                "state=tostring(properties.state)")
Q_TAGS = "resources | where isnotempty(tags) | project id=tolower(id), tags"
Q_ADVISOR = ("advisorresources | where type =~ 'microsoft.advisor/recommendations' and tostring(properties.category) =~ 'Cost' "
             "| project id=tolower(id), subscriptionId=tolower(subscriptionId), resourceGroup, impact=tostring(properties.impact), "
             "problem=tostring(properties.shortDescription.problem), solution=tostring(properties.shortDescription.solution), "
             "typeId=tostring(properties.recommendationTypeId), field=tostring(properties.impactedField), value=tostring(properties.impactedValue), "
             "resourceId=tolower(tostring(properties.resourceMetadata.resourceId)), ext=properties.extendedProperties")


def q_idle(snapshot_days):
    days = int(snapshot_days)
    return ("resources | where type in~ ('microsoft.compute/disks','microsoft.network/publicipaddresses','microsoft.compute/virtualmachines',"
            "'microsoft.web/serverfarms','microsoft.network/networkinterfaces','microsoft.compute/snapshots','microsoft.network/loadbalancers',"
            "'microsoft.network/natgateways') | extend t=tolower(type), p=properties "
            "| extend power=tostring(p.extended.instanceView.powerState.code) "
            "| extend check=case(t == 'microsoft.compute/disks' and tostring(p.diskState) =~ 'Unattached' and isempty(managedBy), 'unattached_disk', "
            "t == 'microsoft.network/publicipaddresses' and isnull(p.ipConfiguration) and isnull(p.natGateway), 'unused_public_ip', "
            "t == 'microsoft.compute/virtualmachines' and power =~ 'PowerState/stopped', 'stopped_vm', "
            "t == 'microsoft.compute/virtualmachines' and power =~ 'PowerState/deallocated', 'deallocated_vm', "
            "t == 'microsoft.web/serverfarms' and toint(p.numberOfSites) == 0 and tolower(tostring(sku.tier)) !in ('free','shared','dynamic','flexconsumption'), 'empty_plan', "
            "t == 'microsoft.network/networkinterfaces' and isnull(p.virtualMachine) and isnull(p.privateEndpoint) and isnull(p.privateLinkService), 'orphaned_nic', "
            f"t == 'microsoft.compute/snapshots' and todatetime(p.timeCreated) < ago({days}d), 'old_snapshot', "
            "t == 'microsoft.network/loadbalancers' and array_length(p.backendAddressPools) == 0, 'idle_load_balancer', "
            "t == 'microsoft.network/natgateways' and array_length(p.subnets) == 0, 'idle_nat_gateway', '') "
            "| where check != '' | project id=tolower(id), name, type=t, resourceGroup, subscriptionId=tolower(subscriptionId), location, check, "
            "sku=tostring(sku.name), tier=tostring(sku.tier), size=toint(p.diskSizeGB), created=tostring(p.timeCreated), "
            "vmSize=tostring(p.hardwareProfile.vmSize), osDisk=tolower(tostring(p.storageProfile.osDisk.managedDisk.id)), "
            "dataDisks=p.storageProfile.dataDisks, tags")


# ------------------------- collection -------------------------
def collect(reader, config, periods):
    """All reads, cheapest and most robust first: Resource Graph and budgets, then Cost Management (throttling-prone)."""
    raw = {"subs": [], "sub_names": {}, "sub_tags": {}, "rgs": {}, "cost": {}, "budgets": [], "tags": {}, "idle": [], "advisor": [],
           "receipts": [], "skipped_subs": [], "invisible_subs": [], "cost_tag_keys": [], "project_detection": None}
    rec = receipt("containers", "src_containers")
    rows = arg_query(reader, arg_scope(config), Q_CONTAINERS, rec)
    raw["receipts"].append(rec)
    for row in rows:
        sub = str(row.get("subscriptionId") or "").lower()
        if row.get("type") == "microsoft.resources/subscriptions":
            raw["sub_names"][sub] = clean(row.get("name"), 120) or sub
            raw["sub_tags"][sub] = row.get("tags") if isinstance(row.get("tags"), dict) else {}
            if str(row.get("state") or "Enabled").lower() not in ("enabled", "pastdue", "warned", ""):
                raw["sub_names"][sub] += " (" + clean(row.get("state"), 20) + ")"
        else:
            raw["rgs"].setdefault(sub, {})[str(row.get("resourceGroup") or row.get("name") or "").lower()] = {
                "name": clean(row.get("name"), 120), "tags": row.get("tags") if isinstance(row.get("tags"), dict) else {},
                "managed_by": clean(row.get("managedBy"), 300)}
    if config["management_group"]:
        subs = sorted(raw["sub_names"], key=lambda s: raw["sub_names"][s].lower())
    else:
        subs = list(config["subscriptions"])
        raw["invisible_subs"] = [s for s in subs if s not in raw["sub_names"] and rec["status"] == "complete"]
    if len(subs) > MAX_SUBSCRIPTIONS:
        raw["skipped_subs"] = subs[MAX_SUBSCRIPTIONS:]
        subs = subs[:MAX_SUBSCRIPTIONS]
    raw["subs"] = subs
    if not subs:
        return raw
    scope = arg_scope(config, subs)
    for source_id, query, key in (("tags", Q_TAGS, "tags"), ("idle", q_idle(SNAPSHOT_MAX_AGE_DAYS), "idle"), ("advisor", Q_ADVISOR, "advisor")):
        r = receipt(source_id, "src_" + source_id)
        rows = arg_query(reader, scope, query, r)
        raw["receipts"].append(r)
        if key == "tags":
            raw["tags"] = {str(x.get("id") or "").lower(): x.get("tags") for x in rows if isinstance(x.get("tags"), dict)}
        else:
            raw[key] = rows
    r = receipt("budgets", "src_budgets")
    paths = [f"/subscriptions/{s}/providers/Microsoft.Consumption/budgets" for s in subs]
    if config["management_group"]:
        paths.insert(0, f"/providers/Microsoft.Management/managementGroups/{config['management_group']}/providers/Microsoft.Consumption/budgets")
    statuses = []
    for path in paths:
        part = receipt("budgets", "src_budgets")
        for b in get_budgets(reader, path, part):
            raw["budgets"].append(dict(b, _scope=path.rsplit("/providers/Microsoft.Consumption", 1)[0]))
        statuses.append(part["status"])
        r["pages"] += part["pages"]
        r["errors"] += part["errors"][:1]
    r["records"] = len(raw["budgets"])
    r["status"] = "complete" if all(s == "complete" for s in statuses) else ("partial" if any(s == "complete" for s in statuses) else statuses[0])
    raw["receipts"].append(r)
    if not config.get("project_keys"):
        r = receipt("cost_tag_keys", "src_cost_tag_keys")
        r["optional"] = True
        statuses, found = [], {}
        for sub in subs:
            part = receipt("cost_tag_keys", "src_cost_tag_keys")
            for k in get_tag_keys(reader, sub, part):
                found.setdefault(k.casefold(), k)
            statuses.append(part["status"])
            r["pages"] += part["pages"]
            r["seconds"] = round(r["seconds"] + part["seconds"], 1)
            r["errors"] += part["errors"][:1]
        raw["cost_tag_keys"] = sorted(found.values(), key=str.casefold)
        r["records"] = len(found)
        r["status"] = "complete" if all(s == "complete" for s in statuses) else ("partial" if any(s == "complete" for s in statuses) else statuses[0])
        raw["receipts"].append(r)
    plan = (("monthly", "src_cost_monthly", periods["trend_start"], periods["today"], "Monthly", ("ResourceGroupName", "ServiceName")),
            ("daily", "src_cost_daily", periods["daily_start"], periods["today"], "Daily", ("ServiceName", "PricingModel")),
            ("resources", "src_cost_resources", periods["prev_start"], periods["today"], "Monthly", ("ResourceId", "ServiceName", "ResourceLocation")))
    for key, label, start, end, gran, grouping in plan:
        collect_cost(reader, config, raw, subs, key, label, start, end, gran, grouping)
    raw["project_detection"] = detect_project_key(raw, config, periods)
    if raw["project_detection"]["keys"]:
        tag_key = raw["project_detection"]["keys"][0]
        collect_cost(reader, config, raw, subs, "project_tags", "src_cost_project", periods["prev_start"], periods["today"], "Monthly",
                     ("ResourceId", ("TagKey", tag_key)), optional=True, min_seconds=60)
    return raw


def collect_cost(reader, config, raw, subs, key, label, start, end, gran, grouping, optional=False, min_seconds=15):
    agg = receipt("cost_" + key, label)
    if optional:
        agg["optional"] = True
    statuses = []
    for sub in subs:
        part = receipt(f"cost_{key}:{sub}", label, sub)
        if reader.remaining() < min_seconds:
            part["status"] = "skipped"
            part["errors"].append(FinOpsError("collection_deadline", "Skipped: collection budget nearly used.", part["id"]).public())
            result = None
        else:
            result = cost_query(reader, sub, cost_body(config["metric"], start, end, gran, grouping), part)
        raw["cost"].setdefault(sub, {})[key] = result
        raw["cost"][sub][key + "_status"] = part["status"]
        statuses.append(part["status"])
        agg["pages"] += part["pages"]
        agg["records"] += part["records"]
        agg["seconds"] = round(agg["seconds"] + part["seconds"], 1)
        if part["errors"]:
            agg["errors"].append(dict(part["errors"][0], scope=sub))
    agg["status"] = ("complete" if all(s == "complete" for s in statuses)
                     else "partial" if any(s in ("complete", "partial") for s in statuses) else (statuses[0] if statuses else "skipped"))
    raw["receipts"].append(agg)


# ------------------------- analysis -------------------------
REGION_NAMES = {"us east": "East US", "us east 2": "East US 2", "us west": "West US", "us west 2": "West US 2", "us west 3": "West US 3",
                "us central": "Central US", "us north central": "North Central US", "us south central": "South Central US",
                "us west central": "West Central US", "eu west": "West Europe", "eu north": "North Europe", "se central": "Sweden Central",
                "fr central": "France Central", "de west central": "Germany West Central", "uk south": "UK South", "uk west": "UK West",
                "es central": "Spain Central", "it north": "Italy North", "ch north": "Switzerland North", "no east": "Norway East",
                "pl central": "Poland Central", "nl west": "West Europe", "ca central": "Canada Central", "br south": "Brazil South",
                "ap southeast": "Southeast Asia", "ap east": "East Asia", "jp east": "Japan East", "au east": "Australia East",
                "in central": "Central India", "global": "Global"}


def region_name(value):
    key = str(value or "").strip().lower()
    if key in ("", "unassigned"):
        return t("unknown_region")
    return REGION_NAMES.get(key) or " ".join(w.upper() if len(w) <= 2 else w.capitalize() for w in key.split())


def type_label(rtype):
    if rtype in TEXT["_types"]:
        return TEXT["_types"][rtype]
    tail = rtype.split("/")[-1] if rtype else ""
    return (tail[:1].upper() + tail[1:]) if tail else ""


def nice_ceiling(value):
    if value <= 0:
        return 0
    exp = 10 ** max(0, int(math.log10(value)) - 1)
    return int(math.ceil(round(value / exp, 6)) * exp)


def pct(part, whole):
    return (part / whole * 100.0) if whole else None


def tag_lookup(tags):
    return {str(k).strip().lower(): str(v).strip() for k, v in (tags or {}).items() if str(v or "").strip()}


def is_excluded(config, rg):
    return bool(rg) and any(p.search(rg) for p in config["rg_patterns"])


def choose_variant(recs):
    """Advisor lists each commitment several times (term x look-back). Keep 1 year / 30 days when present."""
    def key(r):
        ext = r.get("ext") or {}
        term = str(ext.get("term") or "")
        look = str(ext.get("lookbackPeriod") or "")
        return (0 if term == "P1Y" else 1, {"30": 0, "60": 1, "7": 2}.get(look, 3))
    return sorted(recs, key=key)[0]


def ranked_rows(items):
    rows = [{"name": n, "scope": s, "cost": r2(c), "prev": r2(pv), "delta": r2(c - pv), "pct": pct(c - pv, pv), "new": pv <= 0.005 and c > 0}
            for n, s, c, pv in items if c > 0.004 or pv > 0.004]
    return sorted(rows, key=lambda r: -r["cost"])


# ------------------------- projects: which tag names the project, and the project of every resource -------------------------
PROJECT_WHERE = ("resource", "rg", "sub", "cost")


def key_tokens(key):
    text_value = unicodedata.normalize("NFKD", str(key or ""))
    text_value = "".join(ch for ch in text_value if not unicodedata.combining(ch))
    text_value = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", text_value)
    return [w for w in re.split(r"[^a-z0-9]+", text_value.lower()) if w]


def project_name_match(key):
    """(score, meaning) of a tag name. meaning 3 = project, 2 = application or workload, 1 = cost center or team.
    The score is the meaning for an exact name (Proyecto, CostCenter, cost-center) and one less for a partial one (ProjectName)."""
    tokens = key_tokens(key)
    joined = "".join(tokens)
    spans = {"".join(tokens[i:j]) for i in range(len(tokens)) for j in range(i + 1, len(tokens) + 1)}
    best = (0, 0)
    for weight, words in PROJECT_WORDS:
        for word in words:
            if joined == word:
                score = weight
            elif (len(word) >= 4 and word in spans) or (len(word) >= 7 and word in joined):
                score = weight - 1
            else:
                continue
            if score > best[0]:
                best = (score, weight)
    return best


def ptags(tags):
    """Tags with case-insensitive keys and tidy, non-empty values."""
    out = {}
    if isinstance(tags, dict):
        for k, v in tags.items():
            value = re.sub(r"\s+", " ", str(v if v is not None else "")).strip()
            if value and str(k).strip():
                out.setdefault(str(k).strip().casefold(), clean(value, 128))
    return out


def project_context(raw):
    rg_tags, managed = {}, {}
    for sub, groups in raw["rgs"].items():
        for rg, g in groups.items():
            rg_tags[(sub, rg)] = ptags(g.get("tags"))
            if g.get("managed_by"):
                managed[(sub, rg)] = str(g["managed_by"]).lower()
    return {"res": {rid: ptags(tags) for rid, tags in raw["tags"].items()}, "rg": rg_tags, "managed": managed,
            "sub": {s: ptags(tags) for s, tags in raw["sub_tags"].items()}}


def first_value(tags, keys):
    for k in keys:
        if tags.get(k):
            return tags[k]
    return ""


def arg_project(rid, keys, ctx):
    """Project from today's tags in Azure Resource Graph: the resource, then its resource group (for a managed group such as
    an AKS node resource group, the resource that manages it and that resource's group), then the subscription."""
    sub, rg, _, _ = split_id(rid)
    value = first_value(ctx["res"].get(rid, {}), keys)
    if value:
        return value, "resource"
    rg = rg.lower()
    value = first_value(ctx["rg"].get((sub, rg), {}), keys)
    if value:
        return value, "rg"
    manager = ctx["managed"].get((sub, rg))
    if manager:
        msub, mrg, _, _ = split_id(manager)
        value = first_value(ctx["res"].get(manager, {}), keys) or first_value(ctx["rg"].get((msub, mrg.lower()), {}), keys)
        if value:
            return value, "managed"
    value = first_value(ctx["sub"].get(sub, {}), keys)
    return (value, "sub") if value else ("", "")


def review_resource_cost(raw, periods):
    out = defaultdict(float)
    for sub in raw["subs"]:
        for row in raw["cost"].get(sub, {}).get("resources") or []:
            if str(row.get("BillingMonth") or "")[:7] == periods["review_month"]:
                out[str(row.get("ResourceId") or "").lower() or f"/subscriptions/{sub}/(not-a-resource)"] += num(row.get("Cost"))
    return out


def detect_project_key(raw, config, periods):
    """The tag key(s) that name the project: PROJECT_TAG_KEYS or project_tag when set, else the best candidate found on resources,
    resource groups, subscriptions and cost records, scored by name, by the share of the review month's cost it covers and by
    a sensible number of distinct values (2 to 60)."""
    stats = {}

    def note(key, value, where):
        k = str(key or "").strip()
        if not k or not PROJECT_KEY_RX.match(k):
            return
        st = stats.setdefault(k.casefold(), {"names": defaultdict(int), "where": set(), "values": set()})
        st["names"][k] += 0 if where == "cost" else 1  # Cost Management lowercases keys; prefer the casing seen on resources
        st["where"].add(where)
        v = re.sub(r"\s+", " ", str(value if value is not None else "")).strip()
        if v:
            st["values"].add(v.casefold())

    for tags in raw["tags"].values():
        for k, v in (tags.items() if isinstance(tags, dict) else ()):
            note(k, v, "resource")
    for groups in raw["rgs"].values():
        for g in groups.values():
            for k, v in ((g.get("tags") or {}).items() if isinstance(g.get("tags"), dict) else ()):
                note(k, v, "rg")
    for tags in raw["sub_tags"].values():
        for k, v in (tags.items() if isinstance(tags, dict) else ()):
            note(k, v, "sub")
    for k in raw.get("cost_tag_keys") or []:
        note(k, None, "cost")
    costs = review_resource_cost(raw, periods)
    total = sum(v for v in costs.values() if v > 0)
    ctx = project_context(raw)
    configured = list(config.get("project_keys") or [])
    conf_f = [k.casefold() for k in configured]
    for k in configured:
        stats.setdefault(k.casefold(), {"names": defaultdict(int, {k: 0}), "where": set(), "values": set()})
    candidates = []
    for kf, st in stats.items():
        display = max(st["names"], key=lambda n: (st["names"][n], n)) if st["names"] else kf
        score_name, meaning = project_name_match(display)
        if score_name < 1 and kf not in conf_f:
            continue
        in_arg = bool(st["where"] - {"cost"})
        cov = (sum(c for rid, c in costs.items() if c > 0 and arg_project(rid, [kf], ctx)[0]) / total if total > 0 else 0.0) if in_arg else None
        n = len(st["values"])
        fit = 1.0 if 2 <= n <= 60 else 0.5 if n == 1 or 61 <= n <= 200 else 0.0
        candidates.append({"key": display, "kf": kf, "where": [w for w in PROJECT_WHERE if w in st["where"]], "coverage": cov,
                           "values": n if in_arg else None, "name_score": score_name, "meaning": meaning,
                           "score": round(score_name + 2 * (cov or 0.0) + (fit if in_arg else 0.0), 3)})
    candidates.sort(key=lambda c: (-c["score"], -(c["coverage"] or 0), c["key"].casefold()))
    chosen = None
    if configured:
        keys, source = [next((c["key"] for c in candidates if c["kf"] == k.casefold()), k) for k in configured], config.get("project_source") or "configured"
    else:
        qualified = [c for c in candidates if c["name_score"] >= 1 and (c["coverage"] or 0) > 0]
        cost_only = [c for c in candidates if c["coverage"] is None and c["name_score"] >= 2]
        chosen = (qualified or cost_only or [None])[0]
        keys, source = ([chosen["key"]], "detected") if chosen else ([], "none")
    keys_f = [k.casefold() for k in keys]
    for c in candidates:
        c["chosen"] = c["kf"] in keys_f
    candidates.sort(key=lambda c: not c["chosen"])
    return {"keys": keys, "source": source, "candidates": candidates[:8], "chosen": chosen}


def cost_record_projects(raw):
    """Latest non-empty project tag value per resource in the cost records (TagKey grouping)."""
    best = {}
    for sub in raw["subs"]:
        for row in raw["cost"].get(sub, {}).get("project_tags") or []:
            value = re.sub(r"\s+", " ", str(row.get("TagValue") or "")).strip().strip('"')
            rid = str(row.get("ResourceId") or "").lower()
            month = str(row.get("BillingMonth") or "")[:7]
            if value and rid and (rid not in best or month > best[rid][0]):
                best[rid] = (month, clean(value, 128))
    return {rid: v for rid, (_, v) in best.items()}


def analyze_projects(raw, config, p, det, res_cost, res_svc, res_loc, names):
    """Project of every resource (resource tag, resource group tag, subscription tag, cost-record tag, resource group name rule,
    else Unallocated), using today's tags for every month, and the cost per project."""
    keys = [k.casefold() for k in det["keys"]]
    ctx = project_context(raw)
    cost_tags = cost_record_projects(raw) if keys else {}
    rules = config.get("project_rules") or []
    review, prev, cur = p["review_month"], p["prev_month"], p["current_month"]

    def rg_display(sub, rg):
        return (raw["rgs"].get(sub, {}).get(rg.lower()) or {}).get("name") or rg

    def resolve(rid):
        sub, rg, _, _ = split_id(rid)
        if keys:
            value, source = arg_project(rid, keys, ctx)
            if value:
                return value, source
            if cost_tags.get(rid):
                return cost_tags[rid], "cost"
        if rg:
            for rx, project in rules:
                if rx.search(rg_display(sub, rg)):
                    return project, "rule"
        return "", "none"

    groups, by_source, proj_of, rg_votes = {}, defaultdict(float), {}, defaultdict(lambda: defaultdict(float))
    total = 0.0
    for rid, months in res_cost.items():
        value, source = resolve(rid)
        gk = value.casefold() if value else ""
        g = groups.get(gk)
        if g is None:
            g = groups[gk] = {"gk": gk, "names": defaultdict(float), "cost": 0.0, "prev": 0.0, "mtd": 0.0, "res": set(), "src": defaultdict(float),
                              "rg": defaultdict(lambda: [0.0, 0.0]), "svc": defaultdict(lambda: [0.0, 0.0]), "reg": defaultdict(float),
                              "sub": defaultdict(lambda: [0.0, 0.0])}
        c, pv, mtd = months.get(review, 0.0), months.get(prev, 0.0), months.get(cur, 0.0)
        g["names"][value] += abs(c) + abs(pv) + abs(mtd) + 1e-9
        g["cost"] += c
        g["prev"] += pv
        g["mtd"] += mtd
        if max(abs(c), abs(pv), abs(mtd)) > 0.004:
            g["res"].add(rid)
        sub, rg, _, _ = split_id(rid)
        g["rg"][(sub, rg.lower())][0] += c
        g["rg"][(sub, rg.lower())][1] += pv
        g["sub"][sub][0] += c
        g["sub"][sub][1] += pv
        g["reg"][region_name(res_loc.get(rid))] += c
        for svc, sm in res_svc.get(rid, {}).items():
            g["svc"][svc][0] += sm.get(review, 0.0)
            g["svc"][svc][1] += sm.get(prev, 0.0)
        g["src"][source] += c
        by_source[source] += c
        total += c
        proj_of[rid] = (gk, source)
        if rg:
            rg_votes[(sub, rg.lower())][gk] += abs(c) + abs(pv)
    named = sorted((g for gk, g in groups.items() if gk and max(abs(g["cost"]), abs(g["prev"]), abs(g["mtd"])) > 0.004),
                   key=lambda g: (-g["cost"], -g["mtd"], -g["prev"], g["gk"]))
    order = named + ([groups[""]] if "" in groups and max(abs(groups[""]["cost"]), abs(groups[""]["prev"]), abs(groups[""]["mtd"])) > 0.004 else [])
    items, id_of = [], {}
    for i, g in enumerate(order):
        pid = f"p{i}"
        id_of[g["gk"]] = pid
        name = max(g["names"], key=lambda n: (g["names"][n], n)) if g["gk"] else t("proj_unallocated")
        multi = len(raw["subs"]) > 1
        items.append({"id": pid, "name": name, "unallocated": not g["gk"], "cost": r2(g["cost"]), "prev": r2(g["prev"]),
                      "delta": r2(g["cost"] - g["prev"]), "pct": pct(g["cost"] - g["prev"], g["prev"]), "mtd": r2(g["mtd"]), "share": pct(g["cost"], total),
                      "resources": len(g["res"]), "resource_groups": sum(1 for (s, rg), v in g["rg"].items() if rg and max(abs(v[0]), abs(v[1])) > 0.004),
                      "by_rg": ranked_rows([(rg_display(s, rg) if rg else t("no_rg"), names.get(s, s) if multi else "", v[0], v[1]) for (s, rg), v in g["rg"].items()])[:50],
                      "by_service": ranked_rows([(svc, "", v[0], v[1]) for svc, v in g["svc"].items()])[:50],
                      "by_region": sorted(({"name": k, "cost": r2(v)} for k, v in g["reg"].items() if v > 0.004), key=lambda r: -r["cost"]),
                      "by_sub": [{"id": s, "name": names.get(s, s), "cost": r2(v[0]), "prev": r2(v[1]), "delta": r2(v[0] - v[1]), "pct": pct(v[0] - v[1], v[1])}
                                 for s, v in sorted(g["sub"].items(), key=lambda kv: -kv[1][0]) if max(abs(v[0]), abs(v[1])) > 0.004],
                      "sources": {k: r2(v) for k, v in g["src"].items() if abs(v) > 0.004}, "variant": i < PROJECT_VARIANTS or not g["gk"],
                      "savings": 0.0, "savings_idle": 0.0, "savings_advisor": 0.0, "findings": 0, "actions": [], "top_resources": []})
    by_id = {it["id"]: it for it in items}

    def project_of(rid):
        """(id, name, source) of the project of a resource ID; empty strings when it is not a resource or there are no projects."""
        if not split_id(rid)[2] and "(not-a-resource)" not in rid:
            return "", "", ""
        if rid in proj_of:
            gk, source = proj_of[rid]
        else:
            value, source = resolve(rid)
            gk = value.casefold()
        pid = id_of.get(gk)
        if not pid:
            sub, rg, _, _ = split_id(rid)
            pid = rg_project.get((sub, rg.lower()), ("",))[0] or id_of.get("")
        return (pid, by_id[pid]["name"], source) if pid else ("", "", "")

    rg_project = {}
    for key, votes in rg_votes.items():
        pid = id_of.get(max(votes, key=lambda k: (votes[k], k)))
        if pid:
            rg_project[key] = (pid, by_id[pid]["name"])
    unalloc = groups.get("", {"rg": {}, "cost": 0.0})
    multi = len(raw["subs"]) > 1
    unalloc_rgs = sorted(([v[0], rg_display(s, rg) if rg else t("sub_level"), names.get(s, s) if multi else ""] for (s, rg), v in unalloc["rg"].items() if v[0] > 0.004),
                         reverse=True)[:5]
    allocated = total - (unalloc["cost"] if "" in groups else 0.0)
    tagged = sum(by_source.get(s, 0.0) for s in ("resource", "rg", "managed", "sub"))
    chosen = det.get("chosen")
    summary = {"key": det["keys"][0] if det["keys"] else "", "keys": det["keys"], "source": det["source"],
               "candidates": [{"key": c["key"], "where": c["where"], "coverage_pct": round(c["coverage"] * 100, 1) if c["coverage"] is not None else None,
                               "values": c["values"], "meaning": c["meaning"], "name_score": c["name_score"], "chosen": c["chosen"]} for c in det["candidates"]],
               "reason": {"meaning": chosen["meaning"], "coverage_pct": round((chosen["coverage"] or 0) * 100, 1) if chosen["coverage"] is not None else None,
                          "values": chosen["values"]} if chosen else None,
               "total": r2(total), "allocated": r2(allocated), "allocated_pct": pct(allocated, total), "tagged_pct": pct(tagged, total),
               "by_source": {s: r2(by_source.get(s, 0.0)) for s in PROJECT_SOURCES}, "items": items, "named": len(named),
               "rules": [{"pattern": rx.pattern[4:], "project": name} for rx, name in rules],
               "cost_tags_read": bool(keys) and any(raw["cost"].get(s, {}).get("project_tags") is not None for s in raw["subs"]),
               "unallocated_rgs": [{"rg": rg, "sub": sub, "cost": r2(c)} for c, rg, sub in unalloc_rgs]}
    return summary, project_of, rg_project


def analyze(raw, config, periods, now):
    p = periods
    subs = raw["subs"]
    names = {s: raw["sub_names"].get(s, s) for s in subs}
    # ---- currency per subscription; the report currency is the one with most cost
    cur_cost = defaultdict(float)
    sub_cur = {}
    for sub in subs:
        counts = defaultdict(float)
        for key in ("monthly", "daily", "resources"):
            for row in raw["cost"].get(sub, {}).get(key) or []:
                counts[str(row.get("Currency") or "").upper() or "?"] += abs(num(row.get("Cost")))
        if counts:
            sub_cur[sub] = max(counts, key=counts.get)
            cur_cost[sub_cur[sub]] += counts[sub_cur[sub]]
    currency = max(cur_cost, key=cur_cost.get) if cur_cost else "USD"
    other_currency = [s for s in subs if sub_cur.get(s) and sub_cur[s] != currency]

    def ok(sub, key):
        return sub not in other_currency and raw["cost"].get(sub, {}).get(key) is not None

    # ---- monthly (Q1)
    months = [month_key(add_months(p["month_start"], -k)) for k in range(TREND_MONTHS, -1, -1)]
    m_total, m_sub = defaultdict(float), defaultdict(lambda: defaultdict(float))
    m_rg, m_svc, rg_names = defaultdict(lambda: defaultdict(float)), defaultdict(lambda: defaultdict(float)), {}
    monthly_ok = [s for s in subs if ok(s, "monthly")]
    for sub in monthly_ok:
        for row in raw["cost"][sub]["monthly"]:
            m = str(row.get("BillingMonth") or row.get("UsageDate") or "")[:7].replace("/", "-")
            if not re.fullmatch(r"\d{4}-\d{2}", m):
                d = parse_day(row.get("BillingMonth") or row.get("UsageDate"))
                m = month_key(d) if d else ""
            if not m:
                continue
            c = num(row.get("Cost"))
            rg_raw = str(row.get("ResourceGroupName") or "")
            rg = rg_raw.lower()
            svc = clean(row.get("ServiceName"), 80) or "Other"
            m_total[m] += c
            m_sub[sub][m] += c
            m_rg[(sub, rg)][m] += c
            m_svc[svc][m] += c
            if rg and (sub, rg) not in rg_names:
                known = raw["rgs"].get(sub, {}).get(rg)
                rg_names[(sub, rg)] = known["name"] if known else rg_raw
    # ---- daily (Q2)
    days = [p["daily_start"] + timedelta(days=k) for k in range((p["today"] - p["daily_start"]).days + 1)]
    d_total, d_sub = defaultdict(float), defaultdict(lambda: defaultdict(float))
    d_svc = defaultdict(lambda: defaultdict(float))
    pm_review, pm_svc_review = defaultdict(float), defaultdict(lambda: defaultdict(float))
    daily_ok = [s for s in subs if ok(s, "daily")]
    for sub in daily_ok:
        for row in raw["cost"][sub]["daily"]:
            d = parse_day(row.get("UsageDate"))
            if not d:
                continue
            c = num(row.get("Cost"))
            svc = clean(row.get("ServiceName"), 80) or "Other"
            d_total[d] += c
            d_sub[sub][d] += c
            d_svc[svc][d] += c
            if p["review_start"] <= d <= p["review_end"]:
                model = clean(row.get("PricingModel"), 40) or "OnDemand"
                pm_review[model] += c
                pm_svc_review[svc][model] += c
    # ---- resources (Q3: by resource, service and region; the previous month, the review month and this month)
    res_cost, res_loc = defaultdict(lambda: defaultdict(float)), {}
    res_svc = defaultdict(lambda: defaultdict(lambda: defaultdict(float)))
    resources_ok = [s for s in subs if ok(s, "resources")]
    for sub in resources_ok:
        for row in raw["cost"][sub]["resources"]:
            m = str(row.get("BillingMonth") or "")[:7]
            rid = str(row.get("ResourceId") or "").lower() or f"/subscriptions/{sub}/(not-a-resource)"
            c = num(row.get("Cost"))
            res_cost[rid][m] += c
            res_svc[rid][clean(row.get("ServiceName"), 80) or "Other"][m] += c
            if row.get("ResourceLocation") and rid not in res_loc:
                res_loc[rid] = str(row.get("ResourceLocation"))
    review, prev, cur = p["review_month"], p["prev_month"], p["current_month"]

    def month_cost(sub, m):
        if sub in monthly_ok:
            return m_sub[sub].get(m, 0.0)
        start = date(int(m[:4]), int(m[5:7]), 1)
        if sub in daily_ok and start >= p["daily_start"] and month_end(start) <= p["today"]:
            return sum(v for d, v in d_sub[sub].items() if month_key(d) == m)
        return None

    # ---- settled days, month to date, forecast
    settled = p["complete"]
    settled_days = [d for d in days if p["month_start"] <= d <= settled]
    k_days = len(settled_days)
    dim = (p["month_end"] - p["month_start"]).days + 1

    def forecast_for(series):
        last7 = [series.get(settled - timedelta(days=i), 0.0) for i in range(7) if settled - timedelta(days=i) >= p["daily_start"]]
        rate = sum(last7) / len(last7) if last7 else 0.0
        so_far = sum(series.get(d, 0.0) for d in settled_days)
        return so_far + rate * (dim - k_days), rate

    have_daily = bool(daily_ok)
    mtd = sum(v for d, v in d_total.items() if d >= p["month_start"]) if have_daily else None
    forecast, run_rate = forecast_for(d_total) if have_daily else (None, None)
    pace = None
    if have_daily and k_days:
        a = sum(d_total.get(p["month_start"] + timedelta(days=i), 0.0) for i in range(k_days))
        b = sum(d_total.get(p["review_start"] + timedelta(days=i), 0.0) for i in range(k_days))
        pace = {"days": k_days, "current": r2(a), "previous": r2(b), "pct": pct(a - b, b)}
    sub_rows = []
    for sub in subs:
        c, pv = month_cost(sub, review), month_cost(sub, prev)
        fc = forecast_for(d_sub[sub])[0] if sub in daily_ok else None
        sub_rows.append({"id": sub, "name": names[sub], "cost": r2(c) if c is not None else None, "prev": r2(pv) if pv is not None else None,
                         "delta": r2(c - pv) if c is not None and pv is not None else None,
                         "pct": pct(c - pv, pv) if c is not None and pv else None,
                         "mtd": r2(sum(v for d, v in d_sub[sub].items() if d >= p["month_start"])) if sub in daily_ok else None,
                         "forecast": r2(fc) if fc is not None else None, "currency": sub_cur.get(sub, currency),
                         "read": all(ok(sub, k) for k in ("monthly", "daily", "resources"))})
    have_cost = any(r["cost"] is not None for r in sub_rows)
    review_total = sum(r["cost"] or 0 for r in sub_rows) if have_cost else None
    prev_total = sum(r["prev"] or 0 for r in sub_rows if r["prev"] is not None) if any(r["prev"] is not None for r in sub_rows) else None
    sub_rows.sort(key=lambda r: -(r["cost"] or 0))
    monthly = []
    for m in months:
        if m == cur:
            monthly.append({"month": m, "cost": r2(mtd) if mtd is not None else r2(m_total.get(m, 0.0)), "partial": True,
                            "forecast": r2(forecast) if forecast is not None else None})
        else:
            v = sum((month_cost(s, m) or 0.0) for s in subs if s in monthly_ok or s in daily_ok)
            monthly.append({"month": m, "cost": r2(v), "partial": False, "forecast": None})
    # ---- daily series with typical day and unusual days
    daily, unusual = [], []
    min_delta = float(ANOMALY_MIN_DAILY_DELTA)
    for d in days:
        base = [d_total.get(d - timedelta(days=i), 0.0) for i in range(1, BASELINE_DAYS + 1) if d - timedelta(days=i) >= p["daily_start"]]
        typical = median(base) if len(base) >= 7 else None
        row = {"date": d.isoformat(), "cost": r2(d_total.get(d, 0.0)), "typical": r2(typical) if typical is not None else None,
               "settled": d <= settled, "flag": None}
        if have_daily and typical and d <= settled and d >= p["review_start"]:
            cost_d = d_total.get(d, 0.0)
            week = d_total.get(d - timedelta(days=7)) if d - timedelta(days=7) >= p["daily_start"] else None
            delta = cost_d - typical
            if delta >= min_delta and delta / typical >= ANOMALY_DAY_PCT / 100 and (not week or cost_d >= 1.2 * week):
                drivers = []
                for svc, series in d_svc.items():
                    sb = [series.get(d - timedelta(days=i), 0.0) for i in range(1, BASELINE_DAYS + 1) if d - timedelta(days=i) >= p["daily_start"]]
                    sd = series.get(d, 0.0) - median(sb)
                    if sd > 0.1 * delta:
                        drivers.append((sd, svc))
                drivers.sort(reverse=True)
                sev = "high" if delta >= 3 * min_delta and delta / typical >= 0.5 else "medium"
                row["flag"] = sev
                unusual.append({"date": d.isoformat(), "cost": r2(cost_d), "typical": r2(typical), "delta": r2(delta), "pct": delta / typical * 100,
                                "week": r2(week) if week is not None else None, "severity": sev,
                                "drivers": [{"service": s, "delta": r2(v)} for v, s in drivers[:3]]})
        daily.append(row)
    # ---- month-over-month jumps and new spend
    jumps, new_items = [], []
    mom_min = float(MOM_MIN_DELTA)
    before3 = [month_key(add_months(p["review_start"], -k)) for k in (1, 2, 3)]

    def consider(kind, name, series, scope, key=None):
        c, pv = series.get(review, 0.0), series.get(prev, 0.0)
        if c <= 0:
            return
        ref = {"sub_id": key[0], "rg_key": key[1]} if key else {}
        if all(series.get(m, 0.0) <= 0.005 for m in before3) and c >= max(mom_min / 4, 1.0):
            new_items.append(dict(ref, kind=kind, name=name, scope=scope, cost=r2(c), severity="medium" if c >= mom_min else "low"))
            return
        delta = c - pv
        if delta >= mom_min and pv > 0 and delta / pv * 100 >= MOM_MIN_PCT:
            jumps.append(dict(ref, kind=kind, name=name, scope=scope, cost=r2(c), prev=r2(pv), delta=r2(delta), pct=delta / pv * 100,
                              severity="high" if delta >= 3 * mom_min and delta / pv >= 0.5 else "medium"))

    for svc, series in m_svc.items():
        consider("service", svc, series, "")
    for (sub, rg), series in m_rg.items():
        if rg:
            consider("rg", rg_names.get((sub, rg), rg), series, names.get(sub, sub), (sub, rg))
    jumps.sort(key=lambda j: -j["delta"])
    new_items.sort(key=lambda j: -j["cost"])

    # ---- breakdowns for the review month
    ranked = ranked_rows

    by_rg = ranked([(rg_names.get((s, rg), rg) if rg else t("no_rg"), names.get(s, s), v.get(review, 0.0), v.get(prev, 0.0))
                    for (s, rg), v in m_rg.items()])
    by_service = ranked([(svc, "", v.get(review, 0.0), v.get(prev, 0.0)) for svc, v in m_svc.items()])
    reg = defaultdict(float)
    for rid, v in res_cost.items():
        reg[region_name(res_loc.get(rid))] += v.get(review, 0.0)
    by_region = sorted(({"name": k, "cost": r2(v)} for k, v in reg.items() if v > 0.004), key=lambda r: -r["cost"])
    res_rows = []
    for rid, v in res_cost.items():
        c, pv = v.get(review, 0.0), v.get(prev, 0.0)
        if c <= 0.004 and pv <= 0.004:
            continue
        sub, rg, rtype, name = split_id(rid)
        res_rows.append({"id": rid, "name": name if "(not-a-resource)" not in rid else "\u2014", "rg": (raw["rgs"].get(sub, {}).get(rg.lower()) or {}).get("name") or rg,
                         "sub": names.get(sub, sub), "type": type_label(rtype), "region": region_name(res_loc.get(rid)),
                         "cost": r2(c), "prev": r2(pv), "delta": r2(c - pv), "pct": pct(c - pv, pv), "new": pv <= 0.004 and c > 0, "gone": c <= 0.004})
    res_rows.sort(key=lambda r: -r["cost"])
    # ---- budgets
    budgets, budget_subs, mg_budget = [], set(), None
    for b in raw["budgets"]:
        props = b.get("properties") or {}
        amount = num(props.get("amount"))
        spent = num((props.get("currentSpend") or {}).get("amount"))
        fc_raw = (props.get("forecastSpend") or {}).get("amount")
        scope_path = str(b.get("_scope") or "")
        sub = scope_path.split("/")[2].lower() if scope_path.lower().startswith("/subscriptions/") else ""
        if fc_raw is None and sub:
            fc_raw = next((r["forecast"] for r in sub_rows if r["id"] == sub), None)
        fc = num(fc_raw) if fc_raw is not None else None
        filtered = bool(props.get("filter"))
        notes = []
        for n in (props.get("notifications") or {}).values():
            if isinstance(n, dict) and n.get("enabled", True):
                notes.append(((str(n.get("thresholdType") or "Actual")).lower(), num(n.get("threshold"))))
        used, fused = pct(spent, amount), pct(fc, amount) if fc is not None else None
        status = ("over" if used is not None and used >= 100 else "forecast_over" if fused is not None and fused >= 100
                  else "risk" if (used is not None and used >= 80) or (fused is not None and fused >= 90) else "ok")
        scope_label = names.get(sub) if sub else (t("chip_mg", v=config["management_group"]) if "managementgroups" in scope_path.lower() else scope_path)
        row = {"name": clean(b.get("name"), 120), "scope": scope_label, "scope_id": scope_path, "sub": sub, "amount": r2(amount), "spent": r2(spent),
               "forecast": r2(fc) if fc is not None else None, "used_pct": used, "forecast_pct": fused, "grain": clean(props.get("timeGrain"), 20) or "Monthly",
               "status": status, "filtered": filtered, "alerts": sorted(notes, key=lambda x: (x[0] != "actual", x[1])),
               "currency": clean((props.get("currentSpend") or {}).get("unit"), 8) or currency}
        budgets.append(row)
        if not filtered and row["grain"].lower() in ("monthly", "billingmonth"):
            if sub:
                budget_subs.add(sub)
            elif "managementgroups" in scope_path.lower():
                mg_budget = row
    budgets.sort(key=lambda r: ({"over": 0, "forecast_over": 1, "risk": 2, "ok": 3}[r["status"]], -(r["forecast_pct"] or 0)))
    budget_total, budget_fc = 0.0, 0.0
    if mg_budget:
        budget_total, budget_fc = mg_budget["amount"], forecast or 0.0
    else:
        for sub in budget_subs:
            amounts = [b["amount"] for b in budgets if b["sub"] == sub and not b["filtered"] and b["grain"].lower() in ("monthly", "billingmonth")]
            budget_total += max(amounts)
            budget_fc += next((r["forecast"] or 0.0 for r in sub_rows if r["id"] == sub), 0.0)
    no_budget = [] if mg_budget else [r for r in sub_rows if r["id"] not in budget_subs and r["cost"] is not None]
    with_cost = [r for r in sub_rows if r["cost"] is not None]
    budget_cov = {"budgets": len(budgets), "over": sum(1 for b in budgets if b["status"] in ("over", "forecast_over")),
                  "subs": len(with_cost), "budgeted": len(with_cost) if mg_budget else sum(1 for r in with_cost if r["id"] in budget_subs)}
    budget_cov["full"] = bool(budget_cov["subs"]) and budget_cov["budgeted"] == budget_cov["subs"]
    # ---- savings: idle and orphaned resources, Advisor, commitments
    def resource_cost(rid):
        return res_cost.get(rid, {}).get(review, 0.0)

    savings = {}
    for item in raw["idle"]:
        rid = str(item.get("id") or "").lower()
        name = clean(item.get("name"), 120)
        rg = clean(item.get("resourceGroup"), 90)
        tags = tag_lookup(item.get("tags"))
        if item.get("check") == "unattached_disk" and (name.lower().endswith("-asrreplica") or "asr-replicadisk" in tags):
            continue
        if is_excluded(config, rg):
            continue
        check = str(item.get("check") or "")
        cost = resource_cost(rid)
        detail = []
        if check in ("unattached_disk",):
            detail = [f"{item.get('size') or '?'} GB", clean(item.get("sku"), 30)]
        elif check in ("stopped_vm", "deallocated_vm"):
            detail = [clean(item.get("vmSize"), 40)]
            if check == "deallocated_vm":
                disks = [str(item.get("osDisk") or "")] + [str(((x or {}).get("managedDisk") or {}).get("id") or "").lower()
                                                           for x in (item.get("dataDisks") or []) if isinstance(x, dict)]
                disk_cost = sum(resource_cost(dd) for dd in disks if dd)
                cost += disk_cost
                if disk_cost:
                    detail.append(t("disks_only"))
        elif check in ("unused_public_ip", "idle_load_balancer", "idle_nat_gateway", "empty_plan"):
            detail = [clean(item.get("sku"), 30), clean(item.get("tier"), 30)]
        elif check == "old_snapshot":
            created = parse_day(item.get("created"))
            detail = [f"{(p['today'] - created).days} d" if created else "", f"{item.get('size') or '?'} GB"]
        if "pvc-" in name.lower() and check == "unattached_disk":
            detail.append(t("k8s_volume"))
        saving = 0.0 if check == "orphaned_nic" else cost
        savings[rid] = {"source": "idle", "check": check, "id": rid, "name": name, "rg": rg, "sub": names.get(str(item.get("subscriptionId") or "").lower(), ""),
                        "type": type_label(str(item.get("type") or "")), "region": clean(item.get("location"), 40), "detail": " \u00b7 ".join(x for x in detail if x),
                        "cost": r2(cost), "saving": r2(saving), "also": []}
    advisor, commit_recs = [], defaultdict(list)
    for rec in raw["advisor"]:
        ext = rec.get("ext") if isinstance(rec.get("ext"), dict) else {}
        problem = clean(rec.get("problem") or rec.get("solution"), 200)
        sub_cat = str(ext.get("recommendationSubCategory") or "").lower()
        is_commit = sub_cat in ("reservations", "savingsplans", "savingsplan") or re.search(r"(?i)reserved instance|reservation|savings plan", problem or "")
        amount = num(ext.get("savingsAmount")) if ext.get("savingsAmount") not in (None, "") else None
        cur_ = str(ext.get("savingsCurrency") or currency).upper()
        sub = str(rec.get("subscriptionId") or "").lower()
        if is_commit:
            kind = "sp" if ("savings plan" in (problem or "").lower() or "savingsplan" in sub_cat) else "ri"
            group = (sub, kind, str(ext.get("vmSize") or ext.get("displaySKU") or ext.get("sku") or ""), str(ext.get("region") or ext.get("location") or ""),
                     str(ext.get("scope") or ""), str(ext.get("reservedResourceType") or ""))
            commit_recs[group].append(dict(rec, _amount=amount, _cur=cur_))
            continue
        rid = str(rec.get("resourceId") or "").lower()
        _, rg, rtype, name = split_id(rid)
        if is_excluded(config, rg):
            continue
        cost = resource_cost(rid)
        saving = amount if amount is not None and cur_ == currency else (cost if re.search(r"(?i)unattached|delete|unused|idle|shut ?down", problem or "") else 0.0)
        row = {"source": "advisor", "check": "advisor", "id": rid, "name": clean(rec.get("value"), 120) or name, "rg": rg, "sub": names.get(sub, sub),
               "type": type_label(rtype), "problem": problem, "impact": clean(rec.get("impact"), 10), "advisor_amount": r2(amount) if amount is not None else None,
               "advisor_currency": cur_, "cost": r2(cost), "saving": r2(saving), "also": []}
        advisor.append(row)
        if rid in savings:
            if row["saving"] > savings[rid]["saving"]:
                row["also"].append(savings[rid]["check"])
                savings[rid] = row
            else:
                savings[rid]["also"].append("advisor")
        else:
            savings[rid] = row
    commit_by_sub = defaultdict(lambda: {"ri": 0.0, "sp": 0.0, "ri_items": [], "sp_items": []})
    for (sub, kind, sku, region, scope, rtype), recs in commit_recs.items():
        chosen = choose_variant(recs)
        ext = chosen.get("ext") or {}
        amount = chosen["_amount"] if chosen["_cur"] == currency else None
        if amount is None:
            continue
        alt = [r for r in recs if (r.get("ext") or {}).get("term") == "P3Y" and r["_cur"] == currency]
        entry = {"sku": sku or ("Compute savings plan" if kind == "sp" else rtype), "region": region, "term": str(ext.get("term") or ""),
                 "lookback": str(ext.get("lookbackPeriod") or ""), "qty": clean(ext.get("displayQty") or ext.get("qty"), 10), "saving": r2(amount),
                 "saving_3y": r2(max(r["_amount"] or 0 for r in alt)) if alt and str(ext.get("term") or "") != "P3Y" else None, "sub": names.get(sub, sub)}
        commit_by_sub[sub][kind] += amount
        commit_by_sub[sub][kind + "_items"].append(entry)
    commit_best, commit_items, commit_alt = 0.0, [], []
    for sub, c in commit_by_sub.items():
        best = "ri" if c["ri"] >= c["sp"] else "sp"
        commit_best += c[best]
        commit_items += c[best + "_items"]
        other = "sp" if best == "ri" else "ri"
        if c[other]:
            commit_alt.append({"kind": other, "saving": r2(c[other]), "sub": names.get(sub, sub)})
    eligible = {m: 0.0 for m in ("OnDemand", "Reservation", "SavingsPlan", "Spot")}
    for svc, models in pm_svc_review.items():
        if svc.lower() in COMMITMENT_SERVICES:
            for model, v in models.items():
                key = model if model in eligible else "OnDemand"
                eligible[key] += v
    covered = eligible["Reservation"] + eligible["SavingsPlan"]
    elig_total = covered + eligible["OnDemand"]
    commitment = {"pricing_models": {k: r2(v) for k, v in pm_review.items()}, "eligible": {k: r2(v) for k, v in eligible.items()},
                  "eligible_total": r2(elig_total), "coverage_pct": pct(covered, elig_total), "best_saving": r2(commit_best),
                  "items": sorted(commit_items, key=lambda x: -x["saving"]), "alternatives": commit_alt,
                  "approximate": config["metric"] != "AmortizedCost"}
    idle_saving = sum(v["saving"] for v in savings.values() if v["source"] == "idle")
    advisor_saving = sum(v["saving"] for v in savings.values() if v["source"] == "advisor")
    savings_total = idle_saving + advisor_saving + commit_best
    # ---- allocation readiness
    allocation = None
    if config["tags"]:
        req = config["tags"]
        per_tag = {tg: 0.0 for tg in req}
        all_cost, total_alloc, not_res = 0.0, 0.0, 0.0
        rg_untagged = defaultdict(float)
        for rid, v in res_cost.items():
            c = v.get(review, 0.0)
            if c <= 0:
                continue
            total_alloc += c
            sub, rg, rtype, name = split_id(rid)
            have = {}
            if config["inheritance"]:
                have.update(tag_lookup(raw["sub_tags"].get(sub)))
                have.update(tag_lookup((raw["rgs"].get(sub, {}).get(rg.lower()) or {}).get("tags")))
            have.update(tag_lookup(raw["tags"].get(rid)))
            if "(not-a-resource)" in rid or not rtype:
                not_res += c
            missing = [tg for tg in req if tg not in have]
            for tg in req:
                if tg in have:
                    per_tag[tg] += c
            if not missing:
                all_cost += c
            else:
                rg_untagged[(sub, rg.lower())] += c
        rgs_top = sorted(((v, s, g) for (s, g), v in rg_untagged.items()), reverse=True)[:10]
        allocation = {"tags": req, "total": r2(total_alloc), "all_tagged": r2(all_cost), "all_pct": pct(all_cost, total_alloc),
                      "untagged_pct": pct(total_alloc - all_cost, total_alloc), "not_resource": r2(not_res),
                      "per_tag": [{"tag": tg, "tagged": r2(per_tag[tg]), "pct": pct(per_tag[tg], total_alloc), "untagged": r2(total_alloc - per_tag[tg])} for tg in req],
                      "rgs": [{"rg": (raw["rgs"].get(s, {}).get(g) or {}).get("name") or g or t("sub_level"), "sub": names.get(s, s), "untagged": r2(v),
                               "share": pct(v, total_alloc)} for v, s, g in rgs_top]}
    # ---- projects
    det = raw.get("project_detection") or detect_project_key(raw, config, p)
    projects, project_of, rg_project = analyze_projects(raw, config, p, det, res_cost, res_svc, res_loc, names)
    for r in res_rows:
        r["project_id"], r["project"], r["project_source"] = project_of(r["id"])
    by_pid = {it["id"]: it for it in projects["items"]}
    for r in res_rows:
        item = by_pid.get(r["project_id"])
        if item is not None and len(item["top_resources"]) < 10:
            item["top_resources"].append(r)
    for s in savings.values():
        s["project_id"], s["project"], _ = project_of(s["id"])
        item = by_pid.get(s["project_id"])
        if item is not None:
            item["savings"] = r2(item["savings"] + s["saving"])
            item["savings_" + s["source"]] = r2(item["savings_" + s["source"]] + s["saving"])
    return {"currency": currency, "other_currency": other_currency, "names": names, "months": months, "monthly": monthly, "daily": daily,
            "unusual": unusual, "jumps": jumps, "new": new_items, "subs": sub_rows, "by_rg": by_rg, "by_service": by_service, "by_region": by_region,
            "resources": res_rows, "budgets": budgets, "no_budget": no_budget, "budget_total": r2(budget_total), "budget_forecast": r2(budget_fc),
            "budget_subs": sorted(budget_subs), "mg_budget": bool(mg_budget), "budget_cov": budget_cov, "savings": sorted(savings.values(), key=lambda x: -x["saving"]),
            "advisor": advisor, "commitment": commitment, "savings_total": r2(savings_total), "idle_saving": r2(idle_saving),
            "advisor_saving": r2(advisor_saving), "allocation": allocation, "projects": projects, "rg_project": rg_project,
            "totals": {"review": r2(review_total) if review_total is not None else None, "prev": r2(prev_total) if prev_total is not None else None,
                       "delta": r2(review_total - prev_total) if review_total is not None and prev_total is not None else None,
                       "pct": pct(review_total - prev_total, prev_total) if review_total is not None and prev_total else None,
                       "mtd": r2(mtd) if mtd is not None else None, "forecast": r2(forecast) if forecast is not None else None,
                       "run_rate": r2(run_rate) if run_rate is not None else None, "settled_days": k_days, "days_in_month": dim, "pace": pace},
            "have_cost": have_cost, "have_daily": have_daily,
            "data_through": max((d for d, v in d_total.items() if v > 0), default=None)}


# ------------------------- formatting (locale from TEXT) -------------------------
def fnum(value, decimals=2):
    s = f"{num(value):,.{decimals}f}"
    return s.replace(",", "\x00").replace(".", TEXT["_dec"]).replace("\x00", TEXT["_grp"])


def money(value, currency, decimals=2):
    return f"{fnum(value, decimals)}\u00a0{currency}" if value is not None else "\u2014"


def money_short(value, currency):
    return money(value, currency, 0 if value is not None and abs(num(value)) >= 100 else 2)


def fpct(value, signed=False, decimals=None):
    if value is None:
        return "\u2014"
    if abs(value) < 0.05:
        return TEXT["_pct"].format(v="0")
    d = decimals if decimals is not None else (1 if abs(value) < 10 else 0)
    body = fnum(abs(value), d)
    sign = ("+" if value > 0 else "\u2212" if value < 0 else "") if signed else ("\u2212" if value < 0 else "")
    return sign + TEXT["_pct"].format(v=body)


def fdate(value, short=False):
    d = value if isinstance(value, date) else parse_day(value)
    if not d:
        return ""
    return TEXT["_dayshort_fmt" if short else "_day_fmt"].format(d=d.day, mon=TEXT["_mon"][d.month - 1], y=d.year)


def fmonth(key, short=False):
    if not key or not re.fullmatch(r"\d{4}-\d{2}", key):
        return key or ""
    y, m = int(key[:4]), int(key[5:7])
    if short:
        return TEXT["_mon"][m - 1]
    return TEXT["_month_fmt"].format(month=TEXT["_months"][m - 1], y=y)


def grain_label(value):
    return TEXT.get("grain_" + str(value), str(value))


def impact_label(value):
    return TEXT.get("imp_" + str(value), str(value))


def fmonth_name(key):
    return TEXT["_months"][int(key[5:7]) - 1] if key and re.fullmatch(r"\d{4}-\d{2}", key) else key


# ------------------------- findings, actions and verdict -------------------------
def build_findings(a, raw, config, periods, coverage):
    cur = a["currency"]
    findings = []
    review, prev = periods["review_month"], periods["prev_month"]
    multi = len(a["subs"]) > 1
    mom_min = float(MOM_MIN_DELTA)

    def add(sev, cat, title, evidence, action, scope="", rid="", saving=None, link="", proj=("", "")):
        fid = hashlib.sha1("|".join((cat, title, scope, rid)).encode("utf-8")).hexdigest()[:8]
        findings.append({"id": fid, "severity": sev, "category": cat, "title": clean(title, 220), "evidence": clean(evidence, 400),
                         "action": clean(action, 300), "scope": clean(scope, 200), "resource_id": rid, "saving": r2(saving) if saving else None,
                         "link": link or (portal_link(rid) if rid and "(not-a-resource)" not in rid else ""),
                         "project_id": proj[0], "project": proj[1]})

    def rg_proj(item):
        return a["rg_project"].get((item.get("sub_id"), item.get("rg_key")), ("", ""))[:2] if item["kind"] == "rg" else ("", "")

    for b in a["budgets"]:
        if b["status"] == "ok":
            continue
        key, sev = {"over": ("f_budget_over", "critical"), "forecast_over": ("f_budget_forecast", "high"), "risk": ("f_budget_risk", "medium")}[b["status"]]
        if b["status"] == "risk" and (b["used_pct"] or 0) < 80:
            key = "f_budget_risk_fc"
        ev = t("f_budget_ev", spent=money(b["spent"], b["currency"]), fc=money(b["forecast"], b["currency"]) if b["forecast"] is not None else "\u2014",
               amount=money(b["amount"], b["currency"]), grain=grain_label(b["grain"]))
        add(sev, "budget", t(key, name=b["name"], pct=fpct(b["used_pct"])), ev, t("a_budget"), b["scope"], link=portal_link(b["scope_id"]) if b["scope_id"] else "")
    for s in a["no_budget"]:
        fc = s["forecast"] if s["forecast"] is not None else s["cost"] or 0
        add("medium" if fc >= mom_min else "low", "governance", t("f_nobudget", name=s["name"]), t("f_nobudget_ev", fc=money(fc, cur)),
            t("a_nobudget", amount=money(nice_ceiling(fc * 1.1), cur, 0)), s["name"], link=portal_link("/subscriptions/" + s["id"]))
    for u in a["unusual"]:
        drivers = ", ".join(f'{d["service"]} +{money(d["delta"], cur)}' for d in u["drivers"]) or "\u2014"
        add(u["severity"], "anomaly", t("f_day", d=fdate(u["date"])), t("f_day_ev", cost=money(u["cost"], cur), typ=money(u["typical"], cur),
            pct=fpct(u["pct"], True), drivers=t("ud_driver_l", v=drivers)), t("a_day", driver=u["drivers"][0]["service"] if u["drivers"] else t("top_services")))
    kind_name = {"service": t("kind_service"), "rg": t("kind_rg"), "sub": t("kind_sub")}
    for j in a["jumps"]:
        add(j["severity"], "anomaly", t("f_jump", kind=kind_name[j["kind"]], name=j["name"], pct=fpct(j["pct"], True)),
            t("f_jump_ev", prev=money(j["prev"], cur), pm=fmonth_name(prev), cost=money(j["cost"], cur), m=fmonth_name(review), delta="+" + money(j["delta"], cur)),
            t("a_jump", name=j["name"]), (j["scope"] if multi else "") or (t("scope_all") if j["kind"] == "service" else kind_name[j["kind"]]), proj=rg_proj(j))
    for n in a["new"]:
        add(n["severity"], "anomaly", t("f_new", kind_l=kind_name[n["kind"]].lower(), name=n["name"]),
            t("f_new_ev", cost=money(n["cost"], cur), m=fmonth_name(review)), t("a_new", name=n["name"]),
            (n["scope"] if multi else "") or (t("scope_all") if n["kind"] == "service" else kind_name[n["kind"]]), proj=rg_proj(n))
    for s in a["savings"]:
        sev = "high" if s["saving"] >= mom_min else "medium" if s["saving"] >= mom_min / 5 else "low" if s["saving"] > 0 else "info"
        where = " \u00b7 ".join(x for x in (s["rg"], s["sub"] if multi else "") if x)
        if s["source"] == "idle":
            title = t("f_idle", check=t("chk_" + s["check"]), name=s["name"])
            ev = " \u00b7 ".join(x for x in (s["type"], s["detail"], t("ev_monthly", v=money(s["cost"], cur)) if s["cost"] else t("no_cost")) if x)
            action = t("a_idle_" + s["check"])
        else:
            title = t("f_advisor", problem=s["problem"].rstrip("."), name=s["name"] or "\u2014")
            ev = " \u00b7 ".join(x for x in (s["type"], t("advisor_impact", v=impact_label(s["impact"])) if s["impact"] else "",
                                             t("ev_monthly", v=money(s["advisor_amount"], s["advisor_currency"])) if s["advisor_amount"] else "") if x)
            action = t("a_advisor")
        add(sev, "savings" if s["saving"] > 0 else "hygiene", title, ev, action, where, s["id"], s["saving"] or None,
            proj=(s.get("project_id", ""), s.get("project", "")))
    c = a["commitment"]
    on_demand = c["eligible"].get("OnDemand", 0.0)
    if on_demand >= mom_min and (c["coverage_pct"] or 0) < 50:
        best = t("commit_best", v=money(c["best_saving"], cur), t=t("term_1y")) if c["best_saving"] else ""
        add("high" if c["best_saving"] >= mom_min else "medium", "commitment", t("f_commit", pct=fpct(c["coverage_pct"] or 0)),
            t("f_commit_ev", od=money(on_demand, cur), m=fmonth_name(review), best=best), t("a_commit"), t("advisor_link"), "", c["best_saving"] or None,
            "https://portal.azure.com/#view/Microsoft_Azure_Expert/AdvisorMenuBlade/~/Cost")
    al = a["allocation"]
    if al and al["total"] and (al["untagged_pct"] or 0) >= 5:
        sev = "high" if al["untagged_pct"] >= 50 else "medium" if al["untagged_pct"] >= 20 else "low"
        tags = config["tags"]
        title = t("f_alloc", pct=fpct(al["untagged_pct"]), tag=tags[0]) if len(tags) == 1 else t("f_alloc_multi", pct=fpct(al["untagged_pct"]), tags=", ".join(tags))
        add(sev, "allocation", title, t("f_alloc_ev", v=money(al["total"] - al["all_tagged"], cur), total=money(al["total"], cur), m=fmonth_name(review)),
            t("a_alloc", rg=al["rgs"][0]["rg"] if al["rgs"] else "\u2014"))
    pj = a["projects"]
    if pj["total"] > 0:
        unalloc = r2(pj["total"] - pj["allocated"])
        rgs = ", ".join(g["rg"] for g in pj["unallocated_rgs"][:3]) or "\u2014"
        if pj["source"] == "none":
            add("medium" if (pj["allocated_pct"] or 0) < 50 else "low", "allocation", t("f_proj_none"),
                t("f_proj_none_ev", pct=fpct(100 - (pj["allocated_pct"] or 0)), m=fmonth_name(review)), t("a_proj_none"))
        elif (pj["allocated_pct"] or 0) < 80:
            add("medium" if (pj["allocated_pct"] or 0) < 50 else "low", "allocation", t("f_proj_low", pct=fpct(pj["allocated_pct"] or 0), tag=pj["key"]),
                t("f_proj_low_ev", v=money(unalloc, cur), total=money(pj["total"], cur), m=fmonth_name(review), rgs=rgs), t("a_proj_low", tag=pj["key"]))
    for src in coverage["sources"]:
        if src["status"] in ("partial", "denied", "error", "skipped"):
            msg = src["errors"][0]["message"] if src["errors"] else src.get("notes") or src["status"]
            sev = "low" if src.get("optional") else "high" if src["id"].startswith("cost_") and src["status"] != "partial" else "medium"
            add(sev, "data", t("f_cov", v=t(src["label"])), f"{t('st_' + src['status'])}: {clean(msg, 200)}", t("a_cov"))
    if raw.get("skipped_subs"):
        add("medium", "data", t("f_cov", v=t("f_skipped", n=len(raw["skipped_subs"]), max=MAX_SUBSCRIPTIONS)),
            ", ".join(raw["skipped_subs"][:5]), t("a_cov"))
    findings.sort(key=lambda f: (-SEV_RANK[f["severity"]], -(f["saving"] or 0), f["category"], f["title"]))
    return findings


def build_actions(findings, limit=8):
    picked = [f for f in findings if SEV_RANK[f["severity"]] >= SEV_RANK["medium"] or (f["saving"] or 0) > 0]
    return picked[:limit]


def build_verdict(a, findings, status):
    counts = {s: sum(1 for f in findings if f["severity"] == s) for s in SEVERITIES}
    if not a["have_cost"]:
        tone, word = "nodata", t("v_nodata")
    elif counts["critical"] or counts["high"]:
        tone, word = "action", t("v_action")
    elif counts["medium"]:
        tone, word = "review", t("v_review")
    else:
        tone, word = "ok", t("v_ok")
    parts = []
    if a["budget_cov"]["over"]:
        parts.append(tn("vd_budgets", a["budget_cov"]["over"]))
    elif a["no_budget"]:
        parts.append(tn("vd_nobudget", len(a["no_budget"])))
    if a["savings_total"] > 0:
        parts.append(t("vd_savings", v=money_short(a["savings_total"], a["currency"])))
    anomalies = len(a["unusual"]) + len(a["jumps"]) + len(a["new"])
    if anomalies:
        parts.append(tn("vd_anom", anomalies))
    if a["allocation"] and (a["allocation"]["untagged_pct"] or 0) >= 20:
        parts.append(t("vd_untagged", v=fpct(a["allocation"]["untagged_pct"])))
    return {"tone": tone, "label": word, "counts": counts, "partial": status != "ok", "detail": parts[:3]}


def build_lead(a, periods):
    tot, cur = a["totals"], a["currency"]
    if not a["have_cost"]:
        return t("lead_nodata")
    review, prev, current = periods["review_month"], periods["prev_month"], periods["current_month"]
    if tot["prev"]:
        change = t("lead_change_up" if tot["delta"] > 0.005 * tot["prev"] else "lead_change_down" if tot["delta"] < -0.005 * tot["prev"] else "lead_change_flat",
                   pct=fpct(abs(tot["pct"] or 0)))
    else:
        change = t("lead_change_none")
    nb = lambda v: money_short(v, cur).replace(" ", "\u00a0")
    text_value = t("lead_month", month=fmonth_name(review), cost=nb(tot["review"]), change=change, prev=fmonth_name(prev))
    bc = a["budget_cov"]
    if tot["forecast"] is not None:
        if a["budget_total"] and bc["full"]:
            text_value += t("lead_forecast_budget", month=fmonth_name(current), f=nb(tot["forecast"]), pct=fpct(pct(tot["forecast"], a["budget_total"])))
        elif bc["budgets"]:
            text_value += tn("lead_forecast_partial", bc["over"], month=fmonth_name(current), f=nb(tot["forecast"]), k=bc["budgets"])
        else:
            text_value += t("lead_forecast_nobudget", month=fmonth_name(current), f=nb(tot["forecast"]))
    n = sum(1 for s in a["savings"] if s["saving"] > 0) + len(a["commitment"]["items"][:1])
    text_value += tn("lead_savings", n, s=nb(a["savings_total"])) if a["savings_total"] > 0 else t("lead_savings_none")
    return text_value


def plain(html_text):
    return html.unescape(re.sub(r"<[^>]+>", "", html_text)).replace("\u00a0", " ")


def build_snapshot(raw, config, periods, now, stats, provenance="LIVE"):
    a = analyze(raw, config, periods, now)
    sources = [s for s in raw["receipts"]]
    core_failed = not a["have_cost"]
    status = ("error" if core_failed else "ok" if all(s["status"] in ("complete", "not_configured") or s.get("optional") for s in sources) and not raw["skipped_subs"]
              and not a["other_currency"] and not raw["invisible_subs"] else "partial")
    coverage = {"status": status, "sources": sources, "requests": stats.get("requests", 0), "throttled": stats.get("throttled", 0),
                "waited": round(stats.get("waited", 0.0), 1), "seconds": stats.get("seconds", 0.0), "identity": stats.get("identity", ""),
                "skipped_subscriptions": raw["skipped_subs"], "invisible_subscriptions": raw["invisible_subs"],
                "other_currency_subscriptions": [a["names"].get(s, s) for s in a["other_currency"]]}
    findings = build_findings(a, raw, config, periods, coverage)
    actions = build_actions(findings)
    verdict = build_verdict(a, findings, status)
    lead = build_lead(a, periods)
    projects = a["projects"]
    for item in projects["items"]:
        mine = [f for f in findings if f["project_id"] == item["id"]]
        item["findings"] = len(mine)
        item["actions"] = [f["id"] for f in build_actions(mine)]
    per = {k: (v.isoformat() if isinstance(v, date) else v) for k, v in periods.items()}
    per["data_through"] = a["data_through"].isoformat() if a["data_through"] else None
    return {"tool": TOOL_NAME, "version": TOOL_VERSION, "generated_utc": iso(now), "provenance": provenance, "status": status,
            "client_name": config["client_name"], "language": TEXT["_lang"], "metric": config["metric"], "currency": a["currency"],
            "scope": {"management_group": config["management_group"], "subscriptions": [{"id": s["id"], "name": s["name"], "read": s["read"]} for s in a["subs"]]},
            "periods": per, "totals": a["totals"], "monthly": a["monthly"], "daily": a["daily"], "unusual": a["unusual"], "jumps": a["jumps"],
            "new": a["new"], "subscriptions": a["subs"], "resource_groups": a["by_rg"][:200], "services": a["by_service"][:200],
            "regions": a["by_region"], "resources": a["resources"], "resources_total": len(a["resources"]),
            "budgets": a["budgets"], "no_budget": [{"id": s["id"], "name": s["name"], "forecast": s["forecast"]} for s in a["no_budget"]],
            "budget_total": a["budget_total"], "budget_forecast": a["budget_forecast"], "budget_cov": a["budget_cov"],
            "savings": {"total": a["savings_total"], "idle": a["idle_saving"], "advisor": a["advisor_saving"], "commitments": a["commitment"]["best_saving"],
                        "items": a["savings"]}, "commitment": a["commitment"], "allocation": a["allocation"], "projects": projects,
            "findings": findings, "actions": actions, "verdict": verdict, "headline": {"html": lead, "text": plain(lead)},
            "coverage": coverage, "config": {"tags": config["tags"], "inheritance": config["inheritance"], "anomaly_min_daily_delta": ANOMALY_MIN_DAILY_DELTA,
                                             "mom_min_delta": MOM_MIN_DELTA, "trend_months": TREND_MONTHS, "snapshot_max_age_days": SNAPSHOT_MAX_AGE_DAYS,
                                             "excluded_resource_groups": [p_.pattern[4:] for p_ in config["rg_patterns"]],
                                             "project_tag_keys": list(config.get("project_keys") or []),
                                             "project_rg_rules": [[rx.pattern[4:], name] for rx, name in config.get("project_rules") or []]}}


# ------------------------- chat views (operation=query) -------------------------
def response_bytes(value):
    return len(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


def compact_finding(f, evidence=180):
    out = {"severity": f["severity"], "category": f["category"], "title": f["title"], "evidence": f["evidence"][:evidence]}
    if f["saving"]:
        out["saving_month"] = f["saving"]
    if f["scope"]:
        out["scope"] = f["scope"][:80]
    return out


def project_kpis(snapshot):
    pj = snapshot.get("projects") or {}
    named = [it for it in pj.get("items", []) if not it["unallocated"]]
    return {"tag": pj.get("key") or None, "source": pj.get("source"), "allocated_pct": round(pj["allocated_pct"], 1) if pj.get("allocated_pct") is not None else None,
            "count": len(named), "top": [{"name": it["name"][:40], "cost": it["cost"], "share_pct": round(it["share"], 1) if it["share"] is not None else None}
                                         for it in named[:3]]}


def kpis(snapshot):
    tot, cur = snapshot["totals"], snapshot["currency"]
    al = snapshot["allocation"]
    return {"currency": cur, "review_month": snapshot["periods"]["review_month"], "review_cost": tot["review"], "previous_cost": tot["prev"],
            "change_pct": round(tot["pct"], 1) if tot["pct"] is not None else None, "month_to_date": tot["mtd"], "forecast": tot["forecast"],
            "budget": snapshot["budget_total"] or None, "savings_month": snapshot["savings"]["total"],
            "untagged_pct": round(al["untagged_pct"], 1) if al and al["untagged_pct"] is not None else None,
            "unusual_days": len(snapshot["unusual"]), "jumps": len(snapshot["jumps"]), "new": len(snapshot["new"]), "projects": project_kpis(snapshot)}


def compact_coverage(snapshot):
    issues = [f"{s['id']}: {s['status']}" + (f" ({clean(s['errors'][0]['message'], 90)})" if s["errors"] else "")
              for s in snapshot["coverage"]["sources"] if s["status"] in ("partial", "denied", "error", "skipped") and not s.get("optional")]
    return {"status": snapshot["coverage"]["status"], "subscriptions": len(snapshot["scope"]["subscriptions"]),
            "throttled": snapshot["coverage"]["throttled"], "issues": issues[:3]}


def find_project(snapshot, name):
    """The project item named `name` (case-insensitive; 'unallocated' also matches the Unallocated group)."""
    items = (snapshot.get("projects") or {}).get("items", [])
    key = re.sub(r"\s+", " ", name).strip().casefold()
    for it in items:
        if it["name"].casefold() == key or (it["unallocated"] and key in ("unallocated", t("proj_unallocated").casefold())):
            return it
    known = ", ".join(it["name"] for it in items[:12]) or "none"
    raise FinOpsError("unknown_project", f"No project is named '{clean(name, 64)}'. Projects in this review: {known}.", "parameters")


def query_view(snapshot, params):
    view, limit = params["view"], params["limit"]
    cur = snapshot["currency"]
    item = find_project(snapshot, params["project"]) if params.get("project") else None
    pid = item["id"] if item else None
    findings = [f for f in snapshot["findings"] if f.get("project_id") == pid] if item else None
    actions = [f for f in findings if f["id"] in item["actions"]] if item else snapshot["actions"]
    if view == "summary":
        rows = [compact_finding(f) for f in actions[:limit]]
    elif view == "actions":
        rows = [dict(compact_finding(f, 110), action=f["action"][:120]) for f in actions[:limit]]
    elif view == "anomalies":
        rows = ([{"kind": "unusual_day", "date": u["date"], "cost": u["cost"], "typical": u["typical"], "pct": round(u["pct"], 1),
                  "drivers": [d["service"] for d in u["drivers"]]} for u in snapshot["unusual"]] +
                [{"kind": "jump", "of": j["kind"], "name": j["name"], "prev": j["prev"], "cost": j["cost"], "pct": round(j["pct"], 1)} for j in snapshot["jumps"]] +
                [{"kind": "new", "of": n["kind"], "name": n["name"], "cost": n["cost"]} for n in snapshot["new"]])[:limit]
    elif view == "budgets":
        rows = ([{"budget": b["name"], "scope": b["scope"], "amount": b["amount"], "spent": b["spent"], "forecast": b["forecast"], "status": b["status"]}
                 for b in snapshot["budgets"]] + [{"no_budget": s["name"], "forecast": s["forecast"]} for s in snapshot["no_budget"]])[:limit]
    elif view == "savings":
        rows = [{"check": s["check"], "name": s["name"], "rg": s["rg"], "saving_month": s["saving"]} for s in snapshot["savings"]["items"]
                if s["saving"] > 0 and (pid is None or s.get("project_id") == pid)][:limit]
        if pid is None:
            rows += [{"commitment": c["sku"], "region": c["region"], "term": c["term"], "saving_month": c["saving"]} for c in snapshot["commitment"]["items"]][:max(0, limit - len(rows))]
    elif view == "resources":
        rows = [{"name": r["name"], "rg": r["rg"], "type": r["type"], "cost": r["cost"], "prev": r["prev"]} for r in snapshot["resources"]
                if pid is None or r.get("project_id") == pid][:limit]
    elif view == "projects":
        if item:
            rows = ([{"service": x["name"], "cost": x["cost"], "prev": x["prev"]} for x in item["by_service"][:5]] +
                    [{"rg": x["name"], "cost": x["cost"], "prev": x["prev"]} for x in item["by_rg"][:5]] +
                    [{"resource": r["name"], "rg": r["rg"], "cost": r["cost"]} for r in item["top_resources"][:5]])[:limit]
        else:
            rows = [{"project": it["name"], "cost": it["cost"], "prev": it["prev"], "change_pct": round(it["pct"], 1) if it["pct"] is not None else None,
                     "mtd": it["mtd"], "share_pct": round(it["share"], 1) if it["share"] is not None else None, "savings_month": it["savings"],
                     "findings": it["findings"]} for it in snapshot["projects"]["items"]][:limit]
    elif view == "allocation":
        al = snapshot["allocation"] or {}
        rows = [{"tag": p_["tag"], "tagged_pct": round(p_["pct"] or 0, 1), "untagged": p_["untagged"]} for p_ in al.get("per_tag", [])]
        rows += [{"rg": g["rg"], "sub": g["sub"], "untagged": g["untagged"]} for g in al.get("rgs", [])][:max(0, limit - len(rows))]
    else:
        rows = [{"source": s["id"], "status": s["status"], "records": s["records"], "error": s["errors"][0]["message"][:120] if s["errors"] else ""}
                for s in snapshot["coverage"]["sources"]][:limit]
    out = {"status": snapshot["status"], "operation": "query", "view": view, "provenance": snapshot["provenance"], "kpis": kpis(snapshot),
           "headline": snapshot["headline"]["text"][:400], "rows": rows, "row_count": len(rows), "currency": cur, "coverage": compact_coverage(snapshot),
           "read_only": True}
    if view not in ("summary", "projects"):
        kp = out["kpis"]
        out["kpis"] = {k: kp[k] for k in ("currency", "review_month", "review_cost", "change_pct", "forecast", "savings_month")}
        out["kpis"]["projects"] = {k: kp["projects"][k] for k in ("tag", "allocated_pct")}
    if item:
        out["project"] = {"name": item["name"], "cost": item["cost"], "prev": item["prev"], "mtd": item["mtd"],
                          "share_pct": round(item["share"], 1) if item["share"] is not None else None, "savings_month": item["savings"], "findings": item["findings"]}
        if view in ("anomalies", "budgets", "allocation", "coverage"):
            out["project_scope"] = "whole_environment"
    while out["rows"] and response_bytes(out) > TRANSPORT_BYTES:
        out["rows"].pop()
        out["transport_capped"] = True
    out["row_count"] = len(out["rows"])
    return out


# ------------------------- offline HTML report -------------------------
REPORT_CSP = "default-src 'none'; img-src data:; font-src data:; style-src 'unsafe-inline'; script-src 'unsafe-inline'; base-uri 'none'; form-action 'none'"
# @@BRAND-BEGIN@@
BRAND_CSS = (":root{--bar:#111A22;--bar-ink:#fff;--bar-muted:#AEBBC6;--bar-line:#33414C;--hero1:#174B5C;--hero2:#0E3642;--hmuted:#C4D8DE;"
             "--hline:rgba(255,255,255,.17);--accent:#0B6E80;--accent2:#08586A;--accent-soft:#E3F1F3;--accent-on-dark:#8FD3DF;--chart:#2D6B7B;"
             "--chart-soft:#A9C9D1;--font:\"Segoe UI\",system-ui,-apple-system,\"Helvetica Neue\",Roboto,Arial,sans-serif}")
# @@BRAND-END@@
REPORT_CSS = """
:root{--ink:#101828;--text:#1D2939;--muted:#475467;--faint:#667085;--line:#E4E7EC;--line2:#EEF1F4;--paper:#F2F4F7;--soft:#F7F9FA;
--up:#B42318;--down:#067647;--crit:#B42318;--crit-bg:#FEE4E2;--crit-bar:#D92D20;--high:#B93815;--high-bg:#FFEAD5;--high-bar:#EF6820;
--medium:#93370D;--medium-bg:#FEF0C7;--medium-bar:#F79009;--low:#175CD3;--low-bg:#D1E9FF;--low-bar:#2E90FA;--info:#344054;--info-bg:#EAECF0;--info-bar:#98A2B3;
--shadow:0 1px 2px rgba(16,24,40,.05),0 8px 24px rgba(16,24,40,.06)}
*{box-sizing:border-box}html{scroll-behavior:smooth;scroll-padding-top:64px;scrollbar-color:#C3CCD6 var(--paper);-webkit-text-size-adjust:100%}
body{margin:0;background:var(--paper);color:var(--text);font:15px/1.5 var(--font);font-variant-numeric:tabular-nums}
::selection{background:#C9E5EA;color:var(--ink)}a{color:var(--accent);text-underline-offset:3px}a:hover{color:var(--accent2)}
button,input,select{font:inherit;color:inherit}:focus-visible{outline:3px solid var(--accent);outline-offset:2px}.top :focus-visible,.hero :focus-visible{outline-color:var(--accent-on-dark)}
.vh{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}
.skip{position:absolute;left:12px;top:-80px;z-index:50;background:#fff;color:var(--ink);padding:8px 14px;border-radius:8px;font-weight:600}.skip:focus{top:10px}
.wrap{max-width:1320px;margin:0 auto;padding:0 clamp(16px,3.6vw,40px)}.nw{white-space:nowrap}code{font-family:"Cascadia Mono",Consolas,monospace;font-size:13px}
.top{background:var(--bar);color:var(--bar-ink);border-bottom:1px solid var(--bar-line)}.top .wrap{display:flex;align-items:center;gap:16px;min-height:60px}
.wm{display:inline-flex;align-items:center;gap:10px;font-weight:600;font-size:17px;white-space:nowrap;color:var(--bar-ink)}
.wm svg{width:30px;height:30px;padding:5px;border-radius:8px;background:var(--accent);flex:none}
img.logo{height:36px;width:auto;max-width:200px;display:block}.tt{color:var(--bar-muted);font-size:14px;padding-left:16px;border-left:1px solid var(--bar-line);white-space:nowrap}
.acts-top{margin-left:auto;display:flex;align-items:center;gap:10px}.chip{font-size:12.5px;font-weight:600;color:var(--bar-muted);border:1px solid var(--bar-line);border-radius:999px;padding:4px 11px;white-space:nowrap}
.pbtn{display:inline-flex;align-items:center;gap:8px;min-height:38px;padding:0 15px;border:0;border-radius:9px;background:var(--accent);color:#fff;font-weight:600;font-size:14px;cursor:pointer;white-space:nowrap;transition:background-color .15s}
.pbtn:hover{background:var(--accent2)}.pbtn svg{width:16px;height:16px;flex:none}
.hero{background:linear-gradient(180deg,var(--hero1),var(--hero2));color:#fff;padding:clamp(28px,4vw,46px) 0 104px}
.hero-in{display:grid;grid-template-columns:minmax(0,1fr) 340px;gap:24px 48px;align-items:start}
h1{margin:0 0 14px;font-size:clamp(30px,3.2vw,42px);line-height:1.1;font-weight:700;letter-spacing:-.015em;text-wrap:balance}h1,.sh h2,.verdict b{font-family:var(--display,var(--font))}
.lead{margin:0;max-width:64ch;font-size:17.5px;line-height:1.5;color:var(--hmuted);text-wrap:pretty}.lead b{color:#fff;font-weight:600}
.meta{display:flex;flex-wrap:wrap;gap:8px;margin-top:20px}.meta span{font-size:12.5px;padding:5px 11px;border-radius:999px;border:1px solid var(--hline);color:var(--hmuted)}
.meta b{color:#fff;font-weight:600}.meta .warn{color:#FEC84B;border-color:rgba(254,200,75,.5);font-weight:600}.meta .sim{color:#FEC84B;border-color:rgba(254,200,75,.5);font-weight:700}
.verdict{border-radius:16px;padding:20px 22px;background:rgba(255,255,255,.07);border:1px solid var(--hline)}.verdict .k{font-size:13px;font-weight:600;color:var(--hmuted)}
.verdict b{display:block;margin-top:2px;font-size:28px;line-height:1.15;font-weight:700}.verdict p{margin:8px 0 0;font-size:14px;color:var(--hmuted)}
.v-action{border-color:rgba(253,176,34,.5)}.v-action b{color:#FDB022}.v-review b{color:#FEDF89}.v-ok{border-color:rgba(117,224,167,.45)}.v-ok b{color:#75E0A7}.v-nodata b{color:#FDA29B}
.verdict p.cov{display:flex;gap:8px;padding-top:12px;margin-top:14px;border-top:1px solid var(--hline);color:#FEDF89}.verdict p.cov svg{width:16px;height:16px;flex:none;margin-top:2px}
.dist{grid-column:1/-1}.dist-h{font-size:13.5px;color:var(--hmuted);margin-bottom:8px}.dist-h b{color:#fff}
.track{display:flex;gap:2px;height:12px;border-radius:999px;overflow:hidden;background:rgba(255,255,255,.12)}.track i{display:block;height:100%}
.legend{display:flex;flex-wrap:wrap;gap:6px 18px;margin-top:10px;font-size:13.5px;color:var(--hmuted)}.legend span{display:inline-flex;align-items:center;gap:7px}
.legend i{width:10px;height:10px;border-radius:3px}.legend b{color:#fff}
.b-critical{background:var(--crit-bar)}.b-high{background:var(--high-bar)}.b-medium{background:var(--medium-bar)}.b-low{background:var(--low-bar)}.b-info{background:var(--info-bar)}
.kpis{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:14px;margin-top:-72px;position:relative;z-index:2}
.kpi{background:#fff;border:1px solid var(--line);border-radius:16px;padding:16px 18px;box-shadow:var(--shadow);min-width:0}
.kpi .v{font-size:31px;line-height:1.08;font-weight:700;letter-spacing:-.02em;color:var(--ink);white-space:nowrap}.kpi .v small{font-size:14px;font-weight:600;color:var(--muted);letter-spacing:0;margin-left:4px}
.kpi .l{margin-top:8px;font-size:13.5px;line-height:1.35;font-weight:600;color:var(--ink)}.kpi .s{margin-top:4px;font-size:12.5px;line-height:1.4;color:var(--muted)}
.up{color:var(--up);font-weight:600}.down{color:var(--down);font-weight:600}.flat{color:var(--muted)}
.secnav{position:sticky;top:0;z-index:20;background:var(--paper);border-bottom:1px solid var(--line);margin-top:22px}
.secnav .wrap{display:flex;align-items:center;gap:10px}.secnav .links{display:flex;gap:2px;overflow-x:auto;scrollbar-width:none;min-width:0;flex:1 1 auto}.secnav .links::-webkit-scrollbar{display:none}.secnav .links.ovf{padding-right:40px;-webkit-mask-image:linear-gradient(90deg,#000 calc(100% - 44px),transparent);mask-image:linear-gradient(90deg,#000 calc(100% - 44px),transparent)}
.secnav a{white-space:nowrap;text-decoration:none;color:var(--muted);font-size:13px;font-weight:600;padding:12px 9px 10px;border-bottom:2px solid transparent}
.secnav a:hover,.secnav a.on{color:var(--ink);border-bottom-color:var(--accent)}.secnav a:focus-visible{outline-offset:-3px;border-radius:6px}.secnav a small{color:var(--faint);font-size:12px;margin-left:5px;font-weight:600}
.body{padding-top:30px;padding-bottom:40px}.sec{margin:0 0 44px;scroll-margin-top:60px}.sh{margin:0 0 14px}.sh h2{margin:0;font-size:23px;line-height:1.2;letter-spacing:-.01em;color:var(--ink)}
.sh p{margin:5px 0 0;color:var(--muted);max-width:68ch;font-size:14.5px}
.card{background:#fff;border:1px solid var(--line);border-radius:16px;padding:20px 22px;box-shadow:var(--shadow);min-width:0}
.card h3{margin:0 0 3px;font-size:16.5px;color:var(--ink)}.card .sub,.a-ev,.a-do,.note span,ul.plain li{max-width:72ch}.card h3.h3b{margin-top:24px;padding-top:18px;border-top:1px solid var(--line2)}.card .sub{margin:0 0 14px;font-size:13.5px;color:var(--muted);max-width:78ch}
.g2{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}.g2w{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1.55fr);gap:16px}
.stack{display:grid;gap:16px}.mt{margin-top:16px}.g2s{align-items:start}
.sev{display:inline-block;border-radius:6px;padding:0 8px;font-size:12px;font-weight:700;line-height:22px;white-space:nowrap}
.sev-critical{color:var(--crit);background:var(--crit-bg)}.sev-high{color:var(--high);background:var(--high-bg)}.sev-medium{color:var(--medium);background:var(--medium-bg)}
.sev-low{color:var(--low);background:var(--low-bg)}.sev-info{color:var(--info);background:var(--info-bg)}
.tag{display:inline-block;border:1px solid var(--line);border-radius:6px;padding:0 7px;font-size:12px;line-height:20px;color:#344054;background:var(--soft);white-space:nowrap}
.tag.new{border-color:#A6D8E0;background:var(--accent-soft);color:var(--accent2);font-weight:700}
ol.actions{list-style:none;margin:0;padding:0;counter-reset:a}ol.actions li{counter-increment:a;display:grid;grid-template-columns:34px minmax(0,1fr) 250px;gap:6px 16px;padding:16px 0;border-top:1px solid var(--line2)}
ol.actions li:first-child{border-top:0;padding-top:4px}ol.actions li:before{content:counter(a);width:28px;height:28px;border-radius:50%;background:var(--soft);border:1px solid var(--line);display:grid;place-items:center;font-weight:700;font-size:13px;color:var(--ink)}
.a-t{display:flex;flex-wrap:wrap;align-items:center;gap:6px 10px}.a-t b{font-size:15.5px;color:var(--ink);font-weight:600}
.a-ev{margin:4px 0 0;color:var(--muted);font-size:14px;max-width:80ch}.a-do{margin:4px 0 0;font-size:14px;max-width:80ch}
.a-side{text-align:right}.a-sv{display:block;font-size:19px;font-weight:700;color:var(--ink);white-space:nowrap}.a-sv small{font-size:12.5px;color:var(--muted);font-weight:600}
.a-wh{display:block;margin-top:4px;font-size:13px;color:var(--muted);overflow-wrap:anywhere}.a-ln{display:inline-flex;align-items:center;gap:5px;margin-top:6px;font-size:13px;font-weight:600;padding:3px 0}
.a-ln svg,.pl svg{width:13px;height:13px;flex:none}.a-t b,.ud b,#reg td>b,.rn b{overflow-wrap:anywhere;min-width:0}
.mc{display:grid;grid-template-columns:repeat(var(--n),minmax(0,1fr));gap:10px;align-items:end;height:250px;padding-top:6px}
.mcol{display:flex;flex-direction:column;justify-content:flex-end;height:100%;min-width:0;text-align:center}
.mv{font-size:12.5px;font-weight:700;color:var(--ink);white-space:nowrap;margin-bottom:4px}.mv small{display:block;font-weight:600;color:var(--muted);font-size:12px}
.mtrack{position:relative;flex:none;height:var(--h);min-height:2px;margin:0 14%}.mtrack i{position:absolute;left:0;right:0;bottom:0;border-radius:5px 5px 0 0;background:var(--chart)}
.mcol.review .mtrack i{background:var(--accent2)}.mcol.partial .mtrack i.mb{background:repeating-linear-gradient(135deg,var(--chart) 0 6px,var(--chart-soft) 6px 9px)}
.mtrack i.fc{background:none;border:2px dashed var(--chart);border-bottom:0}.mcol.zero .mtrack i{background:var(--line)}
.mx{display:grid;grid-template-columns:repeat(var(--n),minmax(0,1fr));gap:10px;border-top:1px solid #C6CFD8;margin-top:0;padding-top:6px;font-size:12.5px;color:var(--muted);text-align:center}
.mx b{display:block;color:var(--ink);font-weight:600}.mx .rv b{color:var(--accent2)}.mx .up,.mx .down{font-size:12px}.mx .small{display:block;line-height:1.25}
.dc{position:relative;height:230px;margin:10px 0 0 46px}.dgrid{position:absolute;inset:0;pointer-events:none}
.dgrid span{position:absolute;left:-46px;right:0;border-top:1px dashed #DCE2E8;font-size:12px;color:var(--faint);line-height:0}.dgrid span em{position:relative;top:-1px;font-style:normal;background:#fff;padding-right:6px}
.dbars{position:absolute;inset:0;display:grid;grid-template-columns:repeat(var(--n),minmax(0,1fr));align-items:end;gap:2px}
.db{display:block;background:var(--chart);border-radius:2px 2px 0 0;min-height:1px}.db.pre{background:var(--chart-soft)}.db.unsettled,.dleg i.hatch{background:repeating-linear-gradient(135deg,var(--chart) 0 3px,#DCE7EA 3px 6px)}
.dband{position:absolute;top:-2px;bottom:0;background:rgba(43,107,123,.07);border-radius:6px 6px 0 0;pointer-events:none}.dband span{position:absolute;top:4px;left:8px;font-size:12px;font-weight:700;color:var(--chart);letter-spacing:.02em}
.db.high{background:var(--high-bar)}.db.medium{background:var(--medium-bar)}
svg.dtyp{position:absolute;inset:0;width:100%;height:100%;overflow:visible;pointer-events:none}svg.dtyp polyline{fill:none;stroke:var(--ink);stroke-width:1.6;stroke-dasharray:5 4;opacity:.75}
.dlab{position:absolute;transform:translate(-50%,-100%);margin-top:-4px;font-size:12px;font-weight:700;color:var(--high);background:#fff;padding:0 3px;border-radius:3px;white-space:nowrap}
.dlab.medium{color:var(--medium)}.dx{position:relative;height:22px;margin-left:46px;border-top:1px solid #C6CFD8;font-size:12px;color:var(--muted)}
.dx span{position:absolute;top:4px;transform:translateX(-50%);white-space:nowrap}.dleg{display:flex;flex-wrap:wrap;gap:6px 18px;margin-top:6px;font-size:12.5px;color:var(--muted)}
.dleg span{display:inline-flex;align-items:center;gap:7px}.dleg i{width:12px;height:10px;border-radius:2px;display:inline-block}.dleg i.ln{height:0;border-top:2px dashed var(--ink);opacity:.75}
.hb{display:grid;grid-template-columns:minmax(0,1.25fr) minmax(60px,1fr) 14ch 74px;gap:6px 12px;align-items:center;padding:7px 0;border-top:1px solid var(--line2);font-size:14px}
.hb:first-of-type{border-top:0}.hb .n1{min-width:0;overflow-wrap:anywhere}.hb .n1 small{display:block;color:var(--muted);font-size:12px}
.hb .t{height:10px;border-radius:999px;background:#EAECF0;overflow:hidden}.hb .t i{display:block;height:100%;border-radius:999px;background:var(--chart)}
.hb .v{text-align:right;font-weight:700;color:var(--ink);white-space:nowrap}.hb .d{text-align:right;font-size:12.5px;white-space:nowrap}.hb.oth .n1{color:var(--muted)}
.tw{overflow-x:auto;background:linear-gradient(90deg,#fff 30%,rgba(255,255,255,0)) left/36px 100% no-repeat local,linear-gradient(270deg,#fff 30%,rgba(255,255,255,0)) right/36px 100% no-repeat local,radial-gradient(farthest-side at 0 50%,rgba(16,24,40,.16),rgba(16,24,40,0)) left/14px 100% no-repeat scroll,radial-gradient(farthest-side at 100% 50%,rgba(16,24,40,.16),rgba(16,24,40,0)) right/14px 100% no-repeat scroll}
table{width:100%;border-collapse:collapse;font-size:14px}th,td{padding:9px 12px;border-bottom:1px solid var(--line2);text-align:left;vertical-align:top}
thead th{background:var(--soft);font-size:12px;letter-spacing:.04em;text-transform:uppercase;color:var(--ink);white-space:nowrap;border-bottom:1px solid var(--line)}
tbody tr:last-child>*{border-bottom:0}td.n,th.n{text-align:right;white-space:nowrap}.muted{color:var(--muted)}.small{font-size:12.5px}
.rn b{color:var(--ink);font-weight:600;overflow-wrap:anywhere}.rn small{display:block;color:var(--muted);font-size:12.5px;overflow-wrap:anywhere}
a.pl{display:inline-flex;align-items:center;gap:4px;font-size:12.5px;font-weight:600;text-decoration:none;white-space:nowrap;padding:4px 2px;margin-left:2px}a.pl:hover{text-decoration:underline}
a.pl.blk{display:flex;margin:4px 0 0;padding:3px 0}ul.plain a{display:inline-block;padding:2px 0}.linkbtn{border:0;background:none;color:var(--accent);font:inherit;font-weight:600;cursor:pointer;padding:4px;text-decoration:underline}
.pl-only{display:none}#reg col.w1{width:110px}#reg col.w2{width:120px}#reg col.w4{width:230px}#reg col.w5{width:130px}
.empty{color:var(--muted);background:var(--soft);border:1px dashed var(--line);border-radius:12px;padding:14px 16px;font-size:14px}
.mtr{height:8px;border-radius:999px;background:#EAECF0;overflow:hidden;min-width:90px;margin-top:5px}.mtr i{display:block;height:100%;border-radius:999px;background:var(--chart)}
.mtr i.w{background:var(--medium-bar)}.mtr i.x{background:var(--crit-bar)}
.ud{list-style:none;margin:0;padding:0}.ud li{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:2px 12px;padding:11px 0;border-top:1px solid var(--line2)}.ud li:first-child{border-top:0;padding-top:2px}
.ud b{color:var(--ink)}.ud .r{text-align:right;white-space:nowrap}.ud .x{grid-column:1/-1;color:var(--muted);font-size:13.5px}
.svs{display:grid;grid-template-columns:1.3fr repeat(3,minmax(0,1fr));gap:12px;margin-bottom:16px}.svs div{background:#fff;border:1px solid var(--line);border-radius:14px;padding:14px 16px;box-shadow:var(--shadow)}
.svs b{display:block;font-size:24px;line-height:1.1;color:var(--ink)}.svs span{display:block;font-size:13px;color:var(--muted);margin-top:4px}.svs .tot{background:var(--accent-soft);border-color:#B9DCE2}.svs .tot b{font-size:30px;color:var(--accent2)}
.svs.s3{grid-template-columns:1.3fr repeat(2,minmax(0,1fr))}.svs b>span{display:inline;margin:0;font-size:inherit;color:var(--muted)}.svs b>.up{color:var(--up)}.svs b>.down{color:var(--down)}.svs b>.tag.new{font-size:13px;color:var(--accent2);vertical-align:4px}
.pm{display:flex;height:14px;border-radius:999px;overflow:hidden;background:#EAECF0;margin:10px 0 8px}.pm i{display:block;height:100%}
.pm-OnDemand{background:#98A2B3}.pm-Reservation{background:var(--chart)}.pm-SavingsPlan{background:var(--accent)}.pm-Spot{background:var(--chart-soft)}
.note{display:flex;gap:10px;align-items:flex-start;margin:14px 0 0;padding:11px 14px;border-radius:12px;background:var(--soft);border:1px solid var(--line);font-size:13.5px;color:var(--text)}
.note svg{width:17px;height:17px;flex:none;margin-top:2px;color:var(--accent)}.note.warn{background:#FFFAEB;border-color:#FEDF89;color:#7A2E0E}.note.warn svg{color:#B54708}
.filters{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin:0 0 12px}.filters input,.filters select{border:1px solid #C3CCD6;border-radius:9px;padding:8px 10px;font-size:14px;background:#fff;color:var(--text)}
.filters input{min-width:300px}.filters input::placeholder{color:var(--faint);opacity:1}.btn{border:1px solid #C3CCD6;background:#fff;border-radius:999px;padding:7px 14px;font-size:13.5px;font-weight:600;cursor:pointer;color:var(--ink)}
.btn:hover{background:var(--soft)}.fcount{margin-left:auto;color:var(--muted);font-size:13px}
.sb{font:inherit;color:inherit;letter-spacing:inherit;text-transform:inherit;background:none;border:0;padding:0;cursor:pointer;white-space:nowrap}.sb:hover{color:var(--accent2)}
th[aria-sort] .sb:after{content:"";display:inline-block;width:8px;height:5px;margin-left:6px;vertical-align:2px;background:currentColor;clip-path:polygon(0 0,100% 0,50% 100%)}
th[aria-sort=ascending] .sb:after{clip-path:polygon(50% 0,100% 100%,0 100%)}
#reg{table-layout:fixed;min-width:960px}#reg td{font-size:13.5px}#reg .ev{color:var(--muted);font-size:13px;margin-top:2px}#reg .do{font-size:13px;margin-top:3px}
.f-hide,.pg{display:none}.more{margin-top:10px;text-align:center}.morerow td{text-align:center;padding:12px}
.st{display:inline-block;border-radius:6px;padding:0 8px;font-size:12px;font-weight:700;line-height:21px;white-space:nowrap}
.st-complete{background:#DCFAE6;color:#085D3A}.st-partial,.st-skipped{background:#FEF0C7;color:#93370D}.st-denied,.st-error{background:#FEE4E2;color:#B42318}.st-not_configured,.st-simulated{background:#EAECF0;color:#344054}
ul.plain{margin:0;padding-left:18px}ul.plain li{margin:4px 0;max-width:90ch}
.pf{display:flex;align-items:center;gap:8px;flex:none;padding:5px 12px 5px 0;border-right:1px solid var(--line)}.pf label{font-size:12.5px;font-weight:600;color:var(--muted);white-space:nowrap}
.pf select{border:1px solid #C3CCD6;border-radius:9px;padding:5px 8px;font-size:13.5px;font-weight:600;background:#fff;color:var(--ink);max-width:220px;min-height:34px;cursor:pointer}
.pf.on select{border-color:var(--accent);box-shadow:inset 0 0 0 1px var(--accent);background:var(--accent-soft)}
.pfi{display:flex;flex-wrap:wrap;align-items:center;gap:8px 16px;margin:0 0 26px;padding:12px 16px;border-radius:14px;background:var(--accent-soft);border:1px solid var(--chart-soft);font-size:14px;color:var(--ink)}
.pfi p{margin:0;flex:1 1 420px}.pfi p span{display:block;margin-top:2px;color:var(--muted);font-size:13px}.pfi b{font-weight:700}.card p.lvh{margin:14px 0 0}
.pv[hidden],.pnote[hidden],.pchip[hidden]{display:none!important}
.pchip,.pnote{display:inline-flex;align-items:center;gap:6px;margin-top:9px;padding:3px 11px;border-radius:999px;font-size:12.5px;font-weight:600;line-height:1.45}
.pchip{background:var(--accent-soft);color:var(--accent2);border:1px solid var(--chart-soft)}.pchip b{color:var(--ink)}.pnote{color:var(--muted);border:1px dashed #B7C0CB;background:#fff}
.pnote svg{width:14px;height:14px;flex:none}.card>.pnote{margin:0 0 12px}
.pick{font:inherit;font-weight:600;color:var(--accent);background:none;border:0;padding:2px 0;cursor:pointer;text-align:left;text-decoration:underline;text-decoration-color:var(--chart-soft);text-underline-offset:3px;overflow-wrap:anywhere}
.pick:hover{color:var(--accent2);text-decoration-color:currentColor}.pick[aria-pressed=true]{color:var(--ink);text-decoration:none}
tr.sel>td{background:var(--accent-soft)}tr.sel .pick:before{content:"";display:inline-block;width:8px;height:8px;border-radius:50%;background:var(--accent);margin-right:7px;vertical-align:1px}
tr.ua .rn b,tr.ua .pick{font-style:italic}tr.tot>td{background:var(--soft);font-weight:700;border-top:1px solid var(--line)}tr.tot .mtr{display:none}table.pt td:first-child{min-width:230px}
.lvl{list-style:none;margin:8px 0 0;padding:0;counter-reset:l}.lvl li{counter-increment:l;display:grid;grid-template-columns:22px minmax(0,1fr) auto;gap:8px;align-items:baseline;padding:6px 0;border-top:1px solid var(--line2);font-size:13.5px}
.lvl li:first-child{border-top:0}.lvl li:before{content:counter(l);font-weight:700;color:var(--muted);font-size:12.5px}.lvl li.z{color:var(--muted)}.lvl li b{white-space:nowrap;color:var(--ink)}.lvl li.ua:before{content:"\\2014"}
.pkey{display:flex;flex-wrap:wrap;align-items:center;gap:8px 12px;margin:4px 0 10px}.pkey code{font-size:17px;font-weight:700;color:var(--ink);background:var(--soft);border:1px solid var(--line);border-radius:8px;padding:2px 10px}
.pkey .arrow{color:var(--muted)}.card p.why{margin:0 0 4px;font-size:14px;max-width:72ch}.svs.pk{margin:6px 0 4px}.svs.pk b{font-size:21px}.svs.pk .tot b{font-size:26px}
footer{background:var(--bar);color:var(--bar-muted);font-size:12.5px;padding:18px 0}footer .wrap{display:flex;justify-content:space-between;gap:16px;flex-wrap:wrap}
@media (max-width:1200px){.kpis{grid-template-columns:repeat(3,minmax(0,1fr))}.g2w{grid-template-columns:minmax(0,1fr)}.svs{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media screen and (max-width:960px){.hero-in{grid-template-columns:minmax(0,1fr)}.g2{grid-template-columns:minmax(0,1fr)}.tt{display:none}}
@media screen and (max-width:720px){h1{font-size:28px}.lead{font-size:16px}.hero{padding-bottom:88px}.kpis{grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;margin-top:-64px}
.kpi{padding:12px 13px;border-radius:13px}.kpi .v{font-size:23px}.kpi .v small{font-size:12px}.kpi .l{font-size:13px;margin-top:5px}.kpi .s{font-size:12px}
.chip{display:none}.pbtn{padding:0 11px}.pbtn span{display:none}.meta .m-gen{display:none}.verdict{padding:14px 16px}.verdict b{font-size:22px}
.secnav .wrap{gap:8px}.secnav .links{padding-right:40px;-webkit-mask-image:linear-gradient(90deg,#000 calc(100% - 44px),transparent);mask-image:linear-gradient(90deg,#000 calc(100% - 44px),transparent)}
.pf{padding-right:8px}.pf label{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}.pf select{max-width:44vw;font-size:13px}
table.pt td:first-child{min-width:0}.pfi{padding:11px 13px}table.stk.pt tr{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);column-gap:14px}table.stk.pt td:first-child{grid-column:1/-1;margin-bottom:2px}table.stk.pt td:first-child:before{content:none}table.stk.pt td .nw{display:inline}.svs.s3,.svs.pk{grid-template-columns:minmax(0,1fr) minmax(0,1fr)}
.card{padding:16px 15px;border-radius:14px}ol.actions li{grid-template-columns:30px minmax(0,1fr)}.a-side{grid-column:2;text-align:left}.a-sv{font-size:16px}
.mc{gap:4px;height:210px}.mx{gap:4px}.mtrack{margin:0 6%}.dc{margin-left:38px;height:190px}.dgrid span{left:-38px}.dx{margin-left:38px}
.hb{grid-template-columns:minmax(0,1fr) auto;row-gap:2px}.hb .t{grid-column:1/-1;grid-row:2}.hb .d{grid-column:2;grid-row:3;text-align:right}.mv,.mx{font-size:12px}
.svs{grid-template-columns:minmax(0,1fr) minmax(0,1fr)}.svs .tot{grid-column:1/-1}.filters input,.filters select{min-width:0;flex:1 1 140px}.fcount{margin-left:0;width:100%}
table.stk thead{display:none}table.stk,table.stk tbody,table.stk tr,table.stk td{display:block;width:100%}table.stk tr{border-bottom:1px solid var(--line);padding:9px 0}
table.stk td{border:0;padding:2px 0;text-align:left!important;white-space:normal}table.stk td[data-h]:before{content:attr(data-h) ": ";color:var(--muted);font-size:12px}
#reg{min-width:0;table-layout:auto}#reg colgroup,#reg thead{display:none}#reg,#reg tbody{display:block;width:100%}#reg tr{display:flex;flex-wrap:wrap;gap:4px 8px;padding:11px 0;border-bottom:1px solid var(--line)}
#reg td{display:block;border:0;padding:0;flex:1 1 100%}#reg td.c1,#reg td.c2{flex:0 0 auto}#reg td.n{text-align:left}#reg tr.f-hide,#reg tr.pg{display:none}}
@media (prefers-reduced-motion:reduce){html{scroll-behavior:auto}.pbtn{transition:none}}
@media print{*{-webkit-print-color-adjust:exact;print-color-adjust:exact}html{scroll-behavior:auto}body{background:#fff;font-size:12.5px}
.secnav,.filters,.pbtn,.more,.skip{display:none!important}.wrap{max-width:none;padding:0 4mm}a{color:inherit;text-decoration:none}
.top .wrap{min-height:44px}.hero{padding:20px 0 70px}.sb{display:none}.pl-only{display:inline}a.pl,.a-ln{display:none}.hero-in{grid-template-columns:minmax(0,1fr) 230px;gap:16px 24px}h1{font-size:27px}.lead{font-size:14px}
.verdict{padding:12px 14px}.verdict b{font-size:20px}.kpis{grid-template-columns:repeat(6,minmax(0,1fr));gap:8px;margin-top:-54px}.kpi{padding:10px 11px;box-shadow:none}
.kpi .v{font-size:19px}.kpi .v small{font-size:11px}.kpi .l{font-size:11.5px}.kpi .s{font-size:11px}.card,.svs div{box-shadow:none}.card{padding:14px 16px}
main{padding:16px 0 0}.sec{margin:0 0 20px}.sh,.card h3,.card .sub{break-after:avoid}.kpi,.verdict,ol.actions li,tr,.hb,.ud li,.note,.svs div,.mc,.dc,.pm{break-inside:avoid}
#reg .ev,#reg .do{font-size:11.5px}#reg td{padding:6px 8px}tr.xr[hidden]{display:table-row!important}.morerow{display:none!important}
.g2,.g2w{grid-template-columns:minmax(0,1fr)}.tw{overflow:visible!important;background:none}thead{display:table-header-group}#reg{min-width:0;table-layout:auto}#reg col{width:auto!important}
#reg tr.pg{display:table-row}.sh:after{content:"";display:block;height:140px;margin-bottom:-140px}#trend{break-before:page}table.bt td:first-child{min-width:170px}table.bt .rn b,table.bt .rn small{overflow-wrap:normal}.svs{break-inside:avoid}.a-t b,.ud b,#reg td>b,.rn b,.hb .n1{overflow-wrap:break-word}
.pfb .btn{display:none}.pick{color:inherit;text-decoration:none}tr.sel>td{background:none}.pfi{margin-bottom:14px}table.pt{font-size:11.5px}table.pt td:first-child{min-width:150px}table.pt th{white-space:normal;font-size:10.5px}table.pt td,table.pt th{padding:6px 5px}table.pt .mtr{min-width:48px}
footer{display:none}}
"""
WORDMARK = ('<span class="wm"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9.2 3h5.6l6.2 18h-4.5l-1.5-4.6H8.4L9.9 12h3.8L12 6.6 6.4 21H2z" '
            'fill="#fff"/></svg>{product}</span>')
ICON_PRINT = ('<svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
              '<path d="M6 9V3h12v6"/><path d="M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2"/><path d="M6 14h12v7H6z"/></svg>')
ICON_EXT = ('<svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">'
            '<path d="M14 4h6v6"/><path d="M20 4l-9 9"/><path d="M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5"/></svg>')
ICON_WARN = ('<svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
             '<path d="M10.3 3.9 2.4 18a2 2 0 0 0 1.7 3h15.8a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/><path d="M12 9v4"/><path d="M12 17h.01"/></svg>')
ICON_INFO = ('<svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
             '<circle cx="12" cy="12" r="9"/><path d="M12 11v5"/><path d="M12 8h.01"/></svg>')


def esc(value):
    return html.escape("" if value is None else str(value), quote=True)


def css_text(value):
    return '"' + re.sub(r'[<>"\\\r\n]', " ", str(value)) + '"'


def sev_pill(sev):
    return f'<span class="sev sev-{sev}">{esc(t("sev_" + sev))}</span>'


def delta_span(delta, pct_value, currency=None, invert=False, new=False):
    if new:
        return f'<span class="tag new">{esc(t("new_badge"))}</span>'
    if delta is None:
        return '<span class="flat">\u2014</span>'
    if abs(delta) < 0.005 or (pct_value is not None and abs(pct_value) < 0.05):
        return f'<span class="flat">{esc(fpct(0))}</span>'
    cls = ("up" if delta > 0 else "down") if not invert else ("down" if delta > 0 else "up")
    if pct_value is not None and abs(pct_value) <= 500:
        body = fpct(pct_value, True)
    else:
        body = ("+" if delta > 0 else "\u2212") + (money(abs(delta), currency) if currency else fnum(abs(delta)))
    return f'<span class="{cls}">{esc(body)}</span>'


NEW_TAB = ' target="_blank" rel="noopener noreferrer" aria-describedby="newtab"'


def res_cell(name, sub_line, rid="", badge=""):
    link = (f' <a class="pl" href="{esc(portal_link(rid))}"{NEW_TAB} aria-label="{esc(t("open_portal"))}: {esc(name)}">{ICON_EXT}'
            f'{esc(t("open_short"))}</a>') if rid and "(not-a-resource)" not in rid and rid.startswith("/subscriptions/") else ""
    return f'<div class="rn"><b>{esc(name)}</b>{badge}{link}' + (f'<small>{esc(sub_line)}</small>' if sub_line else "") + "</div>"


def hbars(rows, total, cur, limit=10, scope_key="scope"):
    if not rows:
        return f'<p class="empty">{esc(t("no_cost"))}</p>'
    if len(rows) == limit + 1:
        limit += 1
    top = rows[:limit]
    vmax = max(r["cost"] for r in top) or 1
    out = []
    for r in top:
        share = fpct(pct(r["cost"], total)) if total else ""
        sub = " \u00b7 ".join(x for x in (r.get(scope_key) or "", share) if x)
        change = delta_span(r.get("delta"), r.get("pct"), cur, new=bool(r.get("new"))) if r.get("delta") is not None else ""
        out.append(f'<div class="hb"><div class="n1">{esc(r["name"])}<small>{esc(sub)}</small></div><div class="t"><i style="width:{100 * r["cost"] / vmax:.1f}%"></i></div>'
                   f'<div class="v">{esc(money(r["cost"], cur))}</div><div class="d">{change}</div></div>')
    rest = rows[limit:]
    if rest:
        rc = sum(r["cost"] for r in rest)
        out.append(f'<div class="hb oth"><div class="n1">{esc(t("others", n=len(rest)))}<small>{esc(fpct(pct(rc, total)) if total else "")}</small></div>'
                   f'<div class="t"><i style="width:{100 * rc / vmax:.1f}%;background:var(--chart-soft)"></i></div><div class="v">{esc(money(rc, cur))}</div><div class="d"></div></div>')
    return "".join(out)


def render_monthly(s):
    cur, months = s["currency"], s["monthly"]
    vmax = max([m["cost"] for m in months] + [m["forecast"] or 0 for m in months] + [1])
    review = s["periods"]["review_month"]
    cols, xs = [], []
    prev_cost = None
    for m in months:
        h = 100 * m["cost"] / vmax
        cls = "mcol" + (" partial" if m["partial"] else "") + (" review" if m["month"] == review else "") + (" zero" if m["cost"] <= 0 else "")
        if m["partial"]:
            fh = max(100 * (m["forecast"] or 0) / vmax, h)
            label = f'{esc(fnum(m["forecast"] or m["cost"], 0))}<small>{esc(t("fc_label"))}</small>'
            bars = (f'<div class="mtrack" style="--h:{fh:.1f}%"><i class="fc" style="height:100%"></i>'
                    f'<i class="mb" style="height:{(100 * h / max(fh, 0.001)):.1f}%"></i></div>')
        else:
            label = esc(fnum(m["cost"], 0)) if m["cost"] > 0 else f'<small>{esc(t("no_cost"))}</small>'
            bars = f'<div class="mtrack" style="--h:{h:.1f}%"><i class="mb" style="height:100%"></i></div>'
        cols.append(f'<div class="{cls}" title="{esc(fmonth(m["month"]))}: {esc(money(m["cost"], cur))}"><div class="mv">{label}</div>{bars}</div>')
        if m["partial"]:
            under = f'<span class="small">{esc(fnum(m["cost"], 0))} {esc(t("mtd_label"))}</span>'
        elif prev_cost and m["cost"] > 0:
            under = delta_span(m["cost"] - prev_cost, pct(m["cost"] - prev_cost, prev_cost))
        else:
            under = ""
        xs.append(f'<div{" class=rv" if m["month"] == review else ""}><b>{esc(fmonth(m["month"], True))}</b>{under}</div>')
        prev_cost = m["cost"]
    summary = "; ".join(f'{fmonth(m["month"])} {money(m["cost"], cur)}' + (f' ({t("mtd_label")}, {t("fc_label")} {money(m["forecast"], cur)})' if m["partial"] and m["forecast"] else "")
                        for m in months)
    return (f'<div class="card"><h3>{esc(t("monthly_h"))}</h3><p class="sub">{esc(t("monthly_sub", month=fmonth_name(s["periods"]["current_month"])))}</p>'
            f'<div class="mc" style="--n:{len(months)}" role="img" aria-label="{esc(summary)}">{"".join(cols)}</div><div class="mx" style="--n:{len(months)}" aria-hidden="true">{"".join(xs)}</div></div>')


def render_daily(s):
    cur, days = s["currency"], s["daily"]
    n = len(days)
    vmax = max([d["cost"] for d in days] + [d["typical"] or 0 for d in days] + [1])
    step = 10 ** max(0, int(math.log10(vmax)))
    top = math.ceil(vmax / step) * step
    if top / step < 4:
        step /= 2
    lines = "".join(f'<span style="bottom:{100 * v / top:.2f}%"><em>{esc(fnum(v, 0))}</em></span>' for v in [k * step for k in range(int(top / step) + 1)])
    review = s["periods"]["review_month"]
    bars, labels, pts = [], [], []
    first_rv = next((i for i, d in enumerate(days) if d["date"][:7] == review), None)
    last_rv = max((i for i, d in enumerate(days) if d["date"][:7] == review), default=None)
    for i, d in enumerate(days):
        period = "pre" if d["date"][:7] < review else "rv"
        cls = f"db {period}" + (" " + d["flag"] if d["flag"] else "") + ("" if d["settled"] else " unsettled")
        bars.append(f'<i class="{cls}" style="height:{100 * d["cost"] / top:.2f}%" title="{esc(fdate(d["date"]))}: {esc(money(d["cost"], cur))}"></i>')
        if d["flag"]:
            labels.append(f'<span class="dlab {d["flag"]}" style="left:{100 * (i + .5) / n:.2f}%;top:{100 - 100 * d["cost"] / top:.2f}%">{esc(fnum(d["cost"], 0))}</span>')
        if d["typical"] is not None:
            pts.append(f'{i + .5:.1f},{100 - 100 * d["typical"] / top:.2f}')
    band = (f'<div class="dband" style="left:{100 * first_rv / n:.2f}%;width:{100 * (last_rv - first_rv + 1) / n:.2f}%"><span>{esc(fmonth_name(review))}</span></div>'
            if first_rv is not None else "")
    ticks = []
    for i, d in enumerate(days):
        dd = parse_day(d["date"])
        if dd.day == 1 or (i == 0 and dd.day < 25):
            ticks.append(f'<span style="left:{100 * (i + .5) / n:.2f}%">{esc(fdate(dd, True))}</span>')
    aria = t("daily_h", n=n) + f": {fdate(days[0]['date'])} \u2192 {fdate(days[-1]['date'])}; " + t("unusual_days") + f": {len(s['unusual'])}"
    swatches = "".join(f'<i class="b-{f}"></i>' for f in ([f for f in ("high", "medium") if any(d["flag"] == f for d in days)] or ["high"]))
    return (f'<div class="card"><h3>{esc(t("daily_h", n=n))}</h3><p class="sub">{esc(t("daily_sub", b=BASELINE_DAYS, l=DATA_LATENCY_DAYS))}</p>'
            f'<div class="dc" role="img" aria-label="{esc(aria)}">{band}<div class="dgrid">{lines}</div><div class="dbars" style="--n:{n}">{"".join(bars)}</div>'
            f'<svg class="dtyp" viewBox="0 0 {n} 100" preserveAspectRatio="none" aria-hidden="true"><polyline vector-effect="non-scaling-stroke" points="{" ".join(pts)}"/></svg>{"".join(labels)}</div>'
            f'<div class="dx" aria-hidden="true">{"".join(ticks)}</div><div class="dleg"><span><i class="ln"></i>{esc(t("daily_typical"))}</span>'
            f'<span>{swatches}{esc(t("daily_unusual"))}</span><span><i class="hatch"></i>{esc(t("daily_partial"))}</span>'
            f'<span><i style="background:var(--chart-soft)"></i>{esc(t("daily_before", month=fmonth_name(review)))}</span></div></div>')


def render_actions(s, empty_key="act_none"):
    cur = s["currency"]
    items = []
    for f in s["actions"]:
        saving = (f'<span class="a-sv">{esc(money(f["saving"], cur, 0 if f["saving"] >= 1000 else 2))}<small>{esc(t("per_month_unit"))}</small></span>'
                  if f["saving"] else "")
        where = f'<span class="a-wh">{esc(f["scope"])}</span>' if f["scope"] else ""
        if f["link"]:
            where += f'<a class="a-ln" href="{esc(f["link"])}"{NEW_TAB}>{ICON_EXT}{esc(t("open_portal"))}</a>'
        items.append(f'<li><div><div class="a-t">{sev_pill(f["severity"])}<b>{esc(f["title"])}</b></div><p class="a-ev">{esc(f["evidence"])}</p>'
                     f'<p class="a-do">{esc(f["action"])}</p></div><div class="a-side">{saving}{where}</div></li>')
    body = f'<ol class="actions">{"".join(items)}</ol>' if items else f'<p class="empty">{esc(t(empty_key))}</p>'
    return f'<div class="card">{body}</div>'


def render_breakdown(s):
    cur, tot = s["currency"], s["totals"]["review"] or 0
    per = s["periods"]
    subs = [dict(r, scope="", cost=r["cost"] or 0) for r in s["subscriptions"] if r["cost"] is not None]
    sub_card = f'<div class="card"><h3>{esc(t("by_sub"))}</h3>{hbars(subs, tot, cur, 8)}</div>'
    multi = len(s["scope"]["subscriptions"]) > 1
    rgs = s["resource_groups"] if multi else [dict(r, scope="") for r in s["resource_groups"]]
    rg_card = (f'<div class="card"><h3>{esc(t("by_rg"))}</h3><p class="sub">{esc(t("by_rg_sub", n=min(10, len(rgs)), t=len(rgs)))}</p>'
               f'{hbars(rgs, tot, cur, 10)}</div>')
    svc_card = (f'<div class="card"><h3>{esc(t("by_service"))}</h3><p class="sub">{esc(t("by_service_sub", n=min(10, len(s["services"])), t=len(s["services"])))}</p>'
                f'{hbars(s["services"], tot, cur, 10)}</div>')
    regions = [dict(r, scope="", delta=None, pct=None) for r in s["regions"]]
    reg_card = f'<div class="card"><h3>{esc(t("by_region"))}</h3>{hbars(regions, tot, cur, 8)}</div>'
    rows = []
    for r in s["resources"][:10]:
        sub_line = " \u00b7 ".join(x for x in (r["type"], r["rg"] or t("sub_level"), r["sub"] if multi else "") if x)
        rows.append(f'<tr><td data-h="{esc(t("col_resource"))}">{res_cell(r["name"], sub_line, r["id"])}</td><td data-h="{esc(t("col_region"))}">{esc(r["region"])}</td>'
                    f'<td class="n" data-h="{esc(fmonth_name(per["review_month"]))}"><b>{esc(money(r["cost"], cur))}</b></td>'
                    f'<td class="n" data-h="{esc(fmonth_name(per["prev_month"]))}">{esc(money(r["prev"], cur))}</td><td class="n" data-h="{esc(t("col_change"))}">{delta_span(r["delta"], r["pct"], cur, new=r["new"])}</td></tr>')
    top_card = (f'<div class="card mt"><h3>{esc(t("top_res"))}</h3><p class="sub">{esc(t("top_res_sub", n=min(10, len(s["resources"])), month=fmonth_name(per["review_month"]), prev=fmonth_name(per["prev_month"])))}</p>'
                f'<div class="tw"><table class="stk"><thead><tr><th scope="col">{esc(t("col_resource"))}</th><th scope="col">{esc(t("col_region"))}</th>'
                f'<th scope="col" class="n">{esc(fmonth_name(per["review_month"]))}</th><th scope="col" class="n">{esc(fmonth_name(per["prev_month"]))}</th>'
                f'<th scope="col" class="n">{esc(t("col_change"))}</th></tr></thead><tbody>{"".join(rows)}</tbody></table></div></div>') if rows else ""
    if len(subs) > 1:
        return f'<div class="g2">{sub_card}{reg_card}</div><div class="g2 mt">{rg_card}{svc_card}</div>' + top_card
    return f'<div class="g2">{svc_card}{rg_card}</div><div class="g2 mt g2s">{reg_card}{sub_card}</div>' + top_card


def render_changes(s):
    cur, per = s["currency"], s["periods"]
    multi = len(s["scope"]["subscriptions"]) > 1
    lis = []
    for u in s["unusual"]:
        drivers = ", ".join(f'{d["service"]} +{money(d["delta"], cur)}' for d in u["drivers"])
        lis.append(f'<li><div>{sev_pill(u["severity"])} <b>{esc(fdate(u["date"]))}</b></div><div class="r"><b>{esc(money(u["cost"], cur))}</b> '
                   f'<span class="up">{esc(fpct(u["pct"], True))}</span></div><div class="x">{esc(t("ud_typical", v=money(u["typical"], cur)))}'
                   f'{(SEP + esc(t("ud_driver", v=drivers))) if drivers else ""}</div></li>')
    ud = f'<ul class="ud">{"".join(lis)}</ul>' if lis else f'<p class="empty">{esc(t("ud_none", month=fmonth_name(per["review_month"])))}</p>'
    pace = s["totals"]["pace"]
    pace_html = ""
    if pace and pace["previous"]:
        pace_html = (f'<div class="note">{ICON_INFO}<span><b>{esc(t("pace_h"))}.</b> '
                     f'{esc(t("pace_txt", k=pace["days"], month=fmonth_name(per["current_month"]), a=money(pace["current"], cur), prev=fmonth_name(per["review_month"]), b=money(pace["previous"], cur), delta=fpct(pace["pct"], True)))}</span></div>')
    left = (f'<div class="card"><h3>{esc(t("unusual_days"))}</h3><p class="sub">{esc(t("unusual_days_sub", pct=fpct(ANOMALY_DAY_PCT, decimals=0), min=money(ANOMALY_MIN_DAILY_DELTA, cur, 0)))}</p>{ud}{pace_html}')
    kind = {"service": t("kind_service"), "rg": t("kind_rg"), "sub": t("kind_sub")}
    jr = "".join(f'<tr><td data-h="{esc(t("col_resource"))}"><div class="rn"><b>{esc(j["name"])}</b><small>{esc(kind[j["kind"]] + (SEP + j["scope"] if j["scope"] and multi else ""))}</small></div></td>'
                 f'<td class="n" data-h="{esc(fmonth_name(per["prev_month"]))}">{esc(money(j["prev"], cur))}</td><td class="n" data-h="{esc(fmonth_name(per["review_month"]))}"><b>{esc(money(j["cost"], cur))}</b></td>'
                 f'<td class="n" data-h="{esc(t("col_change"))}"><span class="up">+{esc(money(j["delta"], cur))}</span><br><span class="small up">{esc(fpct(j["pct"], True))}</span></td></tr>' for j in s["jumps"][:12])
    jumps = (f'<div class="tw"><table class="stk"><thead><tr><th scope="col">{esc(t("col_resource"))}</th><th scope="col" class="n">{esc(fmonth_name(per["prev_month"]))}</th>'
             f'<th scope="col" class="n">{esc(fmonth_name(per["review_month"]))}</th><th scope="col" class="n">{esc(t("col_change"))}</th></tr></thead><tbody>{jr}</tbody></table></div>'
             if jr else f'<p class="empty">{esc(t("jumps_none"))}</p>')
    nw = "".join(f'<li><div><b>{esc(n["name"])}</b> <span class="tag new">{esc(t("new_badge"))}</span><div class="small muted">{esc(kind[n["kind"]] + (SEP + n["scope"] if n["scope"] and multi else ""))}</div></div>'
                 f'<div class="r"><b>{esc(money(n["cost"], cur))}</b></div></li>' for n in s["new"][:10])
    new_html = f'<ul class="ud">{nw}</ul>' if nw else f'<p class="empty">{esc(t("new_none"))}</p>'
    left += (f'<h3 class="h3b">{esc(t("new_services"))}</h3><p class="sub">{esc(t("new_services_sub", month=fmonth_name(per["review_month"])))}</p>{new_html}</div>')
    right = (f'<div class="card"><h3>{esc(t("jumps"))}</h3><p class="sub">{esc(t("jumps_sub", pct=fpct(MOM_MIN_PCT, decimals=0), min=money(MOM_MIN_DELTA, cur, 0), prev=fmonth_name(per["prev_month"]), month=fmonth_name(per["review_month"])))}</p>{jumps}</div>')
    return f'<div class="g2">{left}{right}</div>'


def render_budgets(s):
    cur = s["currency"]
    rows = []
    for b in s["budgets"]:
        st = {"over": ("critical", t("bs_over")), "forecast_over": ("high", t("bs_forecast_over")), "risk": ("medium", t("bs_risk")), "ok": ("ok", t("bs_ok"))}[b["status"]]
        pill = f'<span class="sev sev-{st[0]}">{esc(st[1])}</span>' if st[0] != "ok" else f'<span class="st st-complete">{esc(st[1])}</span>'
        used = min(100, b["used_pct"] or 0)
        fcp = b["forecast_pct"]
        alerts = ", ".join(t("alerts_" + ("forecast" if k.startswith("forecast") else "actual"), v=fpct(v, decimals=0)) for k, v in b["alerts"]) or t("alerts_none")
        rows.append(f'<tr><td data-h="{esc(t("budget_name"))}"><div class="rn"><b>{esc(b["name"])}</b><small>{esc(b["scope"])} \u00b7 {esc(grain_label(b["grain"]))}</small></div></td>'
                    f'<td class="n" data-h="{esc(t("budget_amount"))}">{esc(money(b["amount"], b["currency"]))}</td>'
                    f'<td data-h="{esc(t("budget_spent"))}"><div class="nw">{esc(money(b["spent"], b["currency"]))} <span class="muted small">{esc(fpct(b["used_pct"]))}</span></div>'
                    f'<div class="mtr"><i class="{"x" if used >= 100 else "w" if used >= 80 else ""}" style="width:{used:.1f}%"></i></div></td>'
                    f'<td data-h="{esc(t("budget_forecast"))}"><div class="nw">{esc(money(b["forecast"], b["currency"]) if b["forecast"] is not None else EMDASH)} '
                    f'<span class="{"up" if (fcp or 0) >= 100 else "muted"} small">{esc(fpct(fcp))}</span></div>'
                    f'<div class="mtr"><i class="{"x" if (fcp or 0) >= 100 else "w" if (fcp or 0) >= 90 else ""}" style="width:{min(100, fcp or 0):.1f}%"></i></div></td>'
                    f'<td data-h="{esc(t("budget_status"))}">{pill}</td><td data-h="{esc(t("budget_alerts"))}" class="small">{esc(alerts)}</td></tr>')
    table = (f'<div class="tw"><table class="stk bt" aria-label="{esc(t("s_budgets"))}"><thead><tr><th scope="col">{esc(t("budget_name"))}</th><th scope="col" class="n">{esc(t("budget_amount"))}</th>'
             f'<th scope="col">{esc(t("budget_spent"))}</th><th scope="col">{esc(t("budget_forecast"))}</th><th scope="col">{esc(t("budget_status"))}</th>'
             f'<th scope="col">{esc(t("budget_alerts"))}</th></tr></thead><tbody>{"".join(rows)}</tbody></table></div>') if rows else f'<p class="empty">{esc(t("budget_none"))}</p>'
    nb = "".join(f'<li><div><b>{esc(x["name"])}</b><div class="small muted">{esc(t("kpi_forecast", month=fmonth_name(s["periods"]["current_month"])))}: '
                 f'{esc(money(x["forecast"], cur))}</div></div><div class="r"><span class="small muted">{esc(t("nobudget_suggest"))}</span><br>'
                 f'<b>{esc(money(nice_ceiling((x["forecast"] or 0) * 1.1), cur, 0))}</b></div></li>' for x in s["no_budget"])
    nobudget = (f'<div class="card mt"><h3>{esc(t("nobudget_h"))}</h3><p class="sub">{esc(t("nobudget_sub"))}</p>'
                + (f'<ul class="ud">{nb}</ul>' if nb else f'<p class="empty">{esc(t("nobudget_none"))}</p>') + "</div>")
    return f'<div class="card">{table}</div>{nobudget}'


def pv_wrap(base, variants, fn):
    """The whole-environment block plus one hidden copy per project, switched by the project filter."""
    if not variants:
        return base
    return f'<div class="pv" data-pv="">{base}</div>' + "".join(f'<div class="pv" data-pv="{it["id"]}" hidden>{fn(it)}</div>' for it in variants)


def pnote_html():
    return f'<span class="pnote" hidden>{ICON_INFO}{esc(t("pf_note"))}</span>'


def savings_strip(total, commitments, advisor, idle, cur, sub_key="sv_total_sub"):
    tiles = [f'<div class="tot"><b>{esc(money_short(total, cur))}</b><span>{esc(t(sub_key))}</span></div>']
    if commitments is not None:
        tiles.append(f'<div><b>{esc(money_short(commitments, cur))}</b><span>{esc(t("sv_commit"))}</span></div>')
    tiles.append(f'<div><b>{esc(money_short(advisor, cur))}</b><span>{esc(t("sv_rightsize"))}</span></div>')
    tiles.append(f'<div><b>{esc(money_short(idle, cur))}</b><span>{esc(t("sv_idle"))}</span></div>')
    return f'<div class="svs{"" if commitments is not None else " s3"}">{"".join(tiles)}</div>'


def render_savings(s, variants=()):
    cur, per = s["currency"], s["periods"]
    multi = len(s["scope"]["subscriptions"]) > 1
    sv, c = s["savings"], s["commitment"]
    pm_total = sum(c["eligible"].values())
    seg = "".join(f'<i class="pm-{k}" style="width:{100 * v / pm_total:.2f}%" title="{esc(t("pm_" + k))}: {esc(money(v, cur))}"></i>' for k, v in c["eligible"].items() if v > 0 and pm_total)
    leg = "".join(f'<span><i class="pm-{k}"></i>{esc(t("pm_" + k))} <b>{esc(money(v, cur))}</b></span>' for k, v in c["eligible"].items() if v > 0)
    items = "".join(f'<li><div><b>{esc(i["sku"])}</b><div class="small muted">{esc(SEP.join(x for x in (i["region"], (i["qty"] + TIMES) if i["qty"] else "", i["term"].replace("P1Y", t("term_1y")).replace("P3Y", t("term_3y")), i["sub"] if multi else "") if x))}'
                    f'{(SEP + esc(t("term_3y")) + ": " + esc(money(i["saving_3y"], cur))) if i.get("saving_3y") else ""}</div></div><div class="r"><b>{esc(money(i["saving"], cur))}</b></div></li>' for i in c["items"][:8])
    alt = "; ".join(f'{t("pm_SavingsPlan" if a_["kind"] == "sp" else "pm_Reservation")} {money(a_["saving"], cur)}' for a_ in c["alternatives"])
    commit = (f'<div class="card">{pnote_html() if variants else ""}<h3>{esc(t("commit_h"))}</h3>'
              + (f'<p class="sub">{esc(t("commit_txt", pct=fpct(c["coverage_pct"] or 0), month=fmonth_name(per["review_month"]), elig=money(c["eligible_total"], cur)))}</p>'
                 f'<div class="pm">{seg}</div><div class="dleg">{leg}</div>' if pm_total else f'<p class="empty">{esc(t("commit_none", month=fmonth_name(per["review_month"])))}</p>')
              + (f'<h3 class="h3b">{esc(t("commit_opts"))}</h3><ul class="ud">{items}</ul>' if items else "")
              + (f'<p class="small muted">{esc(t("commit_alt", v=alt))}</p>' if alt else "")
              + f'<div class="note">{ICON_INFO}<span>{esc(t("commit_util"))}</span></div></div>')

    def table(rows, kind):
        trs = []
        for k, x in enumerate(rows[:200]):
            what = t("chk_" + x["check"]) if kind == "idle" else x["problem"]
            sub_line = " \u00b7 ".join(y for y in (x["type"], x["rg"], x["sub"] if multi else "") if y)
            detail = x.get("detail") if kind == "idle" else (t("advisor_est", v=money(x["advisor_amount"], x["advisor_currency"])) if x["advisor_amount"]
                                                             else (x["impact"] and t("impact_v", v=impact_label(x["impact"]))))
            agree = f' <span class="tag">{esc(t("also_advisor"))}</span>' if "advisor" in x.get("also", []) else ""
            trs.append(f'<tr{" class=xr hidden" if k >= 12 else ""}><td data-h="{esc(t("col_check"))}"><b>{esc(what)}</b></td><td data-h="{esc(t("col_resource"))}">{res_cell(x["name"], sub_line, x["id"], agree)}</td>'
                       f'<td data-h="{esc(t("col_detail"))}" class="small">{esc(detail or "")}</td><td class="n" data-h="{esc(t("col_saving"))}"><b>{esc(money(x["saving"], cur) if x["saving"] else t("no_saving"))}</b></td></tr>')
        if len(trs) > 12:
            trs.append(f'<tr class="morerow"><td colspan="4"><button class="btn" type="button" data-more>{esc(tn("show_more", len(trs) - 12))}</button></td></tr>')
        return (f'<div class="tw"><table class="stk"><thead><tr><th scope="col">{esc(t("col_check"))}</th><th scope="col">{esc(t("col_resource"))}</th>'
                f'<th scope="col">{esc(t("col_detail"))}</th><th scope="col" class="n">{esc(t("col_saving"))}</th></tr></thead><tbody>{"".join(trs)}</tbody></table></div>')

    def tables(rows_all, suffix=""):
        adv_rows = [x for x in rows_all if x["source"] == "advisor"]
        idle_rows = [x for x in rows_all if x["source"] == "idle"]
        adv = (f'<div class="card mt"><h3>{esc(t("advisor_h"))}</h3><p class="sub">{esc(tn("advisor_sub", len(adv_rows)))}</p>{table(adv_rows, "advisor")}</div>' if adv_rows
               else f'<div class="card mt"><h3>{esc(t("advisor_h"))}</h3><p class="empty">{esc(t("advisor_none" + suffix))}</p></div>')
        idle = (f'<div class="card mt"><h3>{esc(t("idle_h"))}</h3><p class="sub">{esc(t("idle_sub", month=fmonth_name(per["review_month"])))}</p>{table(idle_rows, "idle")}</div>' if idle_rows
                else f'<div class="card mt"><h3>{esc(t("idle_h"))}</h3><p class="empty">{esc(t("idle_none" + suffix))}</p></div>')
        return idle + adv

    strip = pv_wrap(savings_strip(sv["total"], sv["commitments"], sv["advisor"], sv["idle"], cur), variants,
                    lambda it: savings_strip(it["savings"], None, it["savings_advisor"], it["savings_idle"], cur, "sv_total_sub_p"))
    lists = pv_wrap(tables(sv["items"]), variants, lambda it: tables([x for x in sv["items"] if x.get("project_id") == it["id"]], "_p"))
    return strip + commit + lists


def render_allocation(s):
    cur, al, per = s["currency"], s["allocation"], s["periods"]
    if not al:
        return f'<div class="card"><p class="empty">{esc(t("alloc_none"))}</p></div>'
    rows = [{"name": p_["tag"], "pct": p_["pct"] or 0, "untagged": p_["untagged"]} for p_ in al["per_tag"]]
    if len(al["tags"]) > 1:
        rows.append({"name": t("alloc_all", n=len(al["tags"])), "pct": al["all_pct"] or 0, "untagged": r2(al["total"] - al["all_tagged"]), "all": True})
    bars = "".join(f'<div class="hb"><div class="n1"><b>{esc(r["name"])}</b>{"" if not r.get("all") else ""}<small>{esc(t("alloc_untagged"))}: {esc(money(r["untagged"], cur))}</small></div>'
                   f'<div class="t"><i style="width:{r["pct"]:.1f}%;{"background:var(--accent2)" if r.get("all") else ""}"></i></div><div class="v">{esc(fpct(r["pct"]))}</div><div class="d"></div></div>' for r in rows)
    multi = len(s["scope"]["subscriptions"]) > 1
    rg_rows = "".join(f'<tr><td data-h="{esc(t("kind_rg"))}"><div class="rn"><b>{esc(g["rg"])}</b>{("<small>" + esc(g["sub"]) + "</small>") if multi else ""}</div></td>'
                      f'<td class="n" data-h="{esc(t("alloc_untagged"))}"><b>{esc(money(g["untagged"], cur))}</b></td><td class="n" data-h="{esc(t("col_share"))}">{esc(fpct(g["share"]))}</td></tr>' for g in al["rgs"])
    rg_html = (f'<div class="tw"><table class="stk"><thead><tr><th scope="col">{esc(t("kind_rg"))}</th><th scope="col" class="n">{esc(t("alloc_untagged"))}</th>'
               f'<th scope="col" class="n">{esc(t("col_share"))}</th></tr></thead><tbody>{rg_rows}</tbody></table></div>') if rg_rows else f'<p class="empty">{esc(t("alloc_rg_none"))}</p>'
    notes = f'<div class="note">{ICON_INFO}<span>{esc(t("alloc_inherit_on" if s["config"]["inheritance"] else "alloc_inherit_off"))}'
    if al["not_resource"]:
        notes += " " + esc(t("alloc_notres", v=money(al["not_resource"], cur)))
    notes += "</span></div>"
    return (f'<div class="g2"><div class="card"><h3>{esc(t("alloc_tag"))}</h3><p class="sub">{esc(t("alloc_tag_sub", month=fmonth_name(per["review_month"]), total=money(al["total"], cur)))}</p>{bars}{notes}</div>'
            f'<div class="card"><h3>{esc(t("alloc_rg_h"))}</h3><p class="sub">{esc(t("alloc_rg_sub", month=fmonth_name(per["review_month"])))}</p>{rg_html}</div></div>')


def project_view(s, it):
    """A copy of the snapshot whose breakdown shows one project only."""
    return dict(s, subscriptions=[dict(r, read=True) for r in it["by_sub"]], resource_groups=it["by_rg"], services=it["by_service"],
                regions=it["by_region"], resources=it["top_resources"], totals=dict(s["totals"], review=it["cost"]))


def pick_html(it, filtering):
    if filtering and it["variant"]:
        return (f'<button class="pick" type="button" data-pick="{it["id"]}" aria-pressed="false" aria-label="{esc(t("proj_pick", name=it["name"]))}">'
                f'{esc(it["name"])}</button>')
    return f'<b>{esc(it["name"])}</b>'


def project_detail(s, it):
    cur, per = s["currency"], s["periods"]
    tiles = (f'<div class="svs pk"><div class="tot"><b>{esc(money_short(it["cost"], cur))}</b><span>{esc(fmonth(per["review_month"]))}</span></div>'
             f'<div><b>{delta_span(it["delta"], it["pct"], cur, new=it["prev"] <= 0.005 and it["cost"] > 0)}</b><span>{esc(t("pd_change", prev=fmonth_name(per["prev_month"])))}</span></div>'
             f'<div><b>{esc(money_short(it["mtd"], cur))}</b><span>{esc(t("pd_mtd", month=fmonth_name(per["current_month"])))}</span></div>'
             f'<div><b>{esc(money_short(it["savings"], cur))}</b><span>{esc(t("pd_savings"))}</span></div></div>')
    res = "".join(f'<li><div><b>{esc(r["name"])}</b><div class="small muted">{esc(SEP.join(x for x in (r["type"], r["rg"]) if x))}</div></div>'
                  f'<div class="r"><b>{esc(money(r["cost"], cur))}</b></div></li>' for r in it["top_resources"][:5])
    sub = SEP.join((tn("proj_res", it["resources"]), tn("proj_rgs", it["resource_groups"]), tn("pd_findings", it["findings"])))
    return (f'<div class="card"><h3>{esc(it["name"])}</h3><p class="sub">{esc(sub)}</p>{tiles}'
            f'<h3 class="h3b">{esc(t("pd_services"))}</h3>{hbars(it["by_service"], it["cost"], cur, 5)}'
            f'<h3 class="h3b">{esc(t("pd_rgs"))}</h3>{hbars(it["by_rg"], it["cost"], cur, 5)}'
            + (f'<h3 class="h3b">{esc(t("pd_resources"))}</h3><ul class="ud">{res}</ul>' if res else "") + "</div>")


def render_projects(s, variants):
    pj, cur, per = s["projects"], s["currency"], s["periods"]
    filtering = bool(variants)
    month, prevm = fmonth_name(per["review_month"]), fmonth_name(per["prev_month"])
    items, total = pj["items"], pj["total"]
    named = [it for it in items if not it["unallocated"]]
    unalloc = [it for it in items if it["unallocated"]]
    heads = (t("col_project"), month, prevm, t("col_change"), t("col_share"), t("col_mtd", month=fmonth(per["current_month"], True)), t("col_psavings"), t("col_findings"))

    def row(it, cls="", name_html=None, line=""):
        share = it["share"] or 0
        return (f'<tr{(" class=" + cls) if cls else ""}><td data-h="{esc(heads[0])}"><div class="rn">{name_html or pick_html(it, filtering)}'
                f'{("<small>" + esc(line) + "</small>") if line else ""}</div></td>'
                f'<td class="n" data-h="{esc(heads[1])}"><b>{esc(money(it["cost"], cur))}</b></td><td class="n" data-h="{esc(heads[2])}">{esc(money(it["prev"], cur))}</td>'
                f'<td class="n" data-h="{esc(heads[3])}">{delta_span(it["delta"], it["pct"], cur, new=it["prev"] <= 0.005 and it["cost"] > 0)}</td>'
                f'<td data-h="{esc(heads[4])}"><div class="nw">{esc(fpct(share))}</div><div class="mtr"><i style="width:{max(0.0, min(100.0, share)):.1f}%"></i></div></td>'
                f'<td class="n" data-h="{esc(heads[5])}">{esc(money(it["mtd"], cur))}</td>'
                f'<td class="n" data-h="{esc(heads[6])}">{esc(money(it["savings"], cur) if it["savings"] else t("no_saving"))}</td>'
                f'<td class="n" data-h="{esc(heads[7])}">{esc(str(it["findings"]) if it["findings"] else t("no_saving"))}</td></tr>')

    if items:
        rows = []
        for it in named[:60]:
            top = it["by_service"][0]["name"] if it["by_service"] else ""
            rows.append(row(it, line=SEP.join(x for x in (tn("proj_res", it["resources"]), tn("proj_rgs", it["resource_groups"]), t("proj_top", v=top) if top else "") if x)))
        rest = named[60:]
        if rest:
            agg = {k: r2(sum(x[k] for x in rest)) for k in ("cost", "prev", "mtd", "savings")}
            agg.update(findings=sum(x["findings"] for x in rest), delta=r2(agg["cost"] - agg["prev"]), pct=pct(agg["cost"] - agg["prev"], agg["prev"]), share=pct(agg["cost"], total))
            rows.append(row(agg, name_html=f'<b>{esc(t("proj_more", n=len(rest)))}</b>'))
        for it in unalloc:
            rows.append(row(it, "ua", line=t("proj_unalloc_sub")))
        tot = {k: r2(sum(x[k] for x in items)) for k in ("cost", "prev", "mtd", "savings")}
        tot.update(findings=sum(x["findings"] for x in items), delta=r2(tot["cost"] - tot["prev"]), pct=pct(tot["cost"] - tot["prev"], tot["prev"]),
                   share=100.0 if tot["cost"] else 0.0)
        rows.append(row(tot, "tot", name_html=f'<b>{esc(t("proj_total"))}</b>'))
        ths = "".join(f'<th scope="col"{" class=n" if k not in (0, 4) else ""}>{esc(h)}</th>' for k, h in enumerate(heads))
        table = (f'<div class="card"><div class="tw"><table class="stk pt" aria-label="{esc(t("s_projects"))}"><thead><tr>{ths}</tr></thead>'
                 f'<tbody>{"".join(rows)}</tbody></table></div></div>')
    else:
        table = f'<div class="card"><p class="empty">{esc(t("proj_none", month=month))}</p></div>'
    # how projects are identified
    src, keys = pj["source"], pj["keys"]
    key_html = '<span class="arrow" aria-hidden="true">\u2192</span>'.join(f"<code>{esc(k)}</code>" for k in keys) if keys else ""
    chip = f'<span class="tag{" new" if src == "detected" else ""}">{esc(t("pid_chip_" + src))}</span>'
    rs = pj["reason"]
    if src == "detected" and rs:
        why = (t("pid_why_detected", meaning=t("meaning_" + str(rs["meaning"])), cov=fpct(rs["coverage_pct"]), month=month, n=rs["values"])
               if rs["coverage_pct"] is not None else t("pid_why_detected_cost", meaning=t("meaning_" + str(rs["meaning"]))))
    elif src in ("configured", "parameter"):
        why = t("pid_why_" + src, cov=fpct(pj["tagged_pct"] or 0), month=month)
    else:
        why = t("pid_why_none")
    levels, bs = [], pj["by_source"]
    for lvl in ("resource", "rg", "managed", "sub", "cost", "rule"):
        v = bs.get(lvl, 0.0)
        if lvl in ("managed", "sub") and abs(v) <= 0.004:
            continue
        extra = ""
        if lvl == "cost" and not pj["cost_tags_read"]:
            extra = t("pid_cost_off")
        elif lvl == "rule":
            extra = "; ".join(t("rule_arrow", p=r_["pattern"], v=r_["project"]) for r_ in pj["rules"][:4]) or t("pid_no_rules")
        extra_html = f' <span class="small">({esc(extra)})</span>' if extra else ""
        levels.append(f'<li{" class=z" if abs(v) <= 0.004 else ""}><span>{esc(t("pid_lvl_" + lvl))}{extra_html}</span><b>{esc(fpct(pct(v, total)) if total else EMDASH)}</b></li>')
    v = bs.get("none", 0.0)
    levels.append(f'<li class="ua{" z" if abs(v) <= 0.004 else ""}"><span>{esc(t("pid_lvl_none"))}</span><b>{esc(fpct(pct(v, total)) if total else EMDASH)}</b></li>')
    crows = []
    for c in pj["candidates"][:6]:
        use = f' <span class="tag new">{esc(t("pid_in_use"))}</span>' if c["chosen"] else ""
        where = ", ".join(t("where_" + w) for w in c["where"]) or EMDASH
        cov = fpct(c["coverage_pct"]) if c["coverage_pct"] is not None else t("not_measured")
        crows.append(f'<tr><td data-h="{esc(t("col_tag"))}"><code>{esc(c["key"])}</code>{use}</td><td data-h="{esc(t("col_found"))}" class="small">{esc(where)}</td>'
                     f'<td class="n" data-h="{esc(t("col_coverage"))}">{esc(cov)}</td>'
                     f'<td class="n" data-h="{esc(t("col_values"))}">{esc(str(c["values"]) if c["values"] is not None else EMDASH)}</td></tr>')
    cand = (f'<h3 class="h3b">{esc(t("pid_cand"))}</h3><p class="sub">{esc(t("pid_cand_sub"))}</p><div class="tw"><table class="stk"><thead><tr>'
            f'<th scope="col">{esc(t("col_tag"))}</th><th scope="col">{esc(t("col_found"))}</th><th scope="col" class="n">{esc(t("col_coverage"))}</th>'
            f'<th scope="col" class="n">{esc(t("col_values"))}</th></tr></thead><tbody>{"".join(crows)}</tbody></table></div>') if crows else ""
    override = t("pid_override", tag=keys[0]) if keys else t("pid_override_none")
    notes = (f'<div class="note">{ICON_INFO}<span>{esc(t("pid_past"))} {esc(override)}</span></div>'
             f'<div class="note">{ICON_INFO}<span>{esc(t("pid_inherit"))} <a href="{esc(LEARN_TAG_INHERITANCE)}"{NEW_TAB}>{esc(LEARN_TITLES[LEARN_TAG_INHERITANCE])}</a></span></div>')
    ident = (f'<div class="card"><h3>{esc(t("pid_h"))}</h3><div class="pkey"><span class="small muted">{esc(t("pid_tag"))}</span>{key_html}{chip}</div>'
             f'<p class="why">{esc(why)}</p><p class="sub lvh">{esc(t("pid_order", month=month))}</p><ol class="lvl">{"".join(levels)}</ol>{cand}{notes}</div>')
    bars = sorted(({"name": it["name"], "scope": "", "cost": it["cost"], "delta": it["delta"], "pct": it["pct"], "new": it["prev"] <= 0.005 and it["cost"] > 0}
                   for it in items), key=lambda r: -r["cost"])
    share_card = (f'<div class="card"><h3>{esc(t("proj_share_h", month=month))}</h3>' + (f'<p class="sub">{esc(t("proj_share_sub"))}</p>' if filtering else "")
                  + f'{hbars(bars, total, cur, 8)}</div>')
    return table + f'<div class="g2 mt g2s">{pv_wrap(share_card, variants, lambda it: project_detail(s, it))}{ident}</div>'


def render_register(s, stem):
    cur = s["currency"]
    cats = sorted({f["category"] for f in s["findings"]})
    rows = []
    for f in s["findings"]:
        q = " ".join((f["title"], f["evidence"], f["scope"], f["action"], t("cat_" + f["category"]), f.get("project", ""))).lower()
        scope = esc(f["scope"] or "\u2014")
        if f["link"]:
            scope += f'<a class="pl blk" href="{esc(f["link"])}"{NEW_TAB}>{ICON_EXT}{esc(t("open_portal"))}</a>'
        rows.append(f'<tr data-sev="{f["severity"]}" data-rank="{SEV_RANK[f["severity"]]}" data-cat="{f["category"]}" data-saving="{f["saving"] or 0}" data-q="{esc(q)}"'
                    f' data-scope="{esc(f["scope"])}" data-id="{esc(f["resource_id"])}" data-url="{esc(f["link"])}" data-proj="{esc(f.get("project_id", ""))}"'
                    f' data-pn="{esc(f.get("project", ""))}">'
                    f'<td class="c1">{sev_pill(f["severity"])}</td><td class="c2 small">{esc(t("cat_" + f["category"]))}</td>'
                    f'<td><b>{esc(f["title"])}</b><div class="ev">{esc(f["evidence"])}</div><div class="do">{esc(f["action"])}</div></td>'
                    f'<td class="small">{scope}</td><td class="n"><b>{esc(money(f["saving"], cur) if f["saving"] else t("no_saving"))}</b></td></tr>')
    sev_opts = "".join(f'<option value="{s_}">{esc(t("sev_" + s_))}</option>' for s_ in SEVERITIES)
    cat_opts = "".join(f'<option value="{c_}">{esc(t("cat_" + c_))}</option>' for c_ in cats)
    return (f'<div class="card"><div class="filters" role="search"><label class="vh" for="fq">{esc(t("reg_search"))}</label>'
            f'<input id="fq" type="search" placeholder="{esc(t("reg_search"))}" autocomplete="off"><label class="vh" for="fs">{esc(t("col_sev"))}</label>'
            f'<select id="fs"><option value="">{esc(t("reg_all_sev"))}</option>{sev_opts}</select><label class="vh" for="fc">{esc(t("col_cat"))}</label>'
            f'<select id="fc"><option value="">{esc(t("reg_all_cat"))}</option>{cat_opts}</select><button class="btn" type="button" id="fx">{esc(t("reg_clear"))}</button>'
            f'<button class="btn" type="button" id="fe">{esc(t("reg_export"))}</button><span class="fcount" id="fn" aria-live="polite"></span></div>'
            f'<div class="tw"><table id="reg" aria-label="{esc(t("s_register"))}" data-file="{esc(stem)}-{esc(t("csv_findings"))}" data-cur="{esc(cur)}" data-count="{esc(t("reg_count"))}" '
            f'data-countf="{esc(t("reg_count_f"))}" data-csvh="{esc("|".join((t("col_evidence"), t("col_action"), t("col_resource_id"), t("col_link"), t("filtered"), t("col_project"))))}"><colgroup><col class="w1"><col class="w2"><col><col class="w4"><col class="w5"></colgroup>'
            f'<thead><tr><th scope="col" data-k="rank" aria-sort="descending"><button class="sb" type="button">{esc(t("col_sev"))}</button><span class="pl-only">{esc(t("col_sev"))}</span></th>'
            f'<th scope="col" data-k="cat"><button class="sb" type="button">{esc(t("col_cat"))}</button><span class="pl-only">{esc(t("col_cat"))}</span></th><th scope="col">{esc(t("col_finding"))}</th>'
            f'<th scope="col">{esc(t("col_scope"))}</th><th scope="col" class="n" data-k="saving"><button class="sb" type="button">{esc(t("col_saving"))}</button><span class="pl-only">{esc(t("col_saving"))}</span></th></tr></thead>'
            f'<tbody id="tb">{"".join(rows)}</tbody></table></div><p class="empty" id="fz" hidden>{esc(t("reg_none"))} <button class="linkbtn" type="button" id="fz2">{esc(t("reg_clear"))}</button></p>'
            f'<div class="more"><button class="btn" type="button" id="fm">{esc(t("reg_more"))}</button></div></div>')


def identity_label(value):
    text_value = str(value or "")
    for prefix, key in (("verified", "id_verified"), ("not matched", "id_unmatched"), ("unreadable", "id_unreadable"), ("self-test", "id_self_test")):
        if text_value.startswith(prefix):
            return t(key)
    return text_value


def render_coverage(s):
    cov, cur, per = s["coverage"], s["currency"], s["periods"]
    rows = "".join(f'<tr><td data-h="{esc(t("cov_source"))}"><b>{esc(t(x["label"]))}</b>{(" <span class=tag>" + esc(t("optional")) + "</span>") if x.get("optional") else ""}'
                   f'{("<div class=small>" + esc(clean(x["errors"][0]["message"], 220)) + "</div>") if x["errors"] else ""}</td>'
                   f'<td data-h="{esc(t("cov_status"))}"><span class="st st-{x["status"]}">{esc(t("st_" + x["status"]))}</span></td>'
                   f'<td class="n" data-h="{esc(t("cov_records"))}">{esc(fnum(x["records"], 0))}</td><td class="n" data-h="{esc(t("cov_seconds"))}">{esc(fnum(x["seconds"], 1))}</td></tr>' for x in cov["sources"])
    method = "".join(f"<li>{esc(m)}</li>" for m in (x.format(metric=t("metric_" + s["metric"]), metric_note=t("metric_note_" + s["metric"]), currency=cur, lat=DATA_LATENCY_DAYS,
                                                               through=fdate(per["complete"]), pct=fpct(ANOMALY_DAY_PCT, decimals=0), b=BASELINE_DAYS,
                                                               min=money(ANOMALY_MIN_DAILY_DELTA, cur, 0), mpct=fpct(MOM_MIN_PCT, decimals=0), mmin=money(MOM_MIN_DELTA, cur, 0),
                                                               month=fmonth(per["review_month"])) for x in t("method_items")))
    notcov = "".join(f"<li>{esc(m)}</li>" for m in t("notcov_items"))
    notes = []
    if cov["throttled"]:
        notes.append(t("throttle_note", n=cov["throttled"], s=fnum(cov["waited"], 0)))
    if cov["skipped_subscriptions"]:
        notes.append(t("cov_skipped", n=len(cov["skipped_subscriptions"])))
    if cov["other_currency_subscriptions"]:
        notes.append(t("cov_other_cur", v=", ".join(cov["other_currency_subscriptions"])))
    if cov["invisible_subscriptions"]:
        notes.append(t("cov_invisible", v=", ".join(cov["invisible_subscriptions"])))
    note_html = "".join(f'<div class="note warn">{ICON_WARN}<span>{esc(n)}</span></div>' for n in notes)
    links = "".join(f'<li><a href="{esc(u)}"{NEW_TAB}>{esc(LEARN_TITLES.get(u, u))}</a></li>' for u in LEARN_SOURCES)
    stats = t("cov_stats", n=fnum(cov["requests"], 0), s=fnum(cov["seconds"], 1)) + (SEP + t("cov_identity", v=identity_label(cov["identity"])) if cov["identity"] else "")
    return (f'<div class="card"><div class="tw"><table class="stk" aria-label="{esc(t("s_coverage"))}"><thead><tr><th scope="col">{esc(t("cov_source"))}</th><th scope="col">{esc(t("cov_status"))}</th>'
            f'<th scope="col" class="n">{esc(t("cov_records"))}</th><th scope="col" class="n">{esc(t("cov_seconds"))}</th></tr></thead><tbody>{rows}</tbody></table></div>'
            f'{note_html}<p class="small muted">{esc(stats)}</p></div>'
            f'<div class="g2 mt"><div class="card"><h3>{esc(t("method_h"))}</h3><ul class="plain">{method}</ul></div>'
            f'<div class="card"><h3>{esc(t("notcov_h"))}</h3><ul class="plain">{notcov}</ul><h3 style="margin-top:18px">{esc(t("learn_h"))}</h3><ul class="plain small">{links}</ul></div></div>')


REPORT_JS = """
(function(){var $=function(i){return document.getElementById(i)},each=function(s,f){[].forEach.call(document.querySelectorAll(s),f)};
each('[data-print]',function(b){b.addEventListener('click',function(){window.print()})});
var navs=[].slice.call(document.querySelectorAll('.secnav a')),strip=document.querySelector('.secnav .links');
if('IntersectionObserver' in window&&strip){var io=new IntersectionObserver(function(es){es.forEach(function(e){if(!e.isIntersecting)return;navs.forEach(function(a){var on=a.getAttribute('href')==='#'+e.target.id;a.classList.toggle('on',on);
if(on){a.setAttribute('aria-current','true');if(strip.scrollWidth>strip.clientWidth)strip.scrollLeft+=a.getBoundingClientRect().left-strip.getBoundingClientRect().left-24}else a.removeAttribute('aria-current')})})},{rootMargin:'-40% 0px -55% 0px'});each('section.sec[id]',function(s){io.observe(s)})}
function tws(){each('.tw',function(w){var o=w.scrollWidth>w.clientWidth+1;if(o&&!w.hasAttribute('tabindex')){var c=w.closest('.card'),h=c&&c.querySelector('h3');w.tabIndex=0;w.setAttribute('role','region');w.setAttribute('aria-label',(h?h.textContent:document.body.getAttribute('data-tbl'))+' '+document.body.getAttribute('data-scroll'))}
else if(!o&&w.hasAttribute('tabindex')){w.removeAttribute('tabindex');w.removeAttribute('role');w.removeAttribute('aria-label')}});if(strip){strip.classList.remove('ovf');strip.classList.toggle('ovf',strip.scrollWidth>strip.clientWidth+1)}}
tws();var rt;window.addEventListener('resize',function(){clearTimeout(rt);rt=setTimeout(tws,200)});
each('[data-more]',function(b){b.addEventListener('click',function(){var tb_=b.closest('tbody');[].forEach.call(tb_.querySelectorAll('tr.xr'),function(r){r.hidden=false});b.closest('tr').remove()})});
window.addEventListener('beforeprint',function(){each('tr.xr',function(r){r.hidden=false});each('tr.morerow',function(r){r.remove()})});
each('.secnav a',function(a){a.addEventListener('focus',function(){var st=a.parentNode;if(a.offsetLeft<st.scrollLeft||a.offsetLeft+a.offsetWidth>st.scrollLeft+st.clientWidth)st.scrollLeft=a.offsetLeft-24})});
var pf=$('pf'),pk='',hooks=[];
function proj(k){pk=k||'';each('[data-pv]',function(e){e.hidden=e.getAttribute('data-pv')!==pk});var o=pf&&pk?pf.querySelector('option[value="'+pk+'"]'):null,nm=o?o.textContent:'';
each('.pnote',function(e){e.hidden=!pk});each('.pchip',function(e){e.hidden=!pk;e.querySelector('b').textContent=nm});
each('[data-pick]',function(b){var on=b.getAttribute('data-pick')===pk,r=b.closest('tr');b.setAttribute('aria-pressed',on?'true':'false');if(r)r.classList.toggle('sel',on)});
if(pf){pf.value=pk;pf.parentNode.classList.toggle('on',!!pk)}hooks.forEach(function(h){h()});tws()}
if(pf)pf.addEventListener('change',function(){proj(pf.value)});
each('[data-pick]',function(b){b.addEventListener('click',function(){proj(b.getAttribute('data-pick'))})});
each('[data-pclear]',function(b){b.addEventListener('click',function(){proj('');if(pf)pf.focus()})});
var tb=$('tb');if(tb){var rows=[].slice.call(tb.rows),PAGE=25,limit=PAGE,key='rank',asc=false,reg=$('reg'),tpl=reg.getAttribute('data-count'),tplf=reg.getAttribute('data-countf');
var vis=function(){var q=$('fq').value.toLowerCase().trim(),s=$('fs').value,c=$('fc').value;return rows.filter(function(r){var d=r.dataset;return(!pk||d.proj===pk)&&(!s||d.sev===s)&&(!c||d.cat===c)&&(!q||d.q.indexOf(q)>=0)})};
var val=function(r){var d=r.dataset;return key==='rank'?(+d.rank)*1e9+(+d.saving):key==='saving'?+d.saving:(d[key]||'')};
var draw=function(){var v=vis();v.sort(function(x,y){var a=val(x),b=val(y);return a<b?(asc?-1:1):a>b?(asc?1:-1):0});rows.forEach(function(r){r.classList.add('f-hide');r.classList.remove('pg')});
v.forEach(function(r,i){tb.appendChild(r);r.classList.remove('f-hide');if(i>=limit)r.classList.add('pg')});var fl=$('fq').value||$('fs').value||$('fc').value||pk;
$('fn').textContent=(fl?tplf:tpl).replace('{v}',Math.min(limit,v.length)).replace('{m}',v.length).replace('{t}',rows.length);$('fz').hidden=v.length>0;
$('fm').parentNode.style.display=v.length>limit?'':'none';each('#reg th[data-k]',function(th){if(th.dataset.k===key)th.setAttribute('aria-sort',asc?'ascending':'descending');else th.removeAttribute('aria-sort')})};
hooks.push(function(){limit=PAGE;draw()});
['fq','fs','fc'].forEach(function(i){$(i).addEventListener('input',function(){limit=PAGE;draw()})});$('fm').addEventListener('click',function(){limit+=PAGE;draw()});
var clr=function(){$('fq').value='';$('fs').value='';$('fc').value='';limit=PAGE;draw()};$('fx').addEventListener('click',clr);$('fz2').addEventListener('click',function(){clr();if(pk)proj('')});
each('#reg th[data-k] .sb',function(b){b.addEventListener('click',function(){var k=b.parentNode.dataset.k;if(key===k)asc=!asc;else{key=k;asc=k==='cat'}draw()})});
var saved;window.addEventListener('beforeprint',function(){saved=[$('fq').value,$('fs').value,$('fc').value,limit];$('fq').value='';$('fs').value='';$('fc').value='';limit=rows.length;draw()});
window.addEventListener('afterprint',function(){if(!saved)return;$('fq').value=saved[0];$('fs').value=saved[1];$('fc').value=saved[2];limit=saved[3];saved=null;draw()});
$('fe').addEventListener('click',function(){var q=function(s){s=String(s).replace(/\\s+/g,' ').trim();if(/^[=+\\-@]/.test(s))s="'"+s;return '"'+s.replace(/"/g,'""')+'"'},tx=function(e){return e?e.textContent:''};
var hd=[].map.call(document.querySelectorAll('#reg thead th'),function(th){return tx(th.querySelector('.pl-only')||th)});var cu=reg.getAttribute('data-cur');
var xh=reg.getAttribute('data-csvh').split('|'),out=[hd.slice(0,4).concat([xh[5],hd[4]+' ('+cu+')',xh[0],xh[1],xh[2],xh[3]]).map(q).join(',')];
[].forEach.call(tb.rows,function(r){if(r.classList.contains('f-hide'))return;var c=r.cells,d=r.dataset;out.push([tx(c[0]),tx(c[1]),tx(c[2].querySelector('b')),d.scope,d.pn,(+d.saving).toFixed(2),tx(c[2].querySelector('.ev')),tx(c[2].querySelector('.do')),d.id,d.url].map(q).join(','))});
var fl=$('fq').value||$('fs').value||$('fc').value||pk;var a=document.createElement('a');a.href=URL.createObjectURL(new Blob(['\\ufeff'+out.join('\\r\\n')],{type:'text/csv;charset=utf-8'}));a.download=reg.getAttribute('data-file')+(fl?'-'+xh[4]:'')+'.csv';
document.body.appendChild(a);a.click();setTimeout(function(){URL.revokeObjectURL(a.href);a.remove()},2000)});draw()}
if(pf&&pf.value)proj(pf.value)})();
"""


def render_html(s, stem="finops-review", logo=""):
    cur, per, tot, v = s["currency"], s["periods"], s["totals"], s["verdict"]
    review, prev, current = per["review_month"], per["prev_month"], per["current_month"]
    client = s["client_name"]
    counts = v["counts"]
    total_findings = sum(counts.values()) or 1
    track = "".join(f'<i class="b-{k}" style="width:{100 * counts[k] / total_findings:.2f}%" title="{esc(t("sev_" + k))}: {counts[k]}"></i>' for k in SEVERITIES if counts[k])
    legend = "".join(f'<span><i class="b-{k}"></i>{esc(t("sev_" + k))} <b>{counts[k]}</b></span>' for k in SEVERITIES if counts[k] or k in ("high", "medium"))
    cov_note = ""
    if v["partial"]:
        issues = [t(x["label"]) for x in s["coverage"]["sources"] if x["status"] in ("partial", "denied", "error", "skipped")]
        cov_note = f'<p class="cov">{ICON_WARN}<span>{esc(t("v_partial", v=", ".join(issues[:2]) or t("chip_partial")))}</span></p>'
    detail = t("v_nodata_detail") if v["tone"] == "nodata" else (" \u00b7 ".join(v.get("detail") or []) or t("v_nothing"))
    verdict = (f'<aside class="verdict v-{v["tone"]}" aria-label="{esc(t("verdict"))}"><div class="k">{esc(t("verdict"))}</div><b>{esc(v["label"])}</b>'
               f'<p>{esc(detail)}</p>{cov_note}</aside>')
    subs = s["scope"]["subscriptions"]
    scope_chip = t("chip_mg", v=s["scope"]["management_group"]) + " \u00b7 " if s["scope"]["management_group"] else ""
    scope_chip += tn("chip_scope", len(subs))
    if s["provenance"] != "LIVE":
        prov = f'<span class="sim">{esc(t("simulated"))}</span>'
    else:
        prov = f'<span class="warn">{esc(t("live_partial"))}</span>' if s["status"] != "ok" else f'<span>{esc(t("live"))}</span>'
    meta = [f'<span>{esc(scope_chip)}</span>', f'<span>{esc(t("metric_" + s["metric"]))} \u00b7 {esc(cur)}</span>',
            f'<span class="m-win">{esc(t("chip_window", a=fdate(per["review_start"]), b=fdate(per["review_end"])))}</span>',
            f'<span class="m-gen">{esc(t("generated", v=s["generated_utc"][:16].replace("T", " ")))}</span>', prov]
    # KPI cards
    al = s["allocation"]
    kp = []
    if tot["review"] is not None:
        sub_m = (t("kpi_month_sub", delta=delta_span(tot["delta"], tot["pct"]), prev=esc(fmonth_name(prev))) if tot["prev"] else esc(t("kpi_month_sub_none", prev=fmonth_name(prev))))
        kp.append((money_short(tot["review"], cur), t("kpi_month", month=fmonth_name(review)), sub_m))
    if tot["mtd"] is not None:
        pace = tot["pace"]
        through = fdate(per["data_through"], True) if per.get("data_through") else fdate(per["today"], True)
        sub_t = (t("kpi_mtd_sub", d=esc(through), delta=delta_span((pace["current"] - pace["previous"]) if pace else None, pace["pct"] if pace else None), prev=esc(fmonth_name(review)))
                 if pace and pace["previous"] else esc(t("kpi_mtd_sub_nodelta", d=through)))
        kp.append((money_short(tot["mtd"], cur), t("kpi_mtd"), sub_t))
    if tot["forecast"] is not None:
        bc = s.get("budget_cov") or {"budgets": 0, "over": 0, "full": False}
        if s["budget_total"] and bc["full"]:
            ratio = pct(tot["forecast"], s["budget_total"])
            sub_f = t("kpi_forecast_budget", pct=f'<span class="{"up" if ratio >= 100 else "flat"}">{esc(fpct(ratio))}</span>', b=esc(money_short(s["budget_total"], cur)))
        elif bc["budgets"]:
            sub_f = (f'<span class="{"up" if bc["over"] else "flat"}">' + esc(tn("kpi_forecast_partial", bc["over"], k=bc["budgets"])) + "</span>")
        else:
            sub_f = esc(t("kpi_forecast_nobudget"))
        kp.append((money_short(tot["forecast"], cur), t("kpi_forecast", month=fmonth_name(current)), sub_f))
    n_actions = sum(1 for f in s["findings"] if (f["saving"] or 0) > 0)
    kp.append((money_short(s["savings"]["total"], cur), t("kpi_savings"), esc(tn("kpi_savings_sub", n_actions))))
    if al:
        label = t("kpi_alloc", tag=al["tags"][0]) if len(al["tags"]) == 1 else t("kpi_alloc_all", n=len(al["tags"]))
        kp.append((fpct(al["untagged_pct"]) if al["untagged_pct"] is not None else "\u2014", label,
                   esc(t("kpi_alloc_sub", v=money_short(al["total"] - al["all_tagged"], cur), total=money_short(al["total"], cur), month=fmonth_name(review)))))
    anom_sub = " \u00b7 ".join((tn("anom_days", len(s["unusual"])), tn("anom_jumps", len(s["jumps"])), tn("anom_new", len(s["new"]))))
    kp.append((str(len(s["unusual"]) + len(s["jumps"]) + len(s["new"])), t("kpi_anom"), esc(anom_sub)))
    kpi_html = "".join(f'<div class="kpi"><div class="v">{_kpi_value(val)}</div><div class="l">{esc(label)}</div><div class="s">{sub}</div></div>' for val, label, sub in kp[:6])
    pj = s["projects"]
    variants = [it for it in pj["items"] if it["variant"]]
    if sum(1 for it in variants if not it["unallocated"]) < 2:
        variants = []
    sec = [("actions", t("nav_actions"), len(s["actions"])), ("trend", t("nav_trend"), None), ("breakdown", t("nav_breakdown"), None),
           ("projects", t("nav_projects"), pj["named"]),
           ("changes", t("nav_changes"), len(s["unusual"]) + len(s["jumps"]) + len(s["new"])), ("budgets", t("nav_budgets"), len(s["budgets"])),
           ("savings", t("nav_savings"), sum(1 for x in s["savings"]["items"] if x["saving"] > 0) + len(s["commitment"]["items"])),
           ("allocation", t("nav_allocation"), None), ("register", t("nav_register"), len(s["findings"])), ("coverage", t("nav_coverage"), None)]
    nav = "".join(f'<a href="#{k}"' + (f' aria-label="{esc(lbl)} ({n})"' if n else "") + f'>{esc(lbl)}' + (f'<small aria-hidden="true">{n}</small>' if n else "") + "</a>" for k, lbl, n in sec)
    filt = ""
    if variants:
        opts = "".join(f'<option value="{it["id"]}">{esc(it["name"])}</option>' for it in variants)
        filt = (f'<div class="pf"><label for="pf">{esc(t("pf_label"))}</label><select id="pf" autocomplete="off"><option value="">{esc(t("pf_all"))}</option>{opts}</select></div>')

    def section(key, title, sub, body, mode=""):
        extra = ""
        if variants and mode == "chip":
            extra = f'<span class="pchip" hidden>{esc(t("pf_chip"))} <b></b></span>'
        elif variants and mode == "env":
            extra = pnote_html()
        return f'<section class="sec" id="{key}" aria-labelledby="h-{key}"><div class="sh"><h2 id="h-{key}">{esc(title)}</h2><p>{esc(sub)}</p>{extra}</div>{body}</section>'

    fmap = {f["id"]: f for f in s["findings"]}
    have = s["totals"]["review"] is not None
    body = (section("actions", t("s_actions"), t("s_actions_sub"),
                    pv_wrap(render_actions(s), variants, lambda it: render_actions(dict(s, actions=[fmap[x] for x in it["actions"] if x in fmap]), "act_none_p")), "chip") +
            section("trend", t("s_trend"), t("s_trend_sub", n=TREND_MONTHS, d=len(s["daily"])),
                    f'<div class="g2w">{render_monthly(s)}{render_daily(s)}</div>' if have else f'<p class="empty">{esc(t("lead_nodata"))}</p>', "env") +
            section("breakdown", t("s_breakdown"), t("s_breakdown_sub", month=fmonth_name(review), prev=fmonth_name(prev)),
                    pv_wrap(render_breakdown(s), variants, lambda it: render_breakdown(project_view(s, it))) if have else f'<p class="empty">{esc(t("lead_nodata"))}</p>', "chip") +
            section("projects", t("s_projects"), t("s_projects_sub", month=fmonth_name(review), prev=fmonth_name(prev), pct=fpct(pj["allocated_pct"] or 0)),
                    render_projects(s, variants)) +
            section("changes", t("s_changes"), t("s_changes_sub"), render_changes(s), "env") +
            section("budgets", t("s_budgets"), t("s_budgets_sub"), render_budgets(s), "env") +
            section("savings", t("s_savings"), t("s_savings_sub"), render_savings(s, variants), "chip") +
            section("allocation", t("s_allocation"), t("s_allocation_sub", month=fmonth_name(review), tags=", ".join(s["config"]["tags"]) or "\u2014"), render_allocation(s), "env") +
            section("register", t("s_register"), t("s_register_sub"), render_register(s, stem), "chip") +
            section("coverage", t("s_coverage"), t("s_coverage_sub"), render_coverage(s), "env"))
    banner = ""
    if variants:
        def banner_text(it):
            text_value = esc(tn("pf_banner", it["findings"], name="\x00", cost=money(it["cost"], cur), month=fmonth_name(review), share=fpct(it["share"] or 0)))
            return (f'<div class="pfi"><p>{text_value.replace(chr(0), "<b>" + esc(it["name"]) + "</b>")}<span>{esc(t("pf_scope"))}</span></p>'
                    f'<button class="btn" type="button" data-pclear>{esc(t("pf_clear"))}</button></div>')
        banner = '<div class="pfb" aria-live="polite">' + "".join(f'<div class="pv" data-pv="{it["id"]}" hidden>{banner_text(it)}</div>' for it in variants) + "</div>"
    title_text = (client + " \u00b7 " if client else "") + t("doc_title") + " \u00b7 " + fmonth(review)
    footer_text = title_text + f' \u00b7 {s["generated_utc"][:10]} \u00b7 {t("internal")}'
    page_css = ('@page{size:A4;margin:11mm 10mm 14mm;@bottom-left{content:' + css_text(footer_text) + ';font:8pt "Segoe UI",system-ui,sans-serif;color:#475467}'
                '@bottom-right{content:counter(page) " / " counter(pages);font:8pt "Segoe UI",system-ui,sans-serif;color:#475467}}')
    brand = (f'<img class="logo" src="{esc(logo)}" alt="{esc(client or t("product"))}">' if logo else WORDMARK.format(product=esc(t("product"))))
    top = (f'<header class="top"><div class="wrap">{brand}<span class="tt">{esc(t("doc_title"))}{(SEP + esc(client)) if client else ""}</span>'
           f'<div class="acts-top"><span class="chip">{esc(t("read_only"))}</span><button class="pbtn" type="button" data-print aria-label="{esc(t("print"))}">{ICON_PRINT}<span>{esc(t("print"))}</span></button></div></div></header>')
    hero = (f'<section class="hero" aria-labelledby="ttl"><div class="wrap hero-in"><div><h1 id="ttl">{esc(t("h1", month=fmonth(review)))}</h1>'
            f'<p class="lead">{s["headline"]["html"]}</p><div class="meta">{"".join(meta)}</div></div>{verdict}'
            f'<div class="dist"><div class="dist-h">{esc(t("dist"))} \u00b7 <b>{sum(counts.values())}</b></div><div class="track">{track}</div><div class="legend">{legend}</div></div></div></section>')
    return (f'<!doctype html><html lang="{esc(TEXT["_lang"])}"><head><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="{REPORT_CSP}">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1"><meta name="color-scheme" content="light"><meta name="referrer" content="no-referrer">'
            f'<title>{esc(title_text)}</title><style>{REPORT_CSS}{BRAND_CSS}{page_css}</style></head><body data-tbl="{esc(t("tbl"))}" data-scroll="{esc(t("scrolls"))}"><a class="skip" href="#main">{esc(t("skip"))}</a>'
            f'{top}<main id="main">{hero}<div class="wrap"><div class="kpis">{kpi_html}</div></div><nav class="secnav" aria-label="{esc(t("sections"))}"><div class="wrap">{filt}<div class="links">{nav}</div></div></nav>'
            f'<div class="wrap body">{banner}{body}</div></main><span id="newtab" class="vh">{esc(t("new_tab"))}</span><footer><div class="wrap"><span>{esc(t("footer", tool=TOOL_NAME, ver=TOOL_VERSION, gen=s["generated_utc"]))}</span>'
            f'<span>{esc(client + SEP if client else "")}{esc(t("internal"))}</span></div></footer><script>{REPORT_JS}</script></body></html>')


def _kpi_value(value):
    """Big number with the currency or unit as a smaller suffix."""
    m = re.fullmatch(r"(.+?)[ \u00a0]([A-Z]{3})", value or "")
    if m:
        return f'{esc(m.group(1))}<small>{esc(m.group(2))}</small>'
    return esc(value)


# ------------------------- files (HTML, JSON, 3 CSV) and native sharing links -------------------------
ARTIFACT_SUFFIXES = {"report_path": ".html", "snapshot_path": "-" + TEXT["file_snapshot"] + ".json",
                     "findings_csv_path": "-" + TEXT["csv_findings"] + ".csv", "costs_csv_path": "-" + TEXT["csv_costs"] + ".csv",
                     "projects_csv_path": "-" + TEXT["csv_projects"] + ".csv"}
STEM_RX = re.compile(re.escape(FILE_PREFIX) + r"-[0-9]{4}-[0-9]{2}-[0-9]{8}T[0-9]{6}Z-[0-9a-f]{8}")
THREAD_ROOT_RX = re.compile(r"/(?:root/sreagent|usr)/terminalRoot/tmp/ThreadFiles/([0-9a-fA-F-]{36})")
FINDING_FIELDS = ("severity", "category", "title", "evidence", "action", "scope", "project", "saving_month", "currency", "resource_id", "link", "id")
COST_FIELDS = ("resource_name", "resource_type", "resource_group", "subscription", "project", "region", "cost_review_month", "cost_previous_month", "change",
               "change_pct", "currency", "project_source", "resource_id")
PROJECT_FIELDS = ("project", "cost_review_month", "cost_previous_month", "change", "change_pct", "share_pct", "cost_month_to_date", "savings_month",
                  "findings", "resources", "resource_groups", "top_services", "top_resource_groups", "currency", "project_tag")


def csv_cell(value):
    if value is None:
        return ""
    if isinstance(value, float):
        value = f"{value:.2f}"
    text_value = str(value)
    if text_value[:1] in ("\t", "\r", "\n") or text_value.lstrip()[:1] in ("=", "+", "-", "@"):
        return "'" + text_value
    return text_value


def csv_document(rows, fields):
    stream = io.StringIO(newline="")
    writer = csv.writer(stream)
    writer.writerow(fields)
    for row in rows:
        writer.writerow([csv_cell(row.get(field)) for field in fields])
    return stream.getvalue()


def findings_rows(s):
    return [{"severity": f["severity"], "category": f["category"], "title": f["title"], "evidence": f["evidence"], "action": f["action"],
             "scope": f["scope"], "project": f.get("project", ""), "saving_month": f["saving"], "currency": s["currency"] if f["saving"] else "",
             "resource_id": f["resource_id"], "link": f["link"], "id": f["id"]} for f in s["findings"]]


def cost_rows(s, resources):
    return [{"resource_name": r["name"], "resource_type": r["type"], "resource_group": r["rg"], "subscription": r["sub"], "project": r.get("project", ""),
             "region": r["region"], "cost_review_month": r["cost"], "cost_previous_month": r["prev"], "change": r["delta"],
             "change_pct": round(r["pct"], 1) if r["pct"] is not None else "", "currency": s["currency"], "project_source": r.get("project_source", ""),
             "resource_id": r["id"] if "(not-a-resource)" not in r["id"] else ""}
            for r in resources]


def project_rows(s):
    pj = s["projects"]
    return [{"project": it["name"], "cost_review_month": it["cost"], "cost_previous_month": it["prev"], "change": it["delta"],
             "change_pct": round(it["pct"], 1) if it["pct"] is not None else "", "share_pct": round(it["share"], 1) if it["share"] is not None else "",
             "cost_month_to_date": it["mtd"], "savings_month": it["savings"], "findings": it["findings"], "resources": it["resources"],
             "resource_groups": it["resource_groups"], "top_services": "; ".join(x["name"] for x in it["by_service"][:3]),
             "top_resource_groups": "; ".join(x["name"] for x in it["by_rg"][:3]), "currency": s["currency"], "project_tag": ", ".join(pj["keys"])}
            for it in pj["items"]]


def artifact_directory():
    try:
        cwd = Path.cwd()
        root = cwd.resolve(strict=True)
        linked = any(part.is_symlink() or getattr(part, "is_junction", lambda: False)() for part in (cwd, *cwd.parents))
    except (OSError, RuntimeError) as exc:
        raise FinOpsError("unsafe_artifact_root", "The working directory must resolve to an existing folder.", "artifact_storage") from exc
    if root == Path(root.anchor) or not root.is_dir() or linked:
        raise FinOpsError("unsafe_artifact_root", "File system roots and symlinked or junction working directories are refused.", "artifact_storage")
    directory = root / OUTPUT_DIRECTORY
    if directory.is_symlink() or getattr(directory, "is_junction", lambda: False)() or (directory.exists() and directory.resolve() != directory):
        raise FinOpsError("unsafe_artifact_directory", "The output folder is a link or escapes the working directory.", "artifact_storage")
    return root, directory


def sharing_fields(root, paths, stem):
    result = {"sharing_mode": "local_files_only"}
    match = THREAD_ROOT_RX.fullmatch(root.as_posix())
    if match is None:
        return result
    try:
        if str(UUID(match.group(1))) != match.group(1).lower():
            return result
    except ValueError:
        return result
    links = {}
    for key, path in paths.items():
        if path.parent != root / OUTPUT_DIRECTORY or path.name != stem + ARTIFACT_SUFFIXES[key]:
            raise FinOpsError("unsafe_sharing_path", "Native links must point to the same run in the output folder.", "artifact_storage")
        links[key[:-len("_path")] + "_url"] = f"/api/files/tmp/ThreadFiles/{match.group(1)}/{OUTPUT_DIRECTORY}/{quote(path.name, safe='')}"
    return {"sharing_mode": "native_ui", **links}


def report_envelope(s, paths, root, stem):
    links = sharing_fields(root, paths, stem)
    out = {"status": s["status"], "operation": "report", "provenance": s["provenance"]}
    out.update({k: v for k, v in links.items() if k.endswith("_url")})
    out.update({key: str(path) for key, path in paths.items()})
    out.update({"sharing_mode": links["sharing_mode"], "artifact_status": "written", "review_month": s["periods"]["review_month"],
                "verdict": s["verdict"]["label"], "headline": s["headline"]["text"][:600], "kpis": kpis(s),
                "top_actions": [compact_finding(f) for f in s["actions"][:5]], "actions_total": len(s["actions"]), "coverage": compact_coverage(s),
                "read_only": True})
    while out["top_actions"] and response_bytes(out) > TRANSPORT_BYTES:
        out["top_actions"].pop()
    if response_bytes(out) > TRANSPORT_BYTES:
        out["coverage"].pop("issues", None)
        out["headline"] = out["headline"][:300]
    return out


def build_documents(s, resources, logo, stem):
    snap = dict(s, resources=s["resources"][:2000])
    contents = {"report_path": render_html(s, stem, logo).encode("utf-8"),
                "snapshot_path": json.dumps(snap, ensure_ascii=False, indent=1, allow_nan=False, default=str).encode("utf-8"),
                "findings_csv_path": csv_document(findings_rows(s), FINDING_FIELDS).encode("utf-8-sig"),
                "costs_csv_path": csv_document(cost_rows(s, resources), COST_FIELDS).encode("utf-8-sig"),
                "projects_csv_path": csv_document(project_rows(s), PROJECT_FIELDS).encode("utf-8-sig")}
    for key, data in contents.items():
        if len(data) > ARTIFACT_BYTES:
            raise FinOpsError("artifact_size_exceeded", f"{key} would exceed 4.8 MB; reduce MAX_SUBSCRIPTIONS.", "artifact_storage")
    return contents


def write_report(s, resources, logo):
    root, directory = artifact_directory()
    stem = f"{FILE_PREFIX}-{s['periods']['review_month']}-" + s["generated_utc"].replace("-", "").replace(":", "") + "-" + uuid4().hex[:8]
    if not STEM_RX.fullmatch(stem):
        raise FinOpsError("unsafe_filename", "Refused an unexpected output file name.", "artifact_storage")
    paths = {key: directory / (stem + suffix) for key, suffix in ARTIFACT_SUFFIXES.items()}
    response = report_envelope(s, paths, root, stem)
    contents = build_documents(s, resources, logo, stem)
    written, temporary = [], []
    try:
        directory.mkdir(exist_ok=True)
        if artifact_directory()[1] != directory or not directory.is_dir() or directory.is_symlink():
            raise FinOpsError("unsafe_artifact_directory", "The output folder changed after creation.", "artifact_storage")
        for key, data in contents.items():
            target = paths[key]
            if target.exists() or target.is_symlink():
                raise FinOpsError("artifact_collision", "An output file already exists; nothing is overwritten.", "artifact_storage")
            fd, name = tempfile.mkstemp(prefix=stem + "-", suffix=".tmp", dir=directory)
            temporary.append(Path(name))
            with os.fdopen(fd, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(name, target)
            temporary.remove(Path(name))
            written.append(target)
    except (OSError, FinOpsError) as exc:
        for path in temporary + written:
            try:
                path.unlink()
            except OSError:
                pass
        if isinstance(exc, FinOpsError):
            raise
        raise FinOpsError("artifact_write_failed", f"Could not write the report files ({type(exc).__name__}).", "artifact_storage") from exc
    return response


# ------------------------- self-test: a synthetic estate behind a fake transport (no network) -------------------------
SELF_TEST_SUBS = [("00000000-0000-0000-0000-0000000000a1", "Contoso Production"), ("00000000-0000-0000-0000-0000000000a2", "Contoso Development"),
                  ("00000000-0000-0000-0000-0000000000a3", "Contoso Shared Services")]
# (sub, resource group, service, provider/type, resource name, region, daily cost, pricing model, tags, pattern)
SELF_TEST_ESTATE = [
    (0, "rg-web-prod", "Azure App Service", "microsoft.web/serverfarms", "asp-web-prod", "eu west", 19.2, "OnDemand", "co", "flat"),
    (0, "rg-web-prod", "Azure Front Door Service", "microsoft.cdn/profiles", "afd-web-prod", "global", 6.4, "OnDemand", "cm", "flat"),
    (0, "rg-web-prod", "Storage", "microsoft.storage/storageaccounts", "stwebprod01", "eu west", 3.1, "OnDemand", "co", "flat"),
    (0, "rg-sql-prod", "SQL Database", "microsoft.sql/servers/databases", "sqlsrv-prod/sqldb-orders", "eu west", 13.5, "Reservation", "co", "flat"),
    (0, "rg-sql-prod", "SQL Database", "microsoft.sql/servers/databases", "sqlsrv-prod/sqldb-catalog", "eu west", 9.0, "OnDemand", "co", "flat"),
    (0, "MC_rg-aks-prod_aks-prod-weu_westeurope", "Virtual Machines", "microsoft.compute/virtualmachinescalesets", "aks-nodepool1-vmss", "eu west", 36.0, "OnDemand", "co", "growth"),
    (0, "MC_rg-aks-prod_aks-prod-weu_westeurope", "Load Balancer", "microsoft.network/loadbalancers", "kubernetes", "eu west", 1.6, "OnDemand", "co", "flat"),
    (0, "rg-aks-prod", "Azure Kubernetes Service", "microsoft.containerservice/managedclusters", "aks-prod-weu", "eu west", 2.4, "OnDemand", "co", "flat"),
    (0, "rg-data-prod", "Storage", "microsoft.storage/storageaccounts", "stdatalakeprod", "eu west", 9.3, "OnDemand", "c", "flat"),
    (0, "rg-data-prod", "Azure Data Factory v2", "microsoft.datafactory/factories", "adf-ingest-prod", "eu west", 4.1, "OnDemand", "c", "flat"),
    (0, "rg-ai-prod", "Foundry Tools", "microsoft.cognitiveservices/accounts", "aif-assistant-prod", "se central", 14.0, "OnDemand", "", "new"),
    (0, "rg-web-prod", "Azure App Service", "microsoft.web/serverfarms", "asp-legacy-prod", "eu west", 2.4, "OnDemand", "co", "flat"),
    (0, "rg-aks-prod", "Storage", "microsoft.compute/disks", "pvc-2b8e51f4-7c1a-4d0e-9a63-41c07fd9be2a", "eu west", 0.36, "OnDemand", "co", "flat"),
    (1, "rg-dev-apps", "Virtual Machines", "microsoft.compute/virtualmachines", "vm-dev-build01", "eu west", 4.6, "OnDemand", "e", "stopped"),
    (1, "rg-dev-apps", "Virtual Machines", "microsoft.compute/virtualmachines", "vm-dev-app01", "eu west", 8.8, "OnDemand", "e", "weekday"),
    (1, "rg-dev-apps", "Storage", "microsoft.storage/storageaccounts", "stdevapps01", "eu west", 1.2, "OnDemand", "e", "flat"),
    (1, "rg-dev-sandbox", "Virtual Machines", "microsoft.compute/virtualmachines", "vm-sandbox-gpu", "eu west", 5.2, "Spot", "", "weekday"),
    (1, "rg-dev-sandbox", "Storage", "microsoft.compute/disks", "disk-sandbox-old", "eu west", 0.66, "OnDemand", "", "flat"),
    (1, "rg-test-perf", "Bandwidth", "microsoft.network/publicipaddresses", "pip-loadtest", "eu west", 0.12, "OnDemand", "", "spike"),
    (1, "rg-test-perf", "Virtual Network", "microsoft.network/publicipaddresses", "pip-loadtest-02", "eu west", 0.12, "OnDemand", "", "flat"),
    (1, "rg-dev-apps", "Storage", "microsoft.compute/disks", "vm-dev-old_OsDisk_1", "eu west", 0.4, "OnDemand", "e", "flat"),
    (2, "rg-network-hub", "Azure Firewall", "microsoft.network/azurefirewalls", "afw-hub-weu", "eu west", 29.6, "OnDemand", "o", "flat"),
    (2, "rg-network-hub", "VPN Gateway", "microsoft.network/virtualnetworkgateways", "vgw-hub-weu", "eu west", 4.5, "OnDemand", "o", "flat"),
    (2, "rg-network-hub", "Azure Bastion", "microsoft.network/bastionhosts", "bas-hub-weu", "eu west", 4.6, "OnDemand", "o", "flat"),
    (2, "rg-network-hub", "Virtual Network", "microsoft.network/natgateways", "nat-hub-unused", "eu west", 1.08, "OnDemand", "o", "flat"),
    (2, "rg-network-hub", "Load Balancer", "microsoft.network/loadbalancers", "lb-hub-legacy", "eu west", 0.6, "OnDemand", "o", "flat"),
    (2, "rg-monitoring", "Log Analytics", "microsoft.operationalinsights/workspaces", "log-platform-weu", "eu west", 7.2, "OnDemand", "co", "flat"),
    (2, "rg-security", "Microsoft Defender for Cloud", "microsoft.security/pricings", "VirtualMachines", "global", 6.1, "OnDemand", "", "flat"),
    (2, "rg-backup", "Backup", "microsoft.recoveryservices/vaults", "rsv-platform-weu", "eu west", 3.3, "OnDemand", "co", "flat"),
    (2, "rg-backup", "Storage", "microsoft.compute/snapshots", "snap-sql-migration-2025", "eu west", 0.21, "OnDemand", "", "flat"),
]
SELF_TEST_TAGS = {"c": {"costcenter": "CC-1001"}, "co": {"costcenter": "CC-1001", "owner": "web-platform", "environment": "prod"},
                  "cm": {"costcenter": "CC-1001", "owner": "web-platform", "environment": "prod", "project": "Marketing site"},
                  "e": {"environment": "dev", "owner": "dev-team"}, "o": {"owner": "network-team", "environment": "shared"}}
SELF_TEST_RG_TAGS = {"rg-web-prod": {"project": "E-commerce web"}, "rg-sql-prod": {"project": "E-commerce web"}, "rg-aks-prod": {"project": "Customer API"},
                     "rg-data-prod": {"costcenter": "CC-2002", "owner": "data-team", "project": "Data platform"}, "rg-ai-prod": {"project": "AI assistant"},
                     "rg-network-hub": {"project": "Shared platform"}, "rg-monitoring": {"project": "Shared platform"},
                     "rg-security": {"project": "Shared platform"}, "rg-backup": {"project": "Shared platform"}}
SELF_TEST_AKS = "/subscriptions/{sub}/resourcegroups/rg-aks-prod/providers/microsoft.containerservice/managedclusters/aks-prod-weu"


def self_test_estate(periods):
    """Deterministic daily cost lines (sub, rg, service, pricing, rid, location, day, cost) relative to today."""
    lines = []
    start = periods["trend_start"]
    review_start, month_start = periods["review_start"], periods["month_start"]
    spike_day = review_start + timedelta(days=16)
    for i, (sx, rg, svc, rtype, name, loc, daily, model, tags, pattern) in enumerate(SELF_TEST_ESTATE):
        sub = SELF_TEST_SUBS[sx][0]
        prov, _, rest = rtype.partition("/")
        if "/" in rest:
            segs = rest.split("/")
            names_ = name.split("/")
            rid = f"/subscriptions/{sub}/resourcegroups/{rg}/providers/{prov}/" + "/".join(f"{segs[k]}/{names_[k]}" for k in range(len(segs)))
        else:
            rid = f"/subscriptions/{sub}/resourcegroups/{rg}/providers/{rtype}/{name}"
        d = start
        while d <= periods["today"]:
            months_back = (month_start.year - d.year) * 12 + month_start.month - d.month
            factor = 1.0 + 0.012 * ((d.toordinal() * (i + 7)) % 11 - 5) - 0.025 * max(0, months_back - 1)
            cost = daily * factor
            if pattern == "weekday" and d.weekday() >= 5:
                cost *= 0.55
            if pattern == "growth" and d >= review_start:
                cost *= 1.42
            if pattern == "new" and d < review_start + timedelta(days=9):
                cost = 0.0
            if pattern == "spike" and d == spike_day:
                cost += 182.0
            if pattern == "stopped" and d >= review_start - timedelta(days=20):
                cost = daily * 1.0
            if cost > 0:
                lines.append((sub, rg, svc, model, rid.lower(), loc, d, round(cost, 4), tags))
            d += timedelta(days=1)
    return lines


class FakeResponse:
    def __init__(self, payload, status=200, headers=None):
        self.status, self.headers, self._data = status, headers or {}, json.dumps(payload).encode("utf-8")

    def read(self, size=-1):
        return self._data if size < 0 else self._data[:size]

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class SelfTestOpener:
    """Answers the tool's read-only requests from the synthetic estate; never opens a socket."""

    def __init__(self, periods):
        self.periods = periods
        self.lines = self_test_estate(periods)
        self.calls = []

    def open(self, request, timeout=None):
        url = request.full_url
        path = urlsplit(url).path.lower()
        body = json.loads(request.data) if request.data else {}
        self.calls.append((request.get_method(), path))
        if path.endswith("/microsoft.resourcegraph/resources"):
            return FakeResponse({"data": self.arg(body.get("query") or ""), "count": 0})
        if path.endswith("/microsoft.costmanagement/query"):
            return FakeResponse(self.cost(path.split("/")[2], body))
        if path.endswith("/microsoft.consumption/budgets"):
            return FakeResponse({"value": self.budgets(path.split("/")[2] if path.startswith("/subscriptions/") else "")})
        if path.endswith("/microsoft.consumption/tags"):
            return FakeResponse({"id": path + "/self-test", "name": "self-test", "type": "Microsoft.Consumption/tags",
                                 "properties": {"tags": [{"key": k, "value": []} for k in ("project", "costcenter", "owner", "environment")]}})
        raise HTTPError(url, 404, "not found", {}, None)

    @staticmethod
    def cost_tag(rid, rg, key):
        """Tags as Cost Management records them: only on the resource itself (no inheritance), plus one group whose tag left ARG."""
        if key.casefold() != "project":
            return ""
        return "Load testing" if rg == "rg-test-perf" else "Marketing site" if rid.endswith("/afd-web-prod") else ""

    def cost(self, sub, body):
        ds = body["dataset"]
        groups = [(g.get("type") or "Dimension", g["name"]) for g in ds.get("grouping", [])]
        start = parse_day(body["timePeriod"]["from"])
        end = parse_day(body["timePeriod"]["to"])
        agg = defaultdict(float)
        for (lsub, rg, svc, model, rid, loc, d, cost, _tags) in self.lines:
            if lsub != sub or not start <= d <= end:
                continue
            values = {"ResourceGroupName": rg, "ServiceName": svc, "PricingModel": model, "ResourceId": rid, "ResourceLocation": loc}
            when = f"{d.year:04d}-{d.month:02d}-01T00:00:00" if ds.get("granularity") == "Monthly" else int(d.strftime("%Y%m%d"))
            key = []
            for gtype, gname in groups:
                if gtype == "TagKey":
                    value = self.cost_tag(rid, rg, gname)
                    key += [gname.lower() if value else "", value]
                else:
                    key.append(values[gname])
            agg[(when,) + tuple(key)] += cost
        date_col = "BillingMonth" if ds.get("granularity") == "Monthly" else "UsageDate"
        names_ = [n for gtype, gname in groups for n in (("TagKey", "TagValue") if gtype == "TagKey" else (gname,))]
        cols = [{"name": "Cost", "type": "Number"}, {"name": date_col, "type": "Datetime"}] + [{"name": g, "type": "String"} for g in names_] + [{"name": "Currency", "type": "String"}]
        rows = [[round(v, 4), k[0]] + list(k[1:]) + ["USD"] for k, v in sorted(agg.items(), key=lambda kv: str(kv[0]))]
        return {"properties": {"columns": cols, "rows": rows, "nextLink": None}}

    def budgets(self, sub):
        today = self.periods["today"]
        if sub == SELF_TEST_SUBS[0][0]:
            spent = sum(x[7] for x in self.lines if x[0] == sub and x[6] >= self.periods["month_start"])
            return [{"id": f"/subscriptions/{sub}/providers/Microsoft.Consumption/budgets/budget-prod-monthly", "name": "budget-prod-monthly",
                     "properties": {"amount": 4200.0, "timeGrain": "Monthly", "timePeriod": {"startDate": "2026-01-01T00:00:00Z"},
                                    "currentSpend": {"amount": round(spent, 2), "unit": "USD"},
                                    "forecastSpend": {"amount": round(spent / max(1, today.day) * calendar.monthrange(today.year, today.month)[1] * 1.04, 2), "unit": "USD"},
                                    "notifications": {"a80": {"enabled": True, "threshold": 80, "thresholdType": "Actual"},
                                                      "f100": {"enabled": True, "threshold": 100, "thresholdType": "Forecasted"}}}}]
        if sub == SELF_TEST_SUBS[1][0]:
            return [{"id": f"/subscriptions/{sub}/providers/Microsoft.Consumption/budgets/budget-dev", "name": "budget-dev",
                     "properties": {"amount": 1100.0, "timeGrain": "Monthly", "currentSpend": {"amount": 236.4, "unit": "USD"},
                                    "forecastSpend": {"amount": 742.0, "unit": "USD"},
                                    "notifications": {"a90": {"enabled": True, "threshold": 90, "thresholdType": "Actual"}}}}]
        return []

    def arg(self, query):
        subs = SELF_TEST_SUBS
        if query.startswith("resourcecontainers"):
            rows = [{"id": f"/subscriptions/{s}", "type": "microsoft.resources/subscriptions", "name": n, "subscriptionId": s, "tags": {}, "state": "Enabled"} for s, n in subs]
            seen = set()
            for (sx, rg, *_rest) in SELF_TEST_ESTATE:
                if (sx, rg) in seen:
                    continue
                seen.add((sx, rg))
                rows.append({"id": f"/subscriptions/{subs[sx][0]}/resourcegroups/{rg.lower()}", "type": "microsoft.resources/subscriptions/resourcegroups",
                             "name": rg, "subscriptionId": subs[sx][0], "resourceGroup": rg, "tags": dict(SELF_TEST_RG_TAGS.get(rg, {})),
                             "managedBy": SELF_TEST_AKS.format(sub=subs[sx][0]) if rg.startswith("MC_") else ""})
            return rows
        if query.startswith("resources | where isnotempty(tags)"):
            out, seen = [], set()
            for (sub, rg, svc, model, rid, loc, d, cost, tags) in self.lines:
                if tags and rid not in seen:
                    seen.add(rid)
                    out.append({"id": rid, "tags": SELF_TEST_TAGS[tags]})
            return out
        if query.startswith("advisorresources"):
            s0, s1 = subs[0][0], subs[1][0]
            ri = lambda term, look, amt: {"id": f"/subscriptions/{s0}/providers/microsoft.advisor/recommendations/ri-{term}-{look}", "subscriptionId": s0, "resourceGroup": "",
                                          "impact": "High", "problem": "Consider virtual machine reserved instance to save over the on-demand costs",
                                          "typeId": "84b1a508-fc21-49da-979e-96894f1665df", "field": "Microsoft.Subscriptions/subscriptions", "value": s0,
                                          "resourceId": f"/subscriptions/{s0}", "ext": {"recommendationSubCategory": "Reservations", "term": term, "lookbackPeriod": look,
                                                                                    "savingsAmount": str(amt), "savingsCurrency": "USD", "vmSize": "Standard_D4s_v5",
                                                                                    "region": "westeurope", "scope": "Single", "displayQty": "3", "reservedResourceType": "virtualmachines"}}
            sp = {"id": f"/subscriptions/{s0}/providers/microsoft.advisor/recommendations/sp-1", "subscriptionId": s0, "resourceGroup": "", "impact": "High",
                  "problem": "Consider purchasing a savings plan to unlock lower prices", "typeId": "89515250-1243-43d1-b4e7-f9437cedffd8",
                  "resourceId": f"/subscriptions/{s0}", "ext": {"recommendationSubCategory": "SavingsPlans", "term": "P1Y", "lookbackPeriod": "30",
                                                            "savingsAmount": "238", "savingsCurrency": "USD", "scope": "Single"}}
            vm = f"/subscriptions/{s1}/resourcegroups/rg-dev-apps/providers/microsoft.compute/virtualmachines/vm-dev-app01"
            rs = {"id": f"/subscriptions/{s1}/providers/microsoft.advisor/recommendations/rs-1", "subscriptionId": s1, "resourceGroup": "rg-dev-apps", "impact": "Medium",
                  "problem": "Right-size or shutdown underutilized virtual machines", "typeId": "e10b1381-5f0a-47ff-8c7b-37bd13d7c974", "field": "Microsoft.Compute/virtualMachines",
                  "value": "vm-dev-app01", "resourceId": vm, "ext": {"savingsAmount": "118", "savingsCurrency": "USD", "currentSku": "Standard_D8s_v5", "targetSku": "Standard_D4s_v5"}}
            disk = f"/subscriptions/{s1}/resourcegroups/rg-dev-sandbox/providers/microsoft.compute/disks/disk-sandbox-old"
            ud = {"id": f"/subscriptions/{s1}/providers/microsoft.advisor/recommendations/ud-1", "subscriptionId": s1, "resourceGroup": "rg-dev-sandbox", "impact": "Medium",
                  "problem": "Review unattached disks and decide whether you still need them", "typeId": "48eda464-1485-4dcf-a674-d0905df5054a",
                  "field": "Microsoft.Compute/disks", "value": "disk-sandbox-old", "resourceId": disk, "ext": {}}
            return [ri("P1Y", "30", 210), ri("P3Y", "30", 352), ri("P1Y", "7", 205), sp, rs, ud]
        if query.startswith("resources | where type in~"):
            s0x, s1, s2 = subs[0][0], subs[1][0], subs[2][0]
            base = lambda sub, rg, prov, name: f"/subscriptions/{sub}/resourcegroups/{rg}/providers/{prov}/{name}"
            today = self.periods["today"]
            return [
                {"id": base(s1, "rg-dev-sandbox", "microsoft.compute/disks", "disk-sandbox-old"), "name": "disk-sandbox-old", "type": "microsoft.compute/disks",
                 "resourceGroup": "rg-dev-sandbox", "subscriptionId": s1, "location": "westeurope", "check": "unattached_disk", "sku": "Premium_LRS", "size": 128, "tags": {}},
                {"id": base(s1, "rg-dev-sandbox", "microsoft.compute/disks", "vm-dr_osdisk-asrreplica"), "name": "vm-dr_osdisk-asrreplica", "type": "microsoft.compute/disks",
                 "resourceGroup": "rg-dev-sandbox", "subscriptionId": s1, "location": "westeurope", "check": "unattached_disk", "sku": "Standard_LRS", "size": 64, "tags": {}},
                {"id": base(s0x, "rg-aks-prod", "microsoft.compute/disks", "pvc-2b8e51f4-7c1a-4d0e-9a63-41c07fd9be2a"), "name": "pvc-2b8e51f4-7c1a-4d0e-9a63-41c07fd9be2a",
                 "type": "microsoft.compute/disks", "resourceGroup": "rg-aks-prod", "subscriptionId": s0x, "location": "westeurope", "check": "unattached_disk",
                 "sku": "Premium_LRS", "size": 64, "tags": {}},
                {"id": base(s1, "rg-test-perf", "microsoft.network/publicipaddresses", "pip-loadtest-02"), "name": "pip-loadtest-02", "type": "microsoft.network/publicipaddresses",
                 "resourceGroup": "rg-test-perf", "subscriptionId": s1, "location": "westeurope", "check": "unused_public_ip", "sku": "Standard", "tags": {}},
                {"id": base(s1, "rg-dev-apps", "microsoft.compute/virtualmachines", "vm-dev-build01"), "name": "vm-dev-build01", "type": "microsoft.compute/virtualmachines",
                 "resourceGroup": "rg-dev-apps", "subscriptionId": s1, "location": "westeurope", "check": "stopped_vm", "vmSize": "Standard_D4s_v5", "tags": {}},
                {"id": base(s1, "rg-dev-apps", "microsoft.compute/virtualmachines", "vm-dev-old"), "name": "vm-dev-old", "type": "microsoft.compute/virtualmachines",
                 "resourceGroup": "rg-dev-apps", "subscriptionId": s1, "location": "westeurope", "check": "deallocated_vm", "vmSize": "Standard_B2ms",
                 "osDisk": base(s1, "rg-dev-apps", "microsoft.compute/disks", "vm-dev-old_osdisk_1"), "dataDisks": [], "tags": {}},
                {"id": base(subs[0][0], "rg-web-prod", "microsoft.web/serverfarms", "asp-legacy-prod"), "name": "asp-legacy-prod", "type": "microsoft.web/serverfarms",
                 "resourceGroup": "rg-web-prod", "subscriptionId": subs[0][0], "location": "westeurope", "check": "empty_plan", "sku": "S1", "tier": "Standard", "tags": {}},
                {"id": base(s2, "rg-network-hub", "microsoft.network/networkinterfaces", "nic-old-jumpbox"), "name": "nic-old-jumpbox", "type": "microsoft.network/networkinterfaces",
                 "resourceGroup": "rg-network-hub", "subscriptionId": s2, "location": "westeurope", "check": "orphaned_nic", "tags": {}},
                {"id": base(s2, "rg-backup", "microsoft.compute/snapshots", "snap-sql-migration-2025"), "name": "snap-sql-migration-2025", "type": "microsoft.compute/snapshots",
                 "resourceGroup": "rg-backup", "subscriptionId": s2, "location": "westeurope", "check": "old_snapshot", "size": 256,
                 "created": (today - timedelta(days=214)).isoformat() + "T08:00:00Z", "tags": {}},
                {"id": base(s2, "rg-network-hub", "microsoft.network/loadbalancers", "lb-hub-legacy"), "name": "lb-hub-legacy", "type": "microsoft.network/loadbalancers",
                 "resourceGroup": "rg-network-hub", "subscriptionId": s2, "location": "westeurope", "check": "idle_load_balancer", "sku": "Standard", "tags": {}},
                {"id": base(s2, "rg-network-hub", "microsoft.network/natgateways", "nat-hub-unused"), "name": "nat-hub-unused", "type": "microsoft.network/natgateways",
                 "resourceGroup": "rg-network-hub", "subscriptionId": s2, "location": "westeurope", "check": "idle_nat_gateway", "sku": "Standard", "tags": {}},
            ]
        return []


# ------------------------- entry point -------------------------
def run_review(config, now, opener=None, provenance="LIVE"):
    started = time.monotonic()
    periods = review_periods(now)
    identity = None
    try:
        if opener is None:
            identity = Identity(config["client_id"])
            identity.token()
            token_source = identity.token
        else:
            token_source = lambda: "self-test"
        reader = Reader(token_source, started + MAX_COLLECTION_SECONDS, opener)
        raw = collect(reader, config, periods)
        stats = {"requests": reader.requests, "throttled": reader.throttled, "waited": reader.waited, "seconds": round(time.monotonic() - started, 1),
                 "identity": identity.check if identity else "self-test (no identity)"}
        snapshot = build_snapshot(raw, config, periods, now, stats, provenance)
        if provenance != "LIVE":
            for src in snapshot["coverage"]["sources"]:
                if src["status"] == "complete":
                    src["status"] = "simulated"
        return snapshot
    finally:
        if identity:
            identity.close()


def resources_for_csv(snapshot):
    return snapshot.get("resources") or []


def main(operation: str = "report", view: str = "summary", limit: int = 15, project: str = "", project_tag: str = "") -> dict:
    """Read-only monthly Azure FinOps review of the configured subscriptions (or management group), with cost per project.

    operation: report (HTML + JSON snapshot + findings CSV + cost-by-resource CSV + cost-by-project CSV), query (bounded chat view, no files)
               or self_test (the full report from built-in SIMULATED data, no network, no configuration needed).
    view (query only): summary | actions | anomalies | budgets | savings | resources | projects | allocation | coverage.
    limit (query only): 1-50 rows.
    project (query only): one project name; summary, actions, savings, resources and projects then show that project only.
    project_tag: tag name(s) that name the project for this run, comma-separated in priority order; overrides PROJECT_TAG_KEYS and detection.
    """
    try:
        params = validate_parameters(operation, view, limit, project, project_tag)
        self_test = params["operation"] == "self_test"
        config = validate_config(self_test=self_test)
        if params["project_tag"]:
            config = dict(config, project_keys=params["project_tag"], project_source="parameter")
        now = utc_now()
        if self_test:
            snapshot = run_review(dict(config, subscriptions=[s for s, _ in SELF_TEST_SUBS]), now, SelfTestOpener(review_periods(now)), "SIMULATED")
        else:
            snapshot = run_review(config, now)
        if params["operation"] == "query":
            return query_view(snapshot, params)
        return write_report(snapshot, resources_for_csv(snapshot), config["logo"])
    except FinOpsError as exc:
        return {"status": "error", "operation": operation if operation in OPERATIONS else "report", "error": exc.public(),
                "artifact_status": "not_written", "read_only": True}
    except Exception as exc:
        return {"status": "error", "operation": operation if operation in OPERATIONS else "report",
                "error": {"code": "unexpected_error", "message": f"Unexpected {type(exc).__name__}; no files were written. The tool is read-only and changed nothing.",
                          "source": "review", "http_status": None}, "artifact_status": "not_written", "read_only": True}
