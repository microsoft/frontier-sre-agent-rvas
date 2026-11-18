"""Read-only Azure Operations, Incidents, Anomalies, and Recommended Actions Digest engine. Build standalone tool with build_tool.py."""

import base64
import binascii
import copy
import csv
import hashlib
import io
import json
import math
import os
import re
import ssl
import statistics
import tempfile
import time
import warnings
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, quote, unquote, urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, HTTPSHandler, Request, build_opener
from uuid import UUID, uuid4


SUBSCRIPTION_ID = "<YOUR_SUBSCRIPTION_ID>"
MANAGED_IDENTITY_CLIENT_ID = "<YOUR_MANAGED_IDENTITY_CLIENT_ID>"
APPROVED_LOG_WORKSPACES = [
    {
        "name": "<WORKSPACE_NAME>",
        "customer_id": "<WORKSPACE_GUID>",
        "resource_group": "<RESOURCE_GROUP>",
    }
]
CLIENT_NAME = "Customer"
# Here goes the customer's logo, privately configured as a validated PNG/JPEG
# data URI. Keep generic Git source empty. Use adjacent strings <10K per line.
CLIENT_LOGO_DATA_URI = ""
CLIENT_LOGO_ALT = "Authorized customer logo"
OUTPUT_DIRECTORY = "operations-digest-reports"

ARM_ORIGIN = "https://management.azure.com"
LOGS_ORIGIN = "https://api.loganalytics.io"
ARM_TOKEN_AUDIENCES = (
    "https://management.azure.com",
    "https://management.core.windows.net",
)
LOGS_TOKEN_AUDIENCES = (
    "https://api.loganalytics.io",
    "https://api.loganalytics.azure.com",
)
ARG_API_VERSION = "2022-10-01"
RESOURCE_HEALTH_API_VERSION = "2022-10-01"
ADVISOR_API_VERSION = "2023-01-01"

TRANSPORT_BYTES = 3500
ARTIFACT_BYTES = 4_800_000
HTTP_BYTES = 12_000_000
MAX_PAGES = 25
MAX_ROWS = 10_000
MAX_WORKSPACES = 10
MAX_COLLECTION_SECONDS = 180
MAX_HTTP_ATTEMPTS = 200
MAX_LOGO_BYTES = 100_000
MAX_LOGO_DIMENSION = 2048

OPERATIONS = ("report", "query")
PERIODS = ("previous_month", "last_30d", "last_7d", "last_24h")
VIEWS = ("summary", "incidents", "anomalies", "actions", "resources", "advisor", "coverage")
CATEGORIES = (
    "all",
    "native_alert",
    "service_health",
    "extension_failure",
    "connectivity_posture",
    "telemetry_anomaly",
    "advisor_recommendation",
)
SEVERITIES = ("all", "critical", "high", "medium", "low")
HORIZONS = ("immediate_24h", "short_term_7d", "monthly_cycle")
SOURCE_STATUSES = ("complete", "partial", "denied", "error", "not_configured")

ESTATE_RESOURCE_TYPES = (
    "microsoft.compute/virtualmachines",
    "microsoft.compute/virtualmachinescalesets",
    "microsoft.hybridcompute/machines",
    "microsoft.kubernetes/connectedclusters",
    "microsoft.containerservice/managedclusters",
    "microsoft.app/containerapps",
    "microsoft.web/sites",
    "microsoft.web/serverfarms",
    "microsoft.storage/storageaccounts",
    "microsoft.keyvault/vaults",
    "microsoft.sql/servers/databases",
    "microsoft.dbforpostgresql/flexibleservers",
    "microsoft.cache/redis",
)
EXTENSION_RESOURCE_TYPES = (
    "microsoft.hybridcompute/machines/extensions",
    "microsoft.compute/virtualmachines/extensions",
)
CRITICAL_EXTENSION_TOKENS = (
    "mde",
    "defender",
    "aadlogin",
    "aadsshlogin",
    "azuremonitor",
    "ama",
    "omsagent",
    "dependencyagent",
    "keyvault",
    "policy",
)

SEVERITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3}
SEVERITY_LABELS = {
    "critical": "Critical",
    "high": "High",
    "medium": "Medium",
    "low": "Low",
}
CATEGORY_LABELS = {
    "native_alert": "Azure Monitor native alert",
    "service_health": "Azure Service Health communication",
    "extension_failure": "VM / Azure Arc extension failure",
    "connectivity_posture": "Control plane / connectivity anomaly",
    "telemetry_anomaly": "Telemetry statistical / threshold anomaly",
    "advisor_recommendation": "Correlated Azure Advisor recommendation",
}
HORIZON_LABELS = {
    "immediate_24h": "Immediate <24h",
    "short_term_7d": "Short term 1-7 days",
    "monthly_cycle": "Monthly cycle",
}
EFFORT_LABELS = {
    "low": "Low",
    "medium": "Medium",
    "high": "High",
}

# BEGIN BUILD-TIME ASSETS
HTML_TEMPLATE = (
    '<!DOCTYPE html>\n<html lang="en" data-theme="light">\n<head>\n<meta charset="utf-8">\n<meta name="viewpo'
    'rt" content="width=device-width, initial-scale=1">\n<meta http-equiv="Content-Security-Policy" conten'
    't="default-src \'none\'; img-src data:; style-src \'unsafe-inline\'; script-src \'unsafe-inline\'; base-ur'
    'i \'none\'; form-action \'none\'; connect-src \'none\'">\n<title>Operations, incidents, anomalies, and reco'
    'mmended actions report</title>\n<style>\n:root {\n  --brand-orange: #FF4E00;\n  --brand-orange-alt: #FC4'
    'C00;\n  --brand-orange-text: #C23800;\n  --brand-orange-wash: #FFF2EC;\n  --brand-orange-line: #FFC9AE;'
    '\n  --slate-topbar: #141B24;\n  --slate-header: #1C2532;\n  --bg-page: #F6F5F2;\n  --bg-panel: #FFFFFF;\n'
    '  --bg-subtle: #F1EEE8;\n  --bg-row-hover: #FAF8F4;\n  --ink-primary: #141B24;\n  --ink-secondary: #3E4'
    'C5E;\n  --ink-muted: #5A687A;\n  --border-hairline: #DEDCD6;\n  --border-strong: #9AA5B5;\n  --hero-bg: '
    '#1C2532;\n  --hero-deep: #141B24;\n  --hero-ink: #E6EBF1;\n  --hero-muted: #C3CCD8;\n  --hero-line: rgba'
    '(255, 255, 255, 0.18);\n  --sev-critical: #B42318;\n  --sev-critical-bg: #FEE4E2;\n  --sev-critical-bar'
    ': #D92D20;\n  --sev-high: #B93815;\n  --sev-high-bg: #FFEAD5;\n  --sev-high-bar: #EF6820;\n  --sev-mediu'
    'm: #93370D;\n  --sev-medium-bg: #FEF0C7;\n  --sev-medium-bar: #F79009;\n  --sev-low: #175CD3;\n  --sev-l'
    'ow-bg: #D1E9FF;\n  --sev-low-bar: #2E90FA;\n  --sev-info: #344054;\n  --sev-info-bg: #EAECF0;\n  --sev-i'
    'nfo-bar: #98A2B3;\n  --ok: #067647;\n  --ok-bg: #DCFAE6;\n  --note-bg: #FFFAEB;\n  --note-line: #FEDF89;'
    '\n  --note-ink: #7A2E0E;\n  --chart: #3E4C5E;\n  --edge: rgba(20, 27, 36, 0.18);\n  --shadow-card: 0 1px'
    " 2px rgba(20, 27, 36, 0.04), 0 6px 20px rgba(20, 27, 36, 0.06);\n  --font-sans: 'Outfit', 'Segoe UI',"
    " system-ui, -apple-system, sans-serif;\n  --font-mono: 'Consolas', ui-monospace, 'Cascadia Mono', mon"
    'ospace;\n  color-scheme: light;\n}\n\nhtml[data-theme="dark"] {\n  --brand-orange: #FF5C14;\n  --brand-ora'
    'nge-alt: #FF6B2B;\n  --brand-orange-text: #FF8854;\n  --brand-orange-wash: #2B1A12;\n  --brand-orange-l'
    'ine: #6E3417;\n  --slate-topbar: #0B0F15;\n  --slate-header: #121923;\n  --bg-page: #0F141B;\n  --bg-pan'
    'el: #161E29;\n  --bg-subtle: #1D2736;\n  --bg-row-hover: #1B2431;\n  --ink-primary: #F3F5F8;\n  --ink-se'
    'condary: #CBD5E1;\n  --ink-muted: #9AA8BA;\n  --border-hairline: #2A3647;\n  --border-strong: #475569;\n'
    '  --hero-bg: #121923;\n  --hero-deep: #0B0F15;\n  --hero-muted: #B8C3D1;\n  --hero-line: rgba(255, 255,'
    ' 255, 0.14);\n  --sev-critical: #FDA29B;\n  --sev-critical-bg: rgba(217, 45, 32, 0.22);\n  --sev-high: '
    '#F9B87F;\n  --sev-high-bg: rgba(239, 104, 32, 0.22);\n  --sev-medium: #FEC84B;\n  --sev-medium-bg: rgba'
    '(247, 144, 9, 0.18);\n  --sev-low: #84CAFF;\n  --sev-low-bg: rgba(46, 144, 250, 0.2);\n  --sev-info: #D'
    '0D5DD;\n  --sev-info-bg: rgba(152, 162, 179, 0.2);\n  --ok: #75E0A7;\n  --ok-bg: rgba(23, 178, 106, 0.1'
    '8);\n  --note-bg: #2A2212;\n  --note-line: #6B571E;\n  --note-ink: #FDE68A;\n  --chart: #9AA8BA;\n  --edg'
    'e: rgba(0, 0, 0, 0.55);\n  --shadow-card: 0 1px 2px rgba(0, 0, 0, 0.3), 0 8px 24px rgba(0, 0, 0, 0.25'
    ');\n  color-scheme: dark;\n}\n\n*, *::before, *::after { box-sizing: border-box; }\nhtml { scroll-behavio'
    'r: smooth; scrollbar-color: var(--border-strong) var(--bg-page); -webkit-text-size-adjust: 100%; }\nb'
    'ody { margin: 0; background: var(--bg-page); color: var(--ink-primary); font: 15px/1.55 var(--font-s'
    'ans); font-variant-numeric: tabular-nums; -webkit-font-smoothing: antialiased; }\n::selection { backg'
    'round: #FFD9C7; color: #141B24; }\na { color: var(--brand-orange-text); text-decoration-thickness: 1p'
    'x; text-underline-offset: 3px; }\na:hover { text-decoration-thickness: 2px; }\n:focus-visible { outlin'
    'e: 2px solid var(--brand-orange); outline-offset: 2px; }\nbutton, input, select { font: inherit; colo'
    'r: inherit; }\ncode { font-family: var(--font-mono); font-size: 0.86em; }\np, li { text-wrap: pretty; '
    '}\nh2, h3 { text-wrap: balance; }\nsvg { flex: none; }\n.sr-only { position: absolute; width: 1px; heig'
    'ht: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; borde'
    'r: 0; }\n.skip-link { position: absolute; left: 16px; top: -60px; z-index: 60; padding: 8px 14px; bor'
    'der-radius: 8px; background: var(--bg-panel); color: var(--ink-primary); font-weight: 600; box-shado'
    'w: var(--shadow-card); }\n.skip-link:focus { top: 12px; }\n.print-only { display: none; }\n.print-only:'
    'empty { display: none !important; }\n\n/* Top bar */\n.topbar { position: sticky; top: 0; z-index: 40; '
    'background-color: var(--slate-topbar); color: #FFFFFF; border-bottom: 2px solid var(--brand-orange);'
    ' }\n.topbar-inner { max-width: 1400px; min-height: 58px; margin: 0 auto; padding: 8px 40px; display: '
    'flex; align-items: center; gap: 16px; }\n.brand { display: flex; align-items: center; gap: 12px; min-'
    'width: 0; color: #FFFFFF; text-decoration: none; }\n.client-plaque { flex-shrink: 0; display: inline-'
    'flex; align-items: center; gap: 8px; min-height: 32px; padding: 4px 10px; border-radius: 6px; backgr'
    'ound: #FFFFFF; color: #141B24; }\n.client-plaque img { display: block; max-height: 24px; width: auto;'
    ' }\n.client-name-label { font-size: 13px; font-weight: 700; letter-spacing: 0.02em; }\n.brand-text { d'
    'isplay: flex; flex-direction: column; min-width: 0; line-height: 1.2; }\n.brand-text b { font-size: 1'
    '5px; font-weight: 700; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }\n.brand-text'
    ' span { font-size: 12.5px; color: #C3CCD8; white-space: nowrap; overflow: hidden; text-overflow: ell'
    'ipsis; }\n.section-nav { display: flex; gap: 2px; margin-left: 12px; }\n.section-nav a { padding: 7px '
    '10px; border-radius: 6px; color: #D5DCE5; font-size: 13.5px; font-weight: 600; text-decoration: none'
    '; white-space: nowrap; }\n.section-nav a:hover { background: rgba(255, 255, 255, 0.08); color: #FFFFF'
    'F; }\n.section-nav a[aria-current="true"] { color: #FFFFFF; box-shadow: inset 0 -2px 0 var(--brand-or'
    'ange); border-radius: 6px 6px 0 0; }\n.section-nav .n { margin-left: 5px; color: #9FB0C3; font-weight'
    ': 500; }\n.toolbar-actions { margin-left: auto; display: flex; align-items: center; gap: 8px; flex-sh'
    'rink: 0; }\n.chip-ro { padding: 4px 11px; border: 1px solid rgba(255, 255, 255, 0.24); border-radius:'
    ' 999px; color: #D5DCE5; font-size: 12.5px; font-weight: 600; white-space: nowrap; }\n.btn { display: '
    'inline-flex; align-items: center; justify-content: center; gap: 8px; min-height: 38px; padding: 0 14'
    'px; border: 1px solid transparent; border-radius: 8px; font-size: 13.5px; font-weight: 600; line-hei'
    'ght: 1.2; white-space: nowrap; cursor: pointer; text-decoration: none; transition: background-color '
    '150ms ease, border-color 150ms ease, filter 150ms ease; }\n.btn svg { width: 16px; height: 16px; }\n.b'
    'tn-bar { background: transparent; color: #F3F5F8; border-color: rgba(255, 255, 255, 0.26); }\n.btn-ba'
    'r:hover { background: rgba(255, 255, 255, 0.08); border-color: rgba(255, 255, 255, 0.45); }\n.btn-pri'
    'mary { background: var(--brand-orange); border-color: var(--brand-orange); color: #141B24; }\n.btn-pr'
    'imary:hover { filter: brightness(1.07); }\n.btn-ghost { background: var(--bg-panel); color: var(--ink'
    '-primary); border-color: var(--border-strong); }\n.btn-ghost:hover { background: var(--bg-subtle); bo'
    'rder-color: var(--ink-secondary); }\n.btn-bar:focus-visible, .btn-primary:focus-visible { outline-col'
    'or: #FFFFFF; }\n\n/* Hero */\n.hero { background: linear-gradient(160deg, var(--hero-bg) 0%, var(--hero'
    '-deep) 100%); color: var(--hero-ink); padding: 44px 40px 100px; }\n.hero-in { max-width: 1320px; marg'
    'in: 0 auto; display: grid; grid-template-columns: minmax(0, 1fr) 340px; gap: 20px 48px; align-items:'
    ' start; }\n.hero h1 { margin: 0; max-width: 24ch; color: #FFFFFF; font-size: 42px; line-height: 1.1; '
    'font-weight: 700; letter-spacing: -0.02em; text-wrap: balance; }\n.hero-scope { margin: 10px 0 0; col'
    'or: var(--hero-muted); font-size: 15px; }\n.hero-lead { margin: 16px 0 0; max-width: 68ch; font-size:'
    ' 17px; line-height: 1.55; }\n.hero-lead b { color: #FFFFFF; font-weight: 700; }\n.meta { display: flex'
    '; flex-wrap: wrap; gap: 8px; margin: 20px 0 0; padding: 0; list-style: none; }\n.meta li { max-width:'
    ' 100%; padding: 4px 11px; border: 1px solid var(--hero-line); border-radius: 999px; color: var(--her'
    'o-muted); font-size: 12.5px; overflow-wrap: anywhere; }\n.meta li.on { color: #FFFFFF; font-weight: 6'
    '00; border-color: rgba(255, 255, 255, 0.42); }\n.meta li.warn { color: #FEDF89; font-weight: 600; bor'
    'der-color: rgba(254, 223, 137, 0.5); }\n.verdict { padding: 20px 22px; border: 1px solid var(--verdic'
    't-line, var(--hero-line)); border-radius: 14px; background: rgba(255, 255, 255, 0.05); }\n.verdict .k'
    ' { color: var(--hero-muted); font-size: 13px; font-weight: 600; }\n.verdict b { display: block; margi'
    'n-top: 6px; color: var(--verdict-ink, #FFFFFF); font-size: 28px; line-height: 1.15; font-weight: 700'
    '; }\n.verdict p { margin: 8px 0 0; color: var(--hero-muted); font-size: 14px; }\n.verdict p + p { marg'
    'in-top: 4px; }\n.verdict.crit { --verdict-ink: #FFB4AB; --verdict-line: rgba(255, 180, 171, 0.5); }\n.'
    'verdict.warn { --verdict-ink: #FEDF89; --verdict-line: rgba(254, 223, 137, 0.5); }\n.verdict.ok { --v'
    'erdict-ink: #A6F4C5; --verdict-line: rgba(166, 244, 197, 0.45); }\n.dist { grid-column: 1 / -1; margi'
    'n-top: 4px; }\n.dist-head { display: flex; justify-content: space-between; gap: 12px; margin-bottom: '
    '8px; color: var(--hero-muted); font-size: 13px; }\n.track { display: flex; height: 12px; overflow: hi'
    'dden; border-radius: 999px; background: rgba(255, 255, 255, 0.12); }\n.track i { display: block; heig'
    'ht: 100%; }\n.legend { display: flex; flex-wrap: wrap; gap: 6px 18px; margin-top: 10px; color: var(--'
    'hero-muted); font-size: 13px; }\n.legend span { display: inline-flex; align-items: center; gap: 7px; '
    '}\n.legend i { width: 10px; height: 10px; border-radius: 3px; }\n.legend b { color: #FFFFFF; }\n\n/* Pag'
    'e body */\n.page { max-width: 1320px; margin: 0 auto; padding: 0 40px 56px; }\n.kpis { position: relat'
    'ive; z-index: 2; display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)); gap: 12px; margin-'
    'top: -60px; }\n.kpi { min-width: 0; padding: 16px 18px 18px; border: 1px solid var(--border-hairline)'
    '; border-radius: 12px; background: var(--bg-panel); box-shadow: var(--shadow-card); }\n.kpi .v { font'
    '-size: 36px; line-height: 1; font-weight: 700; letter-spacing: -0.02em; }\n.kpi .l { margin-top: 10px'
    '; font-size: 14px; line-height: 1.35; font-weight: 600; }\n.kpi .d { margin-top: 4px; color: var(--in'
    'k-muted); font-size: 12.5px; line-height: 1.4; }\n.notes { display: grid; gap: 10px; margin-top: 16px'
    '; }\n.notes:empty { display: none; }\n.note { display: flex; align-items: flex-start; gap: 10px; paddi'
    'ng: 11px 16px; border: 1px solid var(--note-line); border-radius: 10px; background: var(--note-bg); '
    'color: var(--note-ink); font-size: 14px; font-weight: 500; }\n.note svg { width: 18px; height: 18px; '
    'margin-top: 1px; }\n.note a { color: inherit; font-weight: 700; }\n.note.sim { background: repeating-l'
    'inear-gradient(135deg, var(--note-bg) 0 12px, rgba(254, 223, 137, 0.07) 12px 24px), var(--note-bg); '
    '}\nhtml:not([data-theme="dark"]) .note.sim { background: repeating-linear-gradient(135deg, #FFFAEB 0 '
    '12px, #FEF0C7 12px 24px); }\n.sec { margin-top: 48px; scroll-margin-top: 80px; }\n.sh { display: flex;'
    ' flex-wrap: wrap; justify-content: space-between; align-items: flex-end; gap: 8px 24px; margin-botto'
    'm: 14px; }\n.sh h2 { margin: 0; font-size: 22px; line-height: 1.3; font-weight: 700; letter-spacing: '
    '-0.01em; }\n.sh h3 { margin: 0; font-size: 18px; line-height: 1.3; font-weight: 700; }\n.sub-sh { marg'
    'in-top: 32px; }\n.why { margin: 4px 0 0; max-width: 75ch; color: var(--ink-muted); font-size: 14px; }'
    '\n.count { margin: 0; color: var(--ink-secondary); font-size: 13.5px; white-space: nowrap; }\n.count s'
    'trong { color: var(--ink-primary); }\n.card { min-width: 0; padding: 20px 22px; border: 1px solid var'
    '(--border-hairline); border-radius: 12px; background: var(--bg-panel); box-shadow: var(--shadow-card'
    '); }\n.card h3 { margin: 0; font-size: 16.5px; line-height: 1.3; font-weight: 700; }\n.card .sub { mar'
    'gin: 4px 0 14px; color: var(--ink-muted); font-size: 13.5px; }\n.grid2 { display: grid; grid-template'
    '-columns: repeat(2, minmax(0, 1fr)); gap: 16px; }\n.mt { margin-top: 16px; }\n\n/* Overview */\n.tiles {'
    ' display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; margin-bottom: 6px; }\n.'
    'tile { display: flex; flex-direction: column; align-items: flex-start; gap: 4px; padding: 12px 14px;'
    ' border: 1px solid transparent; border-radius: 10px; background: var(--bg-subtle); text-align: left;'
    ' cursor: pointer; transition: border-color 150ms ease; }\n.tile:hover { border-color: var(--border-st'
    'rong); }\n.tile b { font-size: 28px; line-height: 1; font-weight: 700; }\n.tile span { color: var(--in'
    'k-secondary); font-size: 12.5px; line-height: 1.35; }\n.tile.imm { border-color: var(--brand-orange-l'
    'ine); background: var(--brand-orange-wash); }\n.tile.imm b { color: var(--brand-orange-text); }\n.todo'
    ' { margin: 0; padding: 0; list-style: none; }\n.todo li { display: grid; grid-template-columns: 28px '
    'minmax(0, 1fr); gap: 10px; padding: 11px 0; border-top: 1px solid var(--border-hairline); }\n.todo li'
    ' > div { min-width: 0; overflow-wrap: anywhere; }\n.todo .rk { color: var(--ink-muted); font-size: 15'
    'px; font-weight: 700; }\n.todo .t { font-size: 14px; line-height: 1.4; font-weight: 600; }\n.todo .m {'
    ' display: flex; flex-wrap: wrap; align-items: center; gap: 6px 10px; margin-top: 5px; color: var(--i'
    'nk-muted); font-size: 12.5px; }\n.todo .m > span:last-child { min-width: 0; }\n.more-link { display: i'
    'nline-block; margin-top: 4px; font-size: 14px; font-weight: 600; }\n.exec-list { margin: 0; padding-l'
    'eft: 18px; max-width: 75ch; }\n.exec-list li { margin: 0 0 8px; font-size: 14.5px; line-height: 1.55;'
    ' }\n.exec-list li::marker { color: var(--ink-muted); }\n.exec-list b { font-weight: 700; }\n.prov { dis'
    'play: grid; grid-template-columns: max-content minmax(0, 1fr); gap: 6px 16px; margin: 16px 0 0; padd'
    'ing-top: 14px; border-top: 1px solid var(--border-hairline); font-size: 13.5px; }\n.prov dt { color: '
    'var(--ink-muted); }\n.prov dd { margin: 0; font-weight: 600; overflow-wrap: anywhere; }\n.bars { displ'
    'ay: grid; gap: 2px; }\n.brow { display: grid; grid-template-columns: minmax(110px, 42%) minmax(0, 1fr'
    ') 40px; gap: 12px; align-items: center; width: calc(100% + 16px); margin: 0 -8px; padding: 7px 8px; '
    'border: 0; border-radius: 8px; background: none; font-size: 14px; text-align: left; cursor: pointer;'
    ' }\n.brow:hover { background: var(--bg-subtle); }\n.brow .bl { overflow: hidden; text-overflow: ellips'
    'is; white-space: nowrap; }\n.brow .bl small { margin-left: 6px; color: var(--ink-muted); font-size: 1'
    '2.5px; }\n.brow .bt { height: 10px; overflow: hidden; border-radius: 999px; background: var(--bg-subt'
    'le); }\n.brow:hover .bt { background: var(--bg-panel); }\n.brow .bt i { display: block; height: 100%; '
    'min-width: 3px; border-radius: 999px; background: var(--chart); }\n.brow b { text-align: right; font-'
    'weight: 700; }\n.dot { display: inline-block; width: 9px; height: 9px; margin-right: 8px; border-radi'
    'us: 50%; vertical-align: 0; }\n.empty-note { margin: 0; color: var(--ink-muted); font-size: 14px; }\n\n'
    '/* Filters */\n.filters { display: grid; grid-template-columns: minmax(220px, 1.5fr) repeat(3, minmax'
    '(170px, 1fr)) auto; gap: 12px; align-items: end; }\n.field { display: flex; flex-direction: column; g'
    'ap: 6px; min-width: 0; }\n.field label { color: var(--ink-secondary); font-size: 13px; font-weight: 6'
    '00; }\n.field label code { margin-left: 4px; color: var(--ink-muted); font-weight: 500; }\n.control { '
    'width: 100%; min-height: 40px; padding: 0 12px; border: 1px solid var(--border-strong); border-radiu'
    's: 8px; background: var(--bg-panel); color: var(--ink-primary); font-size: 14px; }\n.control::placeho'
    'lder { color: var(--ink-muted); opacity: 1; }\n.control:focus { outline: none; border-color: var(--br'
    'and-orange-text); box-shadow: 0 0 0 3px rgba(255, 78, 0, 0.22); }\n.filter-foot { display: flex; flex'
    '-wrap: wrap; justify-content: space-between; align-items: center; gap: 12px 24px; margin-top: 16px; '
    'padding-top: 14px; border-top: 1px solid var(--border-hairline); }\n.status-line { margin: 0; color: '
    'var(--ink-secondary); font-size: 13.5px; }\n.status-line b { color: var(--ink-primary); }\n.downloads '
    '{ display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }\n.downloads > span { margin-right:'
    ' 2px; color: var(--ink-muted); font-size: 13px; }\n\n/* Tables */\n.table-card { padding: 0; overflow: '
    'hidden; }\n.table-scroll { overflow-x: auto; background: linear-gradient(90deg, var(--bg-panel) 30%, '
    'transparent) left / 36px 100% no-repeat local, linear-gradient(270deg, var(--bg-panel) 30%, transpar'
    'ent) right / 36px 100% no-repeat local, radial-gradient(farthest-side at 0 50%, var(--edge), transpa'
    'rent) left / 14px 100% no-repeat scroll, radial-gradient(farthest-side at 100% 50%, var(--edge), tra'
    'nsparent) right / 14px 100% no-repeat scroll; }\n.ledger-table { width: 100%; border-collapse: collap'
    'se; font-size: 13.5px; }\n.ledger-table th { padding: 10px 12px; border-bottom: 1px solid var(--borde'
    'r-hairline); background: var(--bg-subtle); color: var(--ink-secondary); font-size: 11.5px; font-weig'
    'ht: 700; letter-spacing: 0.04em; line-height: 1.35; text-align: left; text-transform: uppercase; ver'
    'tical-align: bottom; }\n.ledger-table th .hg { white-space: nowrap; }\n.ledger-table td { padding: 12p'
    'x; border-bottom: 1px solid var(--border-hairline); vertical-align: top; }\n.ledger-table tbody tr:la'
    'st-child td { border-bottom: 0; }\n.ledger-table tbody tr:hover td { background: var(--bg-row-hover);'
    ' }\n.ledger-table .n { text-align: right; white-space: nowrap; }\n.ledger-table tr.flash td { backgrou'
    'nd: var(--brand-orange-wash); }\n.ledger-table tr[id] { scroll-margin-top: 90px; }\n.ledger-table tr.p'
    'g { display: none; }\n.more-row { display: flex; flex-wrap: wrap; justify-content: center; align-item'
    's: center; gap: 8px 16px; padding: 14px 16px; border-top: 1px solid var(--border-hairline); color: v'
    'ar(--ink-muted); font-size: 13px; }\n.more-row[hidden] { display: none; }\n.sort { position: relative;'
    ' display: inline-block; margin: -4px -16px -4px -6px; padding: 4px 16px 4px 6px; border: 0; border-r'
    'adius: 4px; background: none; color: inherit; font: inherit; letter-spacing: inherit; line-height: i'
    'nherit; text-align: left; text-transform: inherit; cursor: pointer; }\n.th-print { display: none; }\n.'
    'sort:hover { color: var(--ink-primary); }\n.sort::after { content: ""; position: absolute; right: 4px'
    '; bottom: 10px; width: 0; height: 0; border-left: 4px solid transparent; border-right: 4px solid tra'
    'nsparent; border-top: 5px solid currentColor; opacity: 0; }\n.sort:hover::after { opacity: 0.35; }\nth'
    '[aria-sort="ascending"] .sort::after { opacity: 1; border-top: 0; border-bottom: 5px solid currentCo'
    'lor; }\nth[aria-sort="descending"] .sort::after { opacity: 1; }\nth[aria-sort] { color: var(--ink-prim'
    'ary); }\n.empty-row td { padding: 22px 16px; color: var(--ink-muted); }\n.pill { display: inline-flex;'
    ' align-items: center; gap: 6px; padding: 3px 10px; border-radius: 999px; font-size: 12px; font-weigh'
    't: 700; line-height: 1.3; white-space: nowrap; }\n.pill::before { content: ""; width: 7px; height: 7p'
    'x; border-radius: 50%; background: currentColor; }\n.pill.critical { color: var(--sev-critical); back'
    'ground: var(--sev-critical-bg); }\n.pill.high { color: var(--sev-high); background: var(--sev-high-bg'
    '); }\n.pill.medium { color: var(--sev-medium); background: var(--sev-medium-bg); }\n.pill.low { color:'
    ' var(--sev-low); background: var(--sev-low-bg); }\n.pill.info { color: var(--sev-info); background: v'
    'ar(--sev-info-bg); }\n.pill.ok { color: var(--ok); background: var(--ok-bg); }\n.tag { display: inline'
    '-block; padding: 2px 9px; border: 1px solid var(--border-hairline); border-radius: 6px; background: '
    'var(--bg-subtle); color: var(--ink-secondary); font-size: 12px; font-weight: 600; white-space: nowra'
    'p; }\n.tag.immediate_24h { border-color: var(--brand-orange-line); background: var(--brand-orange-was'
    'h); color: var(--brand-orange-text); }\n.id { color: var(--ink-secondary); font-family: var(--font-mo'
    'no); font-size: 12.5px; white-space: nowrap; }\n.sm { display: block; margin-top: 3px; color: var(--i'
    'nk-muted); font-size: 12.5px; line-height: 1.45; }\n.stack > * + * { margin-top: 6px; }\n.res b { disp'
    'lay: block; font-weight: 600; overflow-wrap: anywhere; }\n.code { color: var(--ink-secondary); font-f'
    'amily: var(--font-mono); font-size: 12px; }\n.ext { display: inline-flex; align-items: center; gap: 4'
    'px; margin-top: 4px; font-size: 12.5px; font-weight: 600; white-space: nowrap; }\n.ext svg { width: 1'
    '2px; height: 12px; }\n.ids { display: flex; flex-wrap: wrap; gap: 4px; }\n.chip-id { padding: 2px 7px;'
    ' border: 1px solid var(--border-hairline); border-radius: 6px; background: var(--bg-subtle); color: '
    'var(--ink-secondary); font-family: var(--font-mono); font-size: 12px; text-decoration: none; white-s'
    'pace: nowrap; }\na.chip-id:hover { border-color: var(--brand-orange-text); color: var(--brand-orange-'
    'text); }\n.state { display: inline-flex; align-items: center; gap: 6px; font-weight: 600; white-space'
    ': nowrap; }\n.state::before { content: ""; width: 7px; height: 7px; border-radius: 50%; background: v'
    'ar(--sev-info-bar); }\n.state.on::before { background: var(--sev-high-bar); }\n.rank { font-size: 16px'
    '; font-weight: 700; }\n.wide { min-width: 280px; overflow-wrap: anywhere; }\n.w3 { min-width: 250px; o'
    'verflow-wrap: anywhere; }\n.w2 { min-width: 170px; overflow-wrap: anywhere; }\n.w1 { min-width: 150px;'
    ' }\n.nw { white-space: nowrap; }\n.errbox { margin-top: 8px; padding: 8px 10px; border-radius: 8px; ba'
    'ckground: var(--sev-critical-bg); color: var(--sev-critical); font-size: 12.5px; line-height: 1.45; '
    '}\n.wslist { margin: 6px 0 0; padding: 0; list-style: none; color: var(--ink-muted); font-size: 12.5p'
    'x; }\n.plain-list { margin: 14px 0 0; padding-left: 18px; color: var(--ink-secondary); font-size: 14p'
    'x; }\n.plain-list li { margin-bottom: 6px; }\n.report-error { margin-top: 24px; }\n\n/* Footer */\n.foot '
    '{ max-width: 1320px; margin: 0 auto; padding: 20px 40px 40px; display: flex; flex-wrap: wrap; justif'
    'y-content: space-between; gap: 8px 16px; color: var(--ink-muted); font-size: 13px; }\n.foot-in { bord'
    'er-top: 1px solid var(--border-hairline); }\n\n.topbar:has(#client-logo-img) .brand-text span { displa'
    'y: none; }\n@media (max-width: 1300px) {\n  .topbar:has(#client-logo-img) .section-nav { display: none'
    '; }\n}\n@media (max-width: 760px) {\n  .topbar:has(#client-logo-img) .client-name-label { display: none'
    '; }\n}\n@media (max-width: 1360px) {\n  #theme-toggle { min-width: 40px; padding: 0 10px; }\n  #theme-to'
    'ggle .lbl { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); whit'
    'e-space: nowrap; }\n}\n@media (max-width: 1220px) {\n  .section-nav { display: none; }\n}\n@media (max-wi'
    'dth: 1100px) {\n  .hero-in { grid-template-columns: minmax(0, 1fr); }\n  .kpis { grid-template-columns'
    ': repeat(3, minmax(0, 1fr)); }\n  .grid2 { grid-template-columns: minmax(0, 1fr); }\n  .filters { grid'
    '-template-columns: repeat(2, minmax(0, 1fr)); }\n}\n@media (max-width: 760px) {\n  .topbar-inner { gap:'
    ' 10px; padding: 8px 16px; }\n  .chip-ro { display: none; }\n  .brand-text span, .btn .lbl { position: '
    'absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }\n  .'
    'btn-bar, .btn-primary { min-width: 40px; padding: 0 10px; }\n  .hero { padding: 28px 16px 84px; }\n  .'
    'hero h1 { font-size: 30px; }\n  .hero-lead { font-size: 15.5px; }\n  .verdict b { font-size: 24px; }\n '
    ' .page { padding: 0 16px 40px; }\n  .kpis { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10'
    'px; margin-top: -56px; }\n  .kpi { padding: 14px; }\n  .kpi .v { font-size: 30px; }\n  .sec { margin-to'
    'p: 36px; }\n  .sh h2 { font-size: 20px; }\n  .card { padding: 16px; }\n  .tiles { gap: 8px; }\n  .tile {'
    ' padding: 10px; }\n  .tile b { font-size: 24px; }\n  .filters { grid-template-columns: minmax(0, 1fr);'
    ' }\n  .brow { grid-template-columns: minmax(0, 1fr) 36px; row-gap: 6px; }\n  .brow .bt { grid-column: '
    '1 / -1; grid-row: 2; }\n  .foot { padding: 16px 16px 32px; }\n}\n@media (max-width: 360px) {\n  .topbar-'
    'inner { gap: 8px; padding: 8px 12px; }\n  .brand { gap: 8px; }\n  .client-plaque { padding: 4px 7px; }'
    '\n  .client-name-label { font-size: 12px; }\n  .brand-text b { font-size: 13px; }\n}\n@media (max-width:'
    ' 340px) {\n  .brand-text { display: none; }\n}\n@media (prefers-reduced-motion: reduce) {\n  html { scro'
    'll-behavior: auto; }\n  *, *::before, *::after { transition: none !important; animation: none !import'
    'ant; }\n}\n\n@page { size: A4 landscape; margin: 10mm 10mm 14mm; @bottom-right { content: "Page " count'
    'er(page) " of " counter(pages); font: 8.5pt \'Segoe UI\', sans-serif; color: #5A687A; } }\n@media print'
    ' {\n  html, html[data-theme="dark"] {\n    --bg-page: #FFFFFF; --bg-panel: #FFFFFF; --bg-subtle: #F1EE'
    'E8; --bg-row-hover: #FFFFFF;\n    --ink-primary: #141B24; --ink-secondary: #3E4C5E; --ink-muted: #5A6'
    '87A;\n    --border-hairline: #DEDCD6; --border-strong: #9AA5B5;\n    --brand-orange-text: #C23800; --b'
    'rand-orange-wash: #FFF2EC; --brand-orange-line: #FFC9AE;\n    --hero-bg: #1C2532; --hero-deep: #141B2'
    '4; --hero-muted: #C3CCD8;\n    --sev-critical: #B42318; --sev-critical-bg: #FEE4E2; --sev-high: #B938'
    '15; --sev-high-bg: #FFEAD5;\n    --sev-medium: #93370D; --sev-medium-bg: #FEF0C7; --sev-low: #175CD3;'
    ' --sev-low-bg: #D1E9FF;\n    --sev-info: #344054; --sev-info-bg: #EAECF0; --ok: #067647; --ok-bg: #DC'
    'FAE6;\n    --note-bg: #FFFAEB; --note-line: #FEDF89; --note-ink: #7A2E0E; --chart: #3E4C5E;\n    color'
    '-scheme: light;\n  }\n  * { -webkit-print-color-adjust: exact; print-color-adjust: exact; }\n  body { b'
    'ackground: #FFFFFF; font-size: 11.5px; }\n  .topbar { position: static; background-color: #FFFFFF; co'
    'lor: #141B24; border-bottom: 0; }\n  .topbar-inner { min-height: 0; padding: 0 0 8px; }\n  .brand { co'
    'lor: #141B24; }\n  .client-plaque { border: 1px solid #DEDCD6; }\n  .brand-text span { color: #5A687A;'
    ' }\n  .chip-ro { display: inline-block; color: #3E4C5E; border-color: #DEDCD6; }\n  .section-nav, #the'
    'me-toggle, #btn-print, .skip-link, #sec-filters, .downloads, .more-link, .more-row { display: none !'
    'important; }\n  .ledger-table tr.pg { display: table-row; }\n  .print-only { display: block; }\n  .hero'
    ' { padding: 22px 24px 70px; border-radius: 12px; }\n  .hero h1 { font-size: 30px; max-width: none; }\n'
    '  .hero-lead { font-size: 13.5px; }\n  .hero-in { grid-template-columns: minmax(0, 1fr) 260px; gap: 1'
    '4px 28px; }\n  .verdict b { font-size: 21px; }\n  .page { padding: 0; max-width: none; }\n  .kpis { gri'
    'd-template-columns: repeat(6, minmax(0, 1fr)); margin-top: -50px; }\n  .kpi .v { font-size: 26px; }\n '
    ' .kpi, .card, .note, .brow, .verdict, .todo li, .tile, .ledger-table tr { break-inside: avoid; }\n  .'
    'card.table-card { break-inside: auto; }\n  .card, .kpi { box-shadow: none; }\n  .grid2 { grid-template'
    '-columns: repeat(2, minmax(0, 1fr)); }\n  .sec { margin-top: 20px; }\n  .sh { break-after: avoid; }\n  '
    '.table-card { overflow: visible; }\n  .table-scroll { overflow: visible; background: none; }\n  .ledge'
    'r-table { font-size: 10.5px; }\n  .ledger-table th { font-size: 9.5px; padding: 6px 8px; }\n  .ledger-'
    'table td { padding: 6px 8px; overflow-wrap: break-word; }\n  .ledger-table td.wide, .ledger-table td.'
    'w2, .ledger-table td.w3 { overflow-wrap: anywhere; }\n  .ledger-table thead { display: table-header-g'
    'roup; }\n  .ledger-table .sm, .ledger-table .ext, .ledger-table .pill, .ledger-table .tag, .ledger-ta'
    'ble .state { font-size: 9.5px; }\n  .ledger-table .id, .ledger-table .code, .ledger-table .chip-id { '
    'font-size: 9.5px; }\n  .ledger-table .rank { font-size: 12px; }\n  .brow .bl { white-space: normal; }\n'
    '  .brow .bl small { display: block; margin: 1px 0 0 17px; }\n  .wide, .w1, .w2, .w3 { min-width: 0; }'
    '\n  .sort { display: none !important; }\n  .th-print { display: inline; }\n  .ext svg { display: none; '
    '}\n  a { text-decoration: none; }\n  .foot { padding: 12px 0 0; max-width: none; }\n}\n</style>\n</head>\n'
    '<body>\n<a class="skip-link" href="#report-body">Skip to content</a>\n<header class="topbar" id="topba'
    'r">\n  <div class="topbar-inner">\n    <a class="brand" href="#top" aria-label="Top of the report">\n  '
    '    <span class="client-plaque" id="client-plaque">\n        <span id="client-logo-slot"></span>\n    '
    '    <span class="client-name-label" id="client-name-label">Customer</span>\n      </span>\n      <span'
    ' class="brand-text"><b>Azure SRE Agent</b><span id="topbar-subtitle">Operations digest</span></span>'
    '\n    </a>\n    <nav class="section-nav" id="section-nav" aria-label="Report sections">\n      <a href='
    '"#sec-executive">Summary</a>\n      <a href="#sec-incidents">Incidents<span class="n" id="nav-inciden'
    'ts-count">0</span></a>\n      <a href="#sec-anomalies">Anomalies<span class="n" id="nav-anomalies-cou'
    'nt">0</span></a>\n      <a href="#sec-actions">Actions<span class="n" id="nav-actions-count">0</span>'
    '</a>\n      <a href="#sec-resources">Resources<span class="n" id="nav-resources-count">0</span></a>\n '
    '     <a href="#sec-coverage">Coverage<span class="n" id="nav-sources-count">0</span></a>\n    </nav>\n'
    '    <div class="toolbar-actions">\n      <span class="chip-ro">Read-only</span>\n      <button type="b'
    'utton" class="btn btn-bar" id="theme-toggle" title="Dark mode"><svg viewBox="0 0 24 24" fill="none" '
    'stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="t'
    'rue"><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8Z"/></svg><span class="lbl">Dark mode</span'
    '></button>\n      <button type="button" class="btn btn-primary" id="btn-print"><svg viewBox="0 0 24 2'
    '4" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"'
    ' aria-hidden="true"><path d="M6 9V3h12v6M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 '
    '2 0 0 1-2 2h-2M6 14h12v7H6z"/></svg><span class="lbl">Print / PDF</span></button>\n    </div>\n  </div'
    '>\n</header>\n\n<main id="report-body">\n  <section class="hero" id="top" aria-labelledby="cover-title">'
    '\n    <div class="hero-in">\n      <div>\n        <h1 id="cover-title">Incidents, anomalies, and recomm'
    'ended actions</h1>\n        <p class="hero-scope" id="hero-scope">Periodic Azure operations report</p'
    '>\n        <p class="hero-lead" id="hero-lead"></p>\n        <ul class="meta" id="hero-meta" aria-labe'
    'l="Report context"></ul>\n      </div>\n      <aside class="verdict" id="verdict-card" aria-label="Ver'
    'dict">\n        <div class="k">Verdict</div>\n        <b id="verdict-title">—</b>\n        <p id="verdi'
    'ct-detail"></p>\n        <p id="verdict-sub"></p>\n      </aside>\n      <div class="dist" id="evidence'
    '-distribution-bar">\n        <div class="dist-head"><span>Severity of incidents and anomalies</span><'
    'span id="dist-total-label">0 signals</span></div>\n        <div class="track" id="dist-track" role="i'
    'mg" aria-label="Distribution by severity"></div>\n        <div class="legend" id="dist-legend"></div>'
    '\n      </div>\n    </div>\n  </section>\n\n  <div class="page">\n    <div class="kpis" id="ledger-summary'
    '-grid">\n      <div class="kpi"><div class="v" id="kpi-native-alerts">0</div><div class="l">Azure Mon'
    'itor alerts</div><div class="d" id="kpi-native-alerts-sub">alertsmanagementresources</div></div>\n   '
    '   <div class="kpi"><div class="v" id="kpi-service-health">0</div><div class="l">Service Health comm'
    'unications</div><div class="d" id="kpi-service-health-sub">ServiceIssue and PlannedMaintenance</div>'
    '</div>\n      <div class="kpi"><div class="v" id="kpi-posture-anomalies">0</div><div class="l">Contro'
    'l plane and Arc anomalies</div><div class="d" id="kpi-posture-anomalies-sub">Failed extensions and c'
    'onnectivity</div></div>\n      <div class="kpi"><div class="v" id="kpi-telemetry-anomalies">0</div><d'
    'iv class="l">Telemetry anomalies</div><div class="d" id="kpi-telemetry-anomalies-sub">InsightsMetric'
    's, Perf, and Heartbeat</div></div>\n      <div class="kpi"><div class="v" id="kpi-actions-total">0</d'
    'iv><div class="l">Recommended actions</div><div class="d" id="kpi-actions-sub">Prioritized by horizo'
    'n</div></div>\n      <div class="kpi"><div class="v" id="kpi-resources-total">0</div><div class="l">R'
    'esources in scope</div><div class="d" id="kpi-resources-sub">0 with active findings</div></div>\n    '
    '</div>\n    <div class="notes" id="status-notes"></div>\n\n    <section class="sec" id="sec-executive" '
    'aria-labelledby="h-executive">\n      <div class="sh"><div><h2 id="h-executive">Period summary</h2><p'
    ' class="why">What needs attention first, and where the signals of the evaluated window come from.</p'
    '></div></div>\n      <div class="grid2">\n        <div class="card">\n          <h3>What to do now</h3>'
    '\n          <p class="sub">Prioritized actions for human review; each one cites the evidence behind i'
    't.</p>\n          <div class="tiles" id="horizon-tiles"></div>\n          <ol class="todo" id="top-act'
    'ions"></ol>\n          <a class="more-link" href="#sec-actions" id="all-actions-link">See all actions'
    '</a>\n        </div>\n        <div class="card">\n          <h3>Executive summary</h3>\n          <p cla'
    'ss="sub">The essentials of the period, calculated from the sources read.</p>\n          <ul class="ex'
    'ec-list" id="executive-messages-list"></ul>\n          <dl class="prov" id="provenance-strip">\n      '
    '      <dt>Azure subscription</dt><dd class="code" id="prov-subscription">—</dd>\n            <dt>Eval'
    'uation window</dt><dd id="prov-window-label">—</dd>\n            <dt>Exact UTC interval</dt><dd id="p'
    'rov-window-range">—</dd>\n            <dt>Cadence</dt><dd id="prov-cadence">—</dd>\n            <dt>Da'
    'ta provenance</dt><dd id="prov-provenance">—</dd>\n            <dt>Reference time (UTC)</dt><dd id="r'
    'eference-utc-label">—</dd>\n          </dl>\n        </div>\n        <div class="card">\n          <h3>S'
    'ignals by evidence stream</h3>\n          <p class="sub">Each bar filters the records by that stream.'
    '</p>\n          <div class="bars" id="stream-bars"></div>\n        </div>\n        <div class="card">\n '
    '         <h3>Resources with the most signals</h3>\n          <p class="sub">Incidents plus anomalies '
    'per resource: where the review starts.</p>\n          <div class="bars" id="resource-bars"></div>\n   '
    '     </div>\n      </div>\n    </section>\n\n    <section class="sec" id="sec-filters" aria-labelledby="'
    'h-filters">\n      <div class="sh"><div><h2 id="h-filters">Filter records</h2><p class="why">The filt'
    'ers narrow incidents, anomalies, actions, resources, and Advisor at the same time. Downloads always '
    'include every record.</p></div></div>\n      <div class="card">\n        <div class="filters">\n       '
    '   <div class="field">\n            <label for="filter-search">Search</label>\n            <input type'
    '="search" class="control" id="filter-search" placeholder="Resource, ID, extension, or metric" autoco'
    'mplete="off">\n          </div>\n          <div class="field">\n            <label for="filter-category'
    '">Evidence stream <code>category</code></label>\n            <select class="control" id="filter-categ'
    'ory">\n              <option value="all">All categories</option>\n              <option value="native_'
    'alert">Azure Monitor native alerts</option>\n              <option value="service_health">Azure Servi'
    'ce Health communications</option>\n              <option value="extension_failure">VM / Azure Arc ext'
    'ension failures</option>\n              <option value="connectivity_posture">Connectivity / control p'
    'lane anomalies</option>\n              <option value="telemetry_anomaly">Telemetry anomalies (CPU / M'
    'emory / Disk / Heartbeat)</option>\n              <option value="advisor_recommendation">Azure Adviso'
    'r recommendations</option>\n            </select>\n          </div>\n          <div class="field">\n    '
    '        <label for="filter-severity">Severity <code>severity</code></label>\n            <select clas'
    's="control" id="filter-severity">\n              <option value="all">All severities</option>\n        '
    '      <option value="critical">Critical</option>\n              <option value="high">High</option>\n  '
    '            <option value="medium">Medium</option>\n              <option value="low">Low</option>\n  '
    '          </select>\n          </div>\n          <div class="field">\n            <label for="filter-ho'
    'rizon">Action horizon <code>horizon</code></label>\n            <select class="control" id="filter-ho'
    'rizon">\n              <option value="all">All horizons</option>\n              <option value="immedia'
    'te_24h">Immediate &lt;24h</option>\n              <option value="short_term_7d">Short term 1-7 days</'
    'option>\n              <option value="monthly_cycle">Monthly cycle</option>\n            </select>\n   '
    '       </div>\n          <button type="button" class="btn btn-ghost" id="filter-reset">Reset</button>'
    '\n        </div>\n        <div class="filter-foot">\n          <p class="status-line" id="filter-status'
    '-summary" aria-live="polite">Showing every collected record</p>\n          <div class="downloads">\n  '
    '          <span>Local downloads:</span>\n            <button type="button" class="btn btn-ghost" id="'
    'btn-export-json"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-'
    'linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 3v12m0 0 5-5m-5 5-5-5M4 21h1'
    '6"/></svg>Full JSON</button>\n            <button type="button" class="btn btn-ghost" id="btn-export-'
    'incidents-csv"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-li'
    'necap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 3v12m0 0 5-5m-5 5-5-5M4 21h16"'
    '/></svg>Incidents and anomalies CSV</button>\n            <button type="button" class="btn btn-ghost"'
    ' id="btn-export-actions-csv"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width'
    '="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 3v12m0 0 5-5m-5 '
    '5-5-5M4 21h16"/></svg>Recommended actions CSV</button>\n          </div>\n        </div>\n      </div>\n'
    '    </section>\n    <p class="print-only status-line" id="print-filter-note"></p>\n\n    <section class'
    '="sec" id="sec-incidents" aria-labelledby="h-incidents">\n      <div class="sh"><div><h2 id="h-incide'
    'nts">Incidents and platform communications</h2><p class="why">Azure Monitor native alerts and offici'
    'al Service Health communications in the window: what already happened or is still active.</p></div><'
    'p class="count"><strong id="incidents-count">0</strong> of <span id="incidents-total">0</span> incid'
    'ents</p></div>\n      <div class="card table-card"><div class="table-scroll" tabindex="0" role="regio'
    'n" aria-labelledby="h-incidents">\n        <table class="ledger-table" id="incidents-table"><caption '
    'class="sr-only">Incidents and platform communications</caption><thead></thead><tbody id="incidents-t'
    'body"></tbody></table>\n      </div></div>\n    </section>\n\n    <section class="sec" id="sec-anomalies'
    '" aria-labelledby="h-anomalies">\n      <div class="sh"><div><h2 id="h-anomalies">Technical anomalies'
    '</h2><p class="why">Deviations detected by the agent: failed extensions, control plane posture, and '
    'out-of-range telemetry.</p></div><p class="count"><strong id="anomalies-count">0</strong> of <span i'
    'd="anomalies-total">0</span> anomalies</p></div>\n      <div class="card table-card"><div class="tabl'
    'e-scroll" tabindex="0" role="region" aria-labelledby="h-anomalies">\n        <table class="ledger-tab'
    'le" id="anomalies-table"><caption class="sr-only">Technical anomalies</caption><thead></thead><tbody'
    ' id="anomalies-tbody"></tbody></table>\n      </div></div>\n    </section>\n\n    <section class="sec" i'
    'd="sec-actions" aria-labelledby="h-actions">\n      <div class="sh"><div><h2 id="h-actions">Prioritiz'
    'ed recommended actions</h2><p class="why">Plan ordered by urgency for human review. Each action link'
    's the evidence behind it; the agent doesn\'t make any changes.</p></div><p class="count"><strong id="'
    'actions-count">0</strong> of <span id="actions-total">0</span> actions</p></div>\n      <div class="c'
    'ard table-card"><div class="table-scroll" tabindex="0" role="region" aria-labelledby="h-actions">\n  '
    '      <table class="ledger-table" id="actions-table"><caption class="sr-only">Prioritized recommende'
    'd actions</caption><thead></thead><tbody id="actions-tbody"></tbody></table>\n      </div></div>\n    '
    '</section>\n\n    <section class="sec" id="sec-resources" aria-labelledby="h-resources">\n      <div cl'
    'ass="sh"><div><h2 id="h-resources">Status by resource</h2><p class="why">Every inventoried resource '
    'with its incidents, anomalies, extensions, and actions; resources with active findings first.</p></d'
    'iv><p class="count"><strong id="resources-count">0</strong> of <span id="resources-total">0</span> r'
    'esources</p></div>\n      <div class="card table-card"><div class="table-scroll" tabindex="0" role="r'
    'egion" aria-labelledby="h-resources">\n        <table class="ledger-table" id="resources-table"><capt'
    'ion class="sr-only">Operational status by resource</caption><thead></thead><tbody id="resources-tbod'
    'y"></tbody></table>\n      </div></div>\n      <div class="sh sub-sh"><div><h3 id="h-advisor">Azure Ad'
    'visor recommendations</h3><p class="why">Cached recommendations from <code>arm_advisor_recommendatio'
    'ns</code>, correlated with the action plan.</p></div><p class="count"><strong id="advisor-count">0</'
    'strong> of <span id="advisor-total">0</span> recommendations</p></div>\n      <div class="card table-'
    'card"><div class="table-scroll" tabindex="0" role="region" aria-labelledby="h-advisor">\n        <tab'
    'le class="ledger-table" id="advisor-table"><caption class="sr-only">Azure Advisor recommendations</c'
    'aption><thead></thead><tbody id="advisor-tbody"></tbody></table>\n      </div></div>\n    </section>\n\n'
    '    <section class="sec" id="sec-coverage" aria-labelledby="h-coverage">\n      <div class="sh"><div>'
    '<h2 id="h-coverage">Source coverage and method</h2><p class="why">What was read and with what result'
    '. A partial source is a blind spot, not a clean result.</p></div><p class="count"><strong id="source'
    's-count">0</strong> sources</p></div>\n      <div class="card table-card"><div class="table-scroll" t'
    'abindex="0" role="region" aria-labelledby="h-coverage">\n        <table class="ledger-table" id="sour'
    'ces-table"><caption class="sr-only">Coverage receipts by source</caption><thead></thead><tbody id="s'
    'ources-tbody"></tbody></table>\n      </div></div>\n      <div class="grid2 mt">\n        <div class="c'
    'ard">\n          <h3>Operational guarantees and limitations</h3>\n          <p class="sub">What this r'
    'eport doesn\'t claim.</p>\n          <ul class="exec-list" id="methodology-list"></ul>\n        </div>\n'
    '        <div class="card">\n          <h3>Method</h3>\n          <p class="sub">Run parameters and the'
    ' evidence streams queried in read-only mode.</p>\n          <dl class="prov" id="method-facts" style='
    '"margin-top:0;padding-top:0;border-top:0"></dl>\n          <ul class="plain-list mt" id="method-strea'
    'ms"></ul>\n        </div>\n      </div>\n    </section>\n  </div>\n</main>\n\n<footer class="foot-in"><div '
    'class="foot" id="report-footer"><span id="footer-left">Generated by Azure SRE Agent · Read-only</spa'
    'n><span id="footer-right"></span></div></footer>\n\n<script type="application/json" id="report-data">_'
    '_REPORT_DATA_JSON__</script>\n<script>\n(function () {\n  "use strict";\n\n  var SEV_RANK = { critical: 0'
    ', high: 1, medium: 2, low: 3 };\n  var SEV_LABEL = { critical: "Critical", high: "High", medium: "Med'
    'ium", low: "Low" };\n  var SEV_WORDS = { critical: ["critical", "critical"], high: ["high", "high"], '
    'medium: ["medium", "medium"], low: ["low", "low"] };\n  var SEV_BAR = { critical: "--sev-critical-bar'
    '", high: "--sev-high-bar", medium: "--sev-medium-bar", low: "--sev-low-bar" };\n  var HORIZON_RANK = '
    '{ immediate_24h: 0, short_term_7d: 1, monthly_cycle: 2 };\n  var STATUS = { complete: ["Complete", "o'
    'k"], partial: ["Partial", "medium"], denied: ["Denied", "critical"], error: ["Error", "critical"], n'
    'ot_configured: ["Not configured", "info"] };\n  var SHORT_CAT = {\n    native_alert: "Azure Monitor al'
    'ert",\n    service_health: "Service Health",\n    extension_failure: "Failed extension",\n    connectiv'
    'ity_posture: "Control plane",\n    telemetry_anomaly: "Telemetry",\n    advisor_recommendation: "Azure'
    ' Advisor"\n  };\n  var UNIT = { Percent: "%", Minutes: "min", MB: "MB", State: "" };\n  var TYPE_LABEL '
    '= {\n    "microsoft.compute/virtualmachines": "Virtual machine",\n    "microsoft.compute/virtualmachin'
    'escalesets": "Virtual machine scale set",\n    "microsoft.hybridcompute/machines": "Azure Arc server"'
    ',\n    "microsoft.kubernetes/connectedclusters": "Azure Arc-enabled Kubernetes",\n    "microsoft.conta'
    'inerservice/managedclusters": "AKS cluster",\n    "microsoft.app/containerapps": "Container App",\n   '
    ' "microsoft.web/sites": "App Service",\n    "microsoft.web/serverfarms": "App Service plan",\n    "mic'
    'rosoft.storage/storageaccounts": "Storage account",\n    "microsoft.keyvault/vaults": "Key Vault",\n  '
    '  "microsoft.sql/servers/databases": "SQL database",\n    "microsoft.dbforpostgresql/flexibleservers"'
    ': "PostgreSQL flexible server",\n    "microsoft.cache/redis": "Azure Cache for Redis",\n    "microsoft'
    '.operationalinsights/workspaces": "Log Analytics workspace",\n    "microsoft.resourcehealth/events": '
    '"Service Health"\n  };\n  var PATHS = {\n    ext: "M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 '
    '1-1-1V7a1 1 0 0 1 1-1h5",\n    alert: "M12 9v4m0 4h.01M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1'
    '.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z",\n    moon: "M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8Z",\n    sun: '
    '"M12 3v2M12 19v2M4.2 4.2l1.4 1.4M18.4 18.4l1.4 1.4M3 12h2M19 12h2M4.2 19.8l1.4-1.4M18.4 5.6l1.4-1.4M'
    '12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8Z"\n  };\n  var REDUCED = window.matchMedia && window.matchMedia("(pre'
    'fers-reduced-motion: reduce)").matches;\n\n  function el(tag, attrs, children) {\n    var node = docume'
    'nt.createElement(tag);\n    if (attrs) {\n      Object.keys(attrs).forEach(function (k) {\n        if ('
    'k === "className") {\n          node.className = attrs[k];\n        } else if (k === "textContent") {\n'
    '          node.textContent = attrs[k];\n        } else if (attrs[k] !== null && attrs[k] !== undefine'
    'd) {\n          node.setAttribute(k, String(attrs[k]));\n        }\n      });\n    }\n    (children || []'
    ').forEach(function (ch) {\n      if (ch === null || ch === undefined || ch === false) {\n        retur'
    'n;\n      }\n      node.appendChild(typeof ch === "string" || typeof ch === "number" ? document.create'
    'TextNode(String(ch)) : ch);\n    });\n    return node;\n  }\n\n  function clear(node) {\n    while (node.f'
    'irstChild) {\n      node.removeChild(node.firstChild);\n    }\n  }\n\n  function icon(name) {\n    var ns '
    '= "http://www.w3.org/2000/svg";\n    var svg = document.createElementNS(ns, "svg");\n    var attrs = {'
    ' viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", "stroke-width": "2", "stroke-linecap": '
    '"round", "stroke-linejoin": "round", "aria-hidden": "true" };\n    Object.keys(attrs).forEach(functio'
    'n (k) { svg.setAttribute(k, attrs[k]); });\n    var path = document.createElementNS(ns, "path");\n    '
    'path.setAttribute("d", PATHS[name]);\n    svg.appendChild(path);\n    return svg;\n  }\n\n  var dataNode '
    '= document.getElementById("report-data");\n  var DATA;\n  try {\n    DATA = JSON.parse(dataNode.textCon'
    'tent);\n  } catch (err) {\n    var holder = document.querySelector(".page");\n    clear(holder);\n    ho'
    'lder.appendChild(el("div", { className: "note report-error", role: "alert" }, [icon("alert"), el("sp'
    'an", null, ["Couldn\'t read the embedded data model. Generate the report with the tool (operation=\\"r'
    'eport\\") instead of opening the template directly."])]));\n    return;\n  }\n  var COUNTS = DATA.counts'
    ' || {};\n\n  function n(value) {\n    var v = Number(value) || 0;\n    return Math.round(v) === v ? Stri'
    'ng(v).replace(/\\B(?=(\\d{3})+(?!\\d))/g, ",") : String(v);\n  }\n\n  function plural(count, one, many) {\n'
    '    return Number(count) === 1 ? one : many;\n  }\n\n  function b(value) {\n    return el("b", { textCon'
    'tent: n(value) });\n  }\n\n  function utc(value) {\n    if (!value) {\n      return "—";\n    }\n    return'
    ' String(value).replace("T", " ").replace(/:\\d{2}(\\.\\d+)?Z$/, "").replace(/Z$/, "");\n  }\n\n  function '
    'plain(value) {\n    if (value === null || value === undefined) {\n      return "";\n    }\n    var s = S'
    'tring(value);\n    if (!/[<&]/.test(s)) {\n      return s;\n    }\n    var doc = new DOMParser().parseFr'
    'omString(s.replace(/<\\/(p|div|li|h[1-6]|tr|ul|ol)>|<br\\s*\\/?>/gi, " $& "), "text/html");\n    return '
    '(doc.body.textContent || "").replace(/\\s+/g, " ").trim();\n  }\n\n  function breakable(value, cls) {\n  '
    '  var span = el("span", { className: cls === undefined ? "code" : cls || null });\n    var buf = "";\n'
    '    String(value === null || value === undefined ? "" : value).split("").forEach(function (ch) {\n   '
    '   buf += ch;\n      if ("/.?&=_".indexOf(ch) >= 0) {\n        span.appendChild(document.createTextNod'
    'e(buf));\n        span.appendChild(document.createElement("wbr"));\n        buf = "";\n      }\n    });\n'
    '    if (buf) {\n      span.appendChild(document.createTextNode(buf));\n    }\n    return span;\n  }\n\n  f'
    'unction prose(value) {\n    var text = plain(value);\n    var span = el("span");\n    var last = 0;\n   '
    ' text.replace(/[A-Za-z)][\\/.](?=[A-Za-z(])/g, function (match, offset) {\n      var cut = offset + ma'
    'tch.length;\n      span.appendChild(document.createTextNode(text.slice(last, cut)));\n      span.appen'
    'dChild(document.createElement("wbr"));\n      last = cut;\n      return match;\n    });\n    span.append'
    'Child(document.createTextNode(text.slice(last)));\n    return span;\n  }\n\n  function withName(text, na'
    'me) {\n    var s = String(text || "");\n    var at = name && name.length <= 32 ? s.indexOf(name) : -1;'
    '\n    if (at < 0) {\n      return [s];\n    }\n    return [s.slice(0, at), el("span", { className: "nw",'
    ' textContent: name }), s.slice(at + name.length)];\n  }\n\n  function sevKey(row) {\n    return SEV_RANK'
    '.hasOwnProperty(row.severity) ? SEV_RANK[row.severity] : 9;\n  }\n\n  function pill(sev, label, title) '
    '{\n    var tone = SEV_RANK.hasOwnProperty(sev) || sev === "ok" || sev === "info" ? sev : "info";\n    '
    'return el("span", { className: "pill " + tone, textContent: label || SEV_LABEL[sev] || String(sev ||'
    ' "—"), title: title || null });\n  }\n\n  function extLink(href, label) {\n    if (typeof href !== "stri'
    'ng" || !/^https:\\/\\//.test(href)) {\n      return null;\n    }\n    return el("a", { className: "ext", '
    'href: href, target: "_blank", rel: "noopener noreferrer" }, [label, icon("ext")]);\n  }\n\n  function p'
    'ortalUrl(id) {\n    return typeof id === "string" && /^\\/subscriptions\\/[^/]+\\/(resourcegroups|provid'
    'ers)\\/[^?#]+$/i.test(id)\n      ? "https://portal.azure.com/#@/resource" + id\n      : null;\n  }\n\n  fu'
    'nction typeLabel(type) {\n    var t = String(type || "").toLowerCase();\n    return TYPE_LABEL[t] || t'
    '.split("/").pop() || "";\n  }\n\n  function rgLabel(rg) {\n    return rg === "subscription-scope" ? "Sub'
    'scription scope" : (rg || "");\n  }\n\n  function resourceCell(name, rg, type, id, extra) {\n    var met'
    'a = [rgLabel(rg), type ? typeLabel(type) : "", extra || ""].filter(Boolean).join(" · ");\n    return '
    'el("div", { className: "res", title: id || null }, [\n      el("b", { textContent: name || "—" }),\n  '
    '    meta ? el("span", { className: "sm", textContent: meta, title: type || null }) : null,\n      por'
    'talUrl(id) ? extLink(portalUrl(id), "Portal") : null\n    ]);\n  }\n\n  function idCell(row) {\n    retur'
    'n [el("span", { className: "id", textContent: row.id }), el("span", { className: "sm", textContent: '
    'SHORT_CAT[row.category] || row.category_label || "", title: row.category_label || null })];\n  }\n\n  f'
    'unction withUnit(value, unit) {\n    var u = UNIT.hasOwnProperty(unit) ? UNIT[unit] : (unit || "");\n '
    '   var text = typeof value === "number" ? n(value) : String(value === null || value === undefined ? '
    '"—" : value);\n    return u ? text + (u === "%" ? "" : "\\u00a0") + u : text;\n  }\n\n  /* ---------- Hea'
    'der, hero and KPIs ---------- */\n\n  function renderBranding() {\n    var client = DATA.client || {};\n'
    '    var nameLabel = document.getElementById("client-name-label");\n    var logoSlot = document.getEle'
    'mentById("client-logo-slot");\n    clear(logoSlot);\n    nameLabel.textContent = client.name || "Custo'
    'mer";\n    if (client.logo_data_uri && /^data:image\\/(png|jpeg);base64,/.test(client.logo_data_uri)) '
    '{\n      logoSlot.appendChild(el("img", { id: "client-logo-img", src: client.logo_data_uri, alt: clie'
    'nt.logo_alt || "Authorized customer logo" }));\n    }\n  }\n\n  function verdict() {\n    var sb = COUNTS'
    '.severity_breakdown || {};\n    var imm = COUNTS.actions_immediate_24h || 0;\n    var parts = ["critic'
    'al", "high", "medium", "low"].filter(function (k) { return sb[k]; }).map(function (k) {\n      return'
    ' n(sb[k]) + " " + SEV_WORDS[k][sb[k] === 1 ? 0 : 1];\n    });\n    var tone = imm > 0 || sb.critical ?'
    ' "crit" : (sb.high || sb.medium) ? "warn" : "ok";\n    var card = document.getElementById("verdict-ca'
    'rd");\n    card.className = "verdict " + tone;\n    document.getElementById("verdict-title").textConte'
    'nt = tone === "crit" ? "Action required" : tone === "warn" ? "Needs attention" : parts.length ? "No '
    'priority findings" : "No findings";\n    document.getElementById("verdict-detail").textContent = part'
    's.length ? parts.join(" · ") : "No incidents or anomalies in the window";\n    document.getElementByI'
    'd("verdict-sub").textContent =\n      (imm ? n(imm) + " " + plural(imm, "immediate action", "immediat'
    'e actions") + " (<24 h)" : "No actions in the immediate horizon")\n      + " · " + n(COUNTS.resources'
    '_attention || 0) + " " + plural(COUNTS.resources_attention, "resource", "resources") + " with active'
    ' findings";\n  }\n\n  function renderHero() {\n    var win = DATA.window || {};\n    var sources = DATA.s'
    'ources || [];\n    var degraded = sources.filter(function (s) { return s.status !== "complete" && s.s'
    'tatus !== "not_configured"; });\n    document.getElementById("hero-scope").textContent = "Periodic Az'
    'ure operations report · " + (win.label || win.period || "window not specified");\n    document.title '
    '= "Operations digest: incidents, anomalies, and recommended actions · " + (win.label || "") + " · " '
    '+ ((DATA.client || {}).name || "Customer");\n\n    var lead = document.getElementById("hero-lead");\n  '
    '  clear(lead);\n    [\n      "The window recorded ", b(COUNTS.incidents_total), " " + plural(COUNTS.in'
    'cidents_total, "incident", "incidents") + " and ",\n      b(COUNTS.anomalies_total), " " + plural(COU'
    'NTS.anomalies_total, "technical anomaly", "technical anomalies") + " across ",\n      b(COUNTS.resour'
    'ces_total), " " + plural(COUNTS.resources_total, "evaluated resource", "evaluated resources") + " ("'
    ',\n      b(COUNTS.resources_attention), " with active findings); the plan proposes ",\n      b(COUNTS.'
    'actions_total), " " + plural(COUNTS.actions_total, "prioritized action", "prioritized actions") + ":'
    ' ",\n      b(COUNTS.actions_immediate_24h), " " + plural(COUNTS.actions_immediate_24h, "immediate", "'
    'immediate") + ", ",\n      b(COUNTS.actions_short_term_7d), " short-term, and ", b(COUNTS.actions_mon'
    'thly_cycle), " for the monthly cycle."\n    ].forEach(function (part) {\n      lead.appendChild(typeof'
    ' part === "string" ? document.createTextNode(part) : part);\n    });\n\n    var sub = DATA.subscription'
    '_id || "";\n    var meta = document.getElementById("hero-meta");\n    clear(meta);\n    var live = DATA'
    '.provenance === "LIVE";\n    [\n      ["Generated " + utc(DATA.reference_utc) + " UTC", ""],\n      ["W'
    'indow " + utc(win.start_utc).slice(0, 10) + " → " + utc(win.end_utc).slice(0, 10) + " (UTC)", ""],\n '
    '     [sub ? "Subscription " + (sub.length > 16 ? sub.slice(0, 8) + "…" + sub.slice(-4) : sub) : "", '
    '""],\n      [live ? "Live read (LIVE)" : "Simulated data (" + (DATA.provenance || "SIMULATED") + ")",'
    ' "on"],\n      [degraded.length ? "Partial coverage · " + (sources.length - degraded.length) + " of "'
    ' + sources.length + " sources" : "Complete coverage · " + sources.length + " sources", degraded.leng'
    'th ? "warn" : ""]\n    ].forEach(function (item) {\n      if (item[0]) {\n        meta.appendChild(el("'
    'li", { className: item[1] || null, textContent: item[0], title: item[0].indexOf("Subscription") === '
    '0 ? sub : null }));\n      }\n    });\n\n    verdict();\n\n    var sb = COUNTS.severity_breakdown || {};\n '
    '   var total = ["critical", "high", "medium", "low"].reduce(function (acc, k) { return acc + (sb[k] '
    '|| 0); }, 0);\n    document.getElementById("dist-total-label").textContent = n(total) + " " + plural('
    'total, "signal", "signals");\n    var track = document.getElementById("dist-track");\n    var legend ='
    ' document.getElementById("dist-legend");\n    clear(track);\n    clear(legend);\n    var described = []'
    ';\n    ["critical", "high", "medium", "low"].forEach(function (k) {\n      var count = sb[k] || 0;\n   '
    '   var color = "var(" + SEV_BAR[k] + ")";\n      if (total > 0 && count > 0) {\n        var seg = el("'
    'i", { title: SEV_LABEL[k] + ": " + count });\n        seg.style.width = (count * 100 / total).toFixed'
    '(2) + "%";\n        seg.style.background = color;\n        track.appendChild(seg);\n      }\n      var s'
    'w = el("i");\n      sw.style.background = color;\n      legend.appendChild(el("span", null, [sw, SEV_L'
    'ABEL[k] + " ", el("b", { textContent: n(count) })]));\n      described.push(SEV_LABEL[k] + " " + coun'
    't);\n    });\n    track.setAttribute("aria-label", "Distribution by severity: " + described.join(", ")'
    ');\n\n    var notes = document.getElementById("status-notes");\n    clear(notes);\n    if (!live) {\n    '
    '  notes.appendChild(el("div", { className: "note sim" }, [icon("alert"), el("span", null, ["Simulate'
    'd data (" + (DATA.provenance || "SIMULATED") + "): demonstration figures generated without reading A'
    'zure; they don\'t describe a real environment."])]));\n    }\n    if (degraded.length) {\n      notes.ap'
    'pendChild(el("div", { className: "note" }, [icon("alert"), el("span", null, [\n        "Partial cover'
    'age: " + degraded.map(function (s) { return s.id + " (" + (STATUS[s.status] || [s.status])[0].toLowe'
    'rCase() + ")"; }).join(", ")\n        + ". What wasn\'t read is a blind spot, not a clean result. ",\n '
    '       el("a", { href: "#sec-coverage", textContent: "See source coverage" })\n      ])]));\n    }\n  }'
    '\n\n  function renderKpis() {\n    var incidents = DATA.incidents || [];\n    var native = incidents.fil'
    'ter(function (r) { return r.category === "native_alert"; });\n    var fired = native.filter(function '
    '(r) { return String(r.monitor_condition || "").toLowerCase() === "fired"; }).length;\n    var sh = in'
    'cidents.filter(function (r) { return r.category === "service_health"; });\n    var issues = sh.filter'
    '(function (r) { return r.signal_type === "ServiceIssue"; }).length;\n    var set = function (id, valu'
    'e) { document.getElementById(id).textContent = value; };\n    set("kpi-native-alerts", n(COUNTS.nativ'
    'e_alerts_total));\n    set("kpi-native-alerts-sub", n(fired) + " " + plural(fired, "active", "active"'
    ') + " (Fired) · " + n(native.length - fired) + " " + plural(native.length - fired, "resolved", "reso'
    'lved"));\n    set("kpi-service-health", n(COUNTS.service_health_total));\n    set("kpi-service-health-'
    'sub", n(issues) + " " + plural(issues, "service issue", "service issues") + " · " + n(sh.length - is'
    'sues) + " " + plural(sh.length - issues, "maintenance event", "maintenance events"));\n    set("kpi-p'
    'osture-anomalies", n((COUNTS.extension_failures_total || 0) + (COUNTS.connectivity_posture_total || '
    '0)));\n    set("kpi-posture-anomalies-sub", n(COUNTS.extension_failures_total) + " failed ext. · " + '
    'n(COUNTS.connectivity_posture_total) + " connectivity/posture");\n    set("kpi-telemetry-anomalies", '
    'n(COUNTS.telemetry_anomalies_total));\n    var kinds = { cpu: 0, mem: 0, disk: 0, hb: 0 };\n    (DATA.'
    'anomalies || []).forEach(function (a) {\n      if (a.category === "telemetry_anomaly") {\n        var '
    'k = String(a.anomaly_kind || "");\n        kinds[/cpu/.test(k) ? "cpu" : /memory/.test(k) ? "mem" : /'
    'disk/.test(k) ? "disk" : "hb"] += 1;\n      }\n    });\n    var kindText = [["cpu", "CPU"], ["mem", "me'
    'mory"], ["disk", "disk"], ["hb", "heartbeat"]].filter(function (k) { return kinds[k[0]]; }).map(func'
    'tion (k) { return n(kinds[k[0]]) + " " + k[1]; }).join(" · ");\n    set("kpi-telemetry-anomalies-sub"'
    ', kindText || "InsightsMetrics, Perf, and Heartbeat");\n    set("kpi-actions-total", n(COUNTS.actions'
    '_total));\n    set("kpi-actions-sub", n(COUNTS.actions_immediate_24h) + " immediate · " + n(COUNTS.ac'
    'tions_short_term_7d) + " short-term · " + n(COUNTS.actions_monthly_cycle) + " monthly");\n    set("kp'
    'i-resources-total", n(COUNTS.resources_total));\n    set("kpi-resources-sub", n(COUNTS.resources_atte'
    'ntion) + " with active findings");\n  }\n\n  /* ---------- Overview ---------- */\n\n  function jumpTo(id'
    ') {\n    var target = document.getElementById(id);\n    if (target) {\n      target.scrollIntoView({ be'
    'havior: REDUCED ? "auto" : "smooth", block: "start" });\n    }\n  }\n\n  function renderOverview() {\n   '
    ' var win = DATA.window || {};\n    var messages = document.getElementById("executive-messages-list");'
    '\n    clear(messages);\n    (DATA.executive_messages || []).forEach(function (msg) {\n      var li = el'
    '("li");\n      var text = String(msg);\n      text.split(/(\\d+(?:,\\d{3})*)/).forEach(function (part, i'
    ', all) {\n        if (!part) {\n          return;\n        }\n        var prev = i > 0 ? all[i - 1].slic'
    'e(-1) : "";\n        var next = i + 1 < all.length ? all[i + 1].charAt(0) : "";\n        var standalon'
    'e = i % 2 === 1 && !/[-:T<\\w]/.test(prev) && !/[-:\\w]/.test(next);\n        li.appendChild(standalone'
    ' ? el("b", { textContent: part }) : document.createTextNode(part));\n      });\n      messages.appendC'
    'hild(li);\n    });\n    document.getElementById("prov-subscription").textContent = DATA.subscription_i'
    'd || "—";\n    document.getElementById("prov-window-label").textContent = win.label || win.period || '
    '"—";\n    document.getElementById("prov-window-range").textContent = (win.start_utc || "—") + " → " +'
    ' (win.end_utc || "—");\n    document.getElementById("prov-cadence").textContent = win.cadence || "Sch'
    'eduled monthly (30 8 1 * * UTC)";\n    document.getElementById("prov-provenance").textContent = (DATA'
    '.provenance || "LIVE") + " · read-only";\n    document.getElementById("reference-utc-label").textCont'
    'ent = DATA.reference_utc || "—";\n\n    var tiles = document.getElementById("horizon-tiles");\n    clea'
    'r(tiles);\n    [["immediate_24h", "Immediate <24h", COUNTS.actions_immediate_24h], ["short_term_7d", '
    '"Short term 1-7 days", COUNTS.actions_short_term_7d], ["monthly_cycle", "Monthly cycle", COUNTS.acti'
    'ons_monthly_cycle]].forEach(function (t) {\n      var tile = el("button", { type: "button", className'
    ': "tile" + (t[0] === "immediate_24h" && t[2] ? " imm" : ""), "aria-label": t[1] + ": " + (t[2] || 0)'
    ' + " actions. Filter the plan by this horizon" }, [el("b", { textContent: n(t[2]) }), el("span", { t'
    'extContent: t[1] })]);\n      tile.addEventListener("click", function () {\n        resetFilters(true)'
    ';\n        document.getElementById("filter-horizon").value = t[0];\n        renderTables();\n        ju'
    'mpTo("sec-actions");\n      });\n      tiles.appendChild(tile);\n    });\n\n    var list = document.getEl'
    'ementById("top-actions");\n    clear(list);\n    var actions = (DATA.actions || []).slice(0, 5);\n    i'
    'f (!actions.length) {\n      list.appendChild(el("li", null, [el("span", { className: "rk", textConte'
    'nt: "—" }), el("div", { className: "t", textContent: "No recommended actions in this window." })]));'
    '\n    }\n    actions.forEach(function (act) {\n      list.appendChild(el("li", null, [\n        el("span'
    '", { className: "rk", textContent: String(act.priority_rank) }),\n        el("div", null, [\n         '
    ' el("div", { className: "t" }, withName(act.title, act.resource_name)),\n          el("div", { classN'
    'ame: "m" }, [pill(act.severity, act.severity_label), el("span", { className: "tag " + (act.horizon |'
    '| ""), textContent: act.horizon_label }), el("span", { textContent: act.resource_name + (act.resourc'
    'e_group ? " · " + rgLabel(act.resource_group) : "") })])\n        ])\n      ]));\n    });\n    document.'
    'getElementById("all-actions-link").textContent = "See all " + n(COUNTS.actions_total) + " actions in'
    ' the plan";\n\n    var streams = [\n      ["native_alert", "Azure Monitor native alerts", COUNTS.native'
    '_alerts_total, "sec-incidents"],\n      ["service_health", "Service Health communications", COUNTS.se'
    'rvice_health_total, "sec-incidents"],\n      ["extension_failure", "Failed VM / Arc extensions", COUN'
    'TS.extension_failures_total, "sec-anomalies"],\n      ["connectivity_posture", "Control plane and con'
    'nectivity", COUNTS.connectivity_posture_total, "sec-anomalies"],\n      ["telemetry_anomaly", "Out-of'
    '-range telemetry", COUNTS.telemetry_anomalies_total, "sec-anomalies"],\n      ["advisor_recommendatio'
    'n", "Azure Advisor recommendations", COUNTS.advisor_recommendations_total, "sec-resources"]\n    ];\n '
    '   var maxStream = Math.max.apply(null, streams.map(function (s) { return s[2] || 0; }).concat([1]))'
    ';\n    var streamBox = document.getElementById("stream-bars");\n    clear(streamBox);\n    streams.forE'
    'ach(function (s) {\n      var bar = el("i");\n      bar.style.width = ((s[2] || 0) * 100 / maxStream).'
    'toFixed(1) + "%";\n      if (!s[2]) {\n        bar.style.minWidth = "0";\n      }\n      var row = el("b'
    'utton", { type: "button", className: "brow", "aria-label": s[1] + ": " + (s[2] || 0) + ". Filter the'
    ' records by this stream" }, [el("span", { className: "bl", textContent: s[1] }), el("span", { classN'
    'ame: "bt" }, [bar]), el("b", { textContent: n(s[2]) })]);\n      row.addEventListener("click", functi'
    'on () {\n        resetFilters(true);\n        document.getElementById("filter-category").value = s[0];'
    '\n        renderTables();\n        jumpTo(s[3]);\n      });\n      streamBox.appendChild(row);\n    });\n\n'
    '    var hot = (DATA.resources || []).map(function (r) {\n      return { r: r, v: (r.incident_count ||'
    ' 0) + (r.anomaly_count || 0) };\n    }).filter(function (x) { return x.v > 0; }).sort(function (x, y)'
    ' {\n      return y.v - x.v || sevKey(x.r) - sevKey(y.r) || String(x.r.resource_name).localeCompare(St'
    'ring(y.r.resource_name));\n    }).slice(0, 6);\n    var resBox = document.getElementById("resource-bar'
    's");\n    clear(resBox);\n    if (!hot.length) {\n      resBox.appendChild(el("p", { className: "empty-'
    'note", textContent: "No inventoried resource has incidents or anomalies in the window." }));\n    }\n '
    '   var maxHot = hot.length ? hot[0].v : 1;\n    hot.forEach(function (x) {\n      var color = "var(" +'
    ' (SEV_BAR[x.r.severity] || "--sev-info-bar") + ")";\n      var bar = el("i");\n      bar.style.width ='
    ' (x.v * 100 / maxHot).toFixed(1) + "%";\n      bar.style.background = color;\n      var dot = el("span'
    '", { className: "dot" });\n      dot.style.background = color;\n      var row = el("button", { type: "'
    'button", className: "brow", title: x.r.resource_id, "aria-label": x.r.resource_name + ": " + x.v + "'
    ' signals, highest severity " + (x.r.severity_label || "") + ". Search the records for this resource"'
    ' }, [\n        el("span", { className: "bl" }, [dot, x.r.resource_name, el("small", { textContent: x.'
    'r.resource_group || "" })]),\n        el("span", { className: "bt" }, [bar]),\n        el("b", { textC'
    'ontent: n(x.v) })\n      ]);\n      row.addEventListener("click", function () {\n        resetFilters(t'
    'rue);\n        document.getElementById("filter-search").value = x.r.resource_name;\n        renderTabl'
    'es();\n        jumpTo(x.r.incident_count ? "sec-incidents" : "sec-anomalies");\n      });\n      resBox'
    '.appendChild(row);\n    });\n  }\n\n  /* ---------- Registers ---------- */\n\n  var TABLES = {};\n  var PA'
    'GE = 50;\n  var lastFilterKey = "";\n\n  function headLabel(text) {\n    var parts = String(text).split('
    '" · ");\n    var out = [];\n    parts.forEach(function (part, i) {\n      if (i) {\n        out.push(" "'
    ');\n      }\n      out.push(el("span", { className: "hg", textContent: part + (i < parts.length - 1 ? '
    '" ·" : "") }));\n    });\n    return out;\n  }\n\n  function setupTable(tableId, cols, rowId) {\n    var t'
    'able = document.getElementById(tableId);\n    var tr = el("tr");\n    cols.forEach(function (c, i) {\n '
    '     var th = el("th", { scope: "col", className: c.num ? "n" : null });\n      if (c.sort) {\n       '
    ' var btn = el("button", { type: "button", className: "sort" }, headLabel(c.head));\n        btn.addEv'
    'entListener("click", function () {\n          var st = TABLES[tableId].sort;\n          TABLES[tableId'
    '].sort = { i: i, dir: st.i === i && st.dir === "ascending" ? "descending" : "ascending" };\n         '
    ' renderTables();\n        });\n        th.appendChild(btn);\n        th.appendChild(el("span", { classN'
    'ame: "th-print", "aria-hidden": "true" }, headLabel(c.head)));\n      } else {\n        headLabel(c.he'
    'ad).forEach(function (part) { th.appendChild(typeof part === "string" ? document.createTextNode(part'
    ') : part); });\n      }\n      tr.appendChild(th);\n    });\n    var thead = table.querySelector("thead"'
    ');\n    clear(thead);\n    thead.appendChild(tr);\n    var more = el("div", { className: "more-row", id'
    ': tableId + "-more", hidden: "hidden" }, [el("span"), el("button", { type: "button", className: "btn'
    ' btn-ghost" })]);\n    more.querySelector("button").addEventListener("click", function () {\n      TAB'
    'LES[tableId].limit += PAGE;\n      renderTables();\n    });\n    table.closest(".table-card").appendChi'
    'ld(more);\n    TABLES[tableId] = { cols: cols, sort: { i: -1, dir: "" }, rowId: rowId, limit: PAGE };'
    '\n  }\n\n  function fillTable(tableId, rows, emptyText) {\n    var t = TABLES[tableId];\n    var table = '
    'document.getElementById(tableId);\n    var tbody = table.querySelector("tbody");\n    var more = docum'
    'ent.getElementById(tableId + "-more");\n    var st = t.sort;\n    var ths = table.querySelectorAll("th'
    'ead th");\n    for (var k = 0; k < ths.length; k++) {\n      if (k === st.i) {\n        ths[k].setAttri'
    'bute("aria-sort", st.dir);\n      } else {\n        ths[k].removeAttribute("aria-sort");\n      }\n    }'
    '\n    if (st.i >= 0) {\n      var acc = t.cols[st.i].sort;\n      var dir = st.dir === "ascending" ? 1 '
    ': -1;\n      rows = rows.map(function (r, idx) { return [r, idx]; }).sort(function (x, y) {\n        v'
    'ar a = acc(x[0]);\n        var c = acc(y[0]);\n        var d = typeof a === "number" && typeof c === "'
    'number" ? a - c : String(a).localeCompare(String(c), "en", { numeric: true, sensitivity: "base" });\n'
    '        return d ? d * dir : x[1] - y[1];\n      }).map(function (p) { return p[0]; });\n    }\n    cle'
    'ar(tbody);\n    var hidden = Math.max(0, rows.length - t.limit);\n    more.hidden = hidden === 0;\n    '
    'if (hidden) {\n      more.querySelector("span").textContent = "Showing " + n(t.limit) + " of " + n(ro'
    'ws.length) + ". Printing includes every row.";\n      more.querySelector("button").textContent = "Sho'
    'w " + n(Math.min(PAGE, hidden)) + " more";\n    }\n    if (!rows.length) {\n      tbody.appendChild(el('
    '"tr", { className: "empty-row" }, [el("td", { colspan: String(t.cols.length), textContent: emptyText'
    ' })]));\n      return;\n    }\n    var frag = document.createDocumentFragment();\n    rows.forEach(funct'
    'ion (row, idx) {\n      var attrs = t.rowId ? { id: t.rowId(row) } : {};\n      if (idx >= t.limit) {\n'
    '        attrs.className = "pg";\n      }\n      var tr = el("tr", attrs);\n      t.cols.forEach(functio'
    'n (c) {\n        var value = c.cell(row);\n        tr.appendChild(el("td", { className: c.cls || (c.nu'
    'm ? "n" : null) }, Array.isArray(value) ? value : [value]));\n      });\n      frag.appendChild(tr);\n '
    '   });\n    tbody.appendChild(frag);\n  }\n\n  function stateCell(row) {\n    var cond = row.monitor_cond'
    'ition || "—";\n    var active = /^(fired|active)$/i.test(cond);\n    return [el("span", { className: "'
    'state" + (active ? " on" : ""), textContent: cond }), el("span", { className: "sm", textContent: row'
    '.state || "" })];\n  }\n\n  function evidenceLinks(ids) {\n    return el("div", { className: "ids" }, (i'
    'ds || []).map(function (id) {\n      var a = el("a", { className: "chip-id", href: "#ev-" + id, textC'
    'ontent: id, title: "Go to evidence " + id });\n      a.addEventListener("click", function (ev) {\n    '
    '    ev.preventDefault();\n        gotoEvidence(id);\n      });\n      return a;\n    }));\n  }\n\n  functio'
    'n gotoEvidence(id) {\n    var row = document.getElementById("ev-" + id);\n    if (!row) {\n      resetF'
    'ilters();\n      row = document.getElementById("ev-" + id);\n    }\n    if (row && row.classList.contai'
    'ns("pg")) {\n      TABLES[row.closest("table").id].limit = Infinity;\n      renderTables();\n      row '
    '= document.getElementById("ev-" + id);\n    }\n    if (!row) {\n      return;\n    }\n    row.scrollIntoV'
    'iew({ behavior: REDUCED ? "auto" : "smooth", block: "center" });\n    row.classList.add("flash");\n   '
    ' setTimeout(function () { row.classList.remove("flash"); }, 1800);\n  }\n\n  function evId(row) {\n    r'
    'eturn "ev-" + row.id;\n  }\n\n  function telemetryText(metrics) {\n    var tm = metrics || {};\n    var p'
    'arts = [];\n    if (tm.cpu_percent) {\n      parts.push("CPU max " + tm.cpu_percent.max + "% (median "'
    ' + tm.cpu_percent.median + "%)");\n    }\n    if (tm.memory_available_mb) {\n      parts.push("Memory m'
    'in " + n(tm.memory_available_mb.min) + " MB");\n    }\n    if (tm.disk_free_percent) {\n      parts.pus'
    'h("Disk free min " + tm.disk_free_percent.min + "%");\n    }\n    if (tm.heartbeat_silence_minutes) {\n'
    '      parts.push("Heartbeat silence " + n(tm.heartbeat_silence_minutes.max) + " min");\n    }\n    ret'
    'urn parts.length ? parts.join(" · ") : "No guest telemetry in the window";\n  }\n\n  function setupTabl'
    'es() {\n    var byName = function (r) { return String(r.resource_name || "").toLowerCase(); };\n    se'
    'tupTable("incidents-table", [\n      { head: "Severity", sort: sevKey, cls: "nw", cell: function (r) '
    '{ return [pill(r.severity, r.severity_label), el("span", { className: "sm", textContent: r.native_se'
    'verity || "" })]; } },\n      { head: "ID · stream", sort: function (r) { return r.id; }, cls: "nw", '
    'cell: idCell },\n      { head: "Resource / service", sort: byName, cls: "w2", cell: function (r) {\n  '
    '      if (r.category === "service_health") {\n          return resourceCell(r.resource_name, "subscri'
    'ption-scope", null, null, (r.regions || []).join(", "));\n        }\n        return resourceCell(r.res'
    'ource_name, r.resource_group, r.resource_type, r.resource_id);\n      } },\n      { head: "State", sor'
    't: function (r) { return (r.monitor_condition || "") + " " + (r.state || ""); }, cls: "nw", cell: st'
    'ateCell },\n      { head: "Signal", sort: function (r) { return r.signal_type || ""; }, cell: functio'
    'n (r) { return [el("div", { textContent: r.signal_type || "—" }), el("span", { className: "sm", text'
    'Content: r.monitor_service || "" })]; } },\n      { head: "Start · updated (UTC)", sort: function (r)'
    ' { return r.start_time_utc || ""; }, cls: "nw", cell: function (r) {\n        return [el("div", { tex'
    'tContent: utc(r.start_time_utc), title: r.start_time_utc }), el("span", { className: "sm", textConte'
    'nt: "updated " + utc(r.last_updated_utc), title: r.last_updated_utc })];\n      } },\n      { head: "D'
    'escription", cls: "wide", cell: function (r) { return [el("div", null, [prose(r.summary)]), extLink('
    'r.learn_url, "Microsoft Learn")]; } }\n    ], evId);\n\n    setupTable("anomalies-table", [\n      { hea'
    'd: "Severity", sort: sevKey, cls: "nw", cell: function (r) { return pill(r.severity, r.severity_labe'
    'l); } },\n      { head: "ID · stream", sort: function (r) { return r.id; }, cls: "nw", cell: idCell }'
    ',\n      { head: "Resource", sort: byName, cls: "w2", cell: function (r) { return resourceCell(r.reso'
    'urce_name, r.resource_group, r.resource_type, r.resource_id); } },\n      { head: "Metric or property'
    '", sort: function (r) { return r.metric_or_field || ""; }, cell: function (r) { return breakable(r.m'
    'etric_or_field, "code"); } },\n      { head: "Observed · reference", cell: function (r) {\n        ret'
    'urn [el("div", null, [el("b", { textContent: withUnit(r.observed_value, r.unit) })]), el("span", { c'
    'lassName: "sm", textContent: "ref. " + withUnit(r.baseline_or_expected, r.unit) })];\n      } },\n    '
    '  { head: "Samples · window", sort: function (r) { return Number(r.sample_count) || 0; }, cell: func'
    'tion (r) {\n        var count = Number(r.sample_count) || 1;\n        return [el("div", { className: "'
    'nw", textContent: n(count) + " " + plural(count, "sample", "samples") }), el("span", { className: "s'
    'm", textContent: (r.window_grain || "PointInTime") + (r.workspace_name ? " · " + r.workspace_name : '
    '"") })];\n      } },\n      { head: "Technical evidence", cls: "wide", cell: function (r) { return [el'
    '("div", null, [prose(r.summary)]), extLink(r.learn_url, "Guidance on Microsoft Learn")]; } }\n    ], '
    'evId);\n\n    setupTable("actions-table", [\n      { head: "Priority", sort: function (r) { return Numb'
    'er(r.priority_rank) || 0; }, cls: "nw", cell: function (r) { return [el("span", { className: "rank",'
    ' textContent: "#" + r.priority_rank }), el("span", { className: "sm id", textContent: r.id })]; } },'
    '\n      { head: "Horizon · severity", sort: function (r) { return (HORIZON_RANK.hasOwnProperty(r.hori'
    'zon) ? HORIZON_RANK[r.horizon] : 9) * 10 + sevKey(r); }, cls: "nw stack", cell: function (r) {\n     '
    '   return [el("div", null, [el("span", { className: "tag " + (r.horizon || ""), textContent: r.horiz'
    'on_label })]), el("div", null, [pill(r.severity, r.severity_label)])];\n      } },\n      { head: "Rec'
    'ommended action", sort: function (r) { return r.title || ""; }, cls: "w3", cell: function (r) {\n    '
    '    return el("div", { className: "res", title: r.resource_id || null }, [el("b", null, withName(r.t'
    'itle, r.resource_name)), el("span", { className: "sm", textContent: (r.resource_name || "") + (r.res'
    'ource_group ? " · " + rgLabel(r.resource_group) : "") }), portalUrl(r.resource_id) ? extLink(portalU'
    'rl(r.resource_id), "Portal") : null]);\n      } },\n      { head: "Owner · effort", sort: function (r)'
    ' { return r.owner_scope || ""; }, cls: "w1", cell: function (r) { return [el("div", { textContent: r'
    '.owner_scope || "—" }), el("span", { className: "sm", textContent: "Effort: " + (r.effort_label || "'
    '—") })]; } },\n      { head: "Evidence", cell: function (r) { return evidenceLinks(r.linked_evidence_'
    'ids); } },\n      { head: "Guidance for human review", cls: "wide", cell: function (r) {\n        retu'
    'rn [el("div", null, [prose(r.recommendation)]), el("span", { className: "sm" }, ["Evidence: ", prose'
    '(r.evidence_summary)]), extLink(r.learn_url, "Microsoft Learn reference")];\n      } }\n    ]);\n\n    s'
    'etupTable("resources-table", [\n      { head: "Resource", sort: byName, cls: "w2", cell: function (r)'
    ' { return resourceCell(r.resource_name, r.resource_group, null, r.resource_id, r.location); } },\n   '
    '   { head: "Type · hosting", sort: function (r) { return typeLabel(r.resource_type); }, cell: functi'
    'on (r) { return [el("div", { textContent: typeLabel(r.resource_type) }), el("span", { className: "sm'
    '" }, [breakable(r.resource_type, "code"), " · " + String(r.hosting || "").toUpperCase()])]; } },\n   '
    '   { head: "Operational status", sort: function (r) { return (r.status === "attention" ? 0 : r.statu'
    's === "review" ? 1 : 2) * 10 + sevKey(r); }, cls: "nw", cell: function (r) {\n        return [r.statu'
    's === "healthy" ? pill("ok", "Normal") : pill(r.severity, r.severity_label), el("span", { className:'
    ' "sm", textContent: r.operational_state || "" })];\n      } },\n      { head: "Incidents", num: true, '
    'sort: function (r) { return r.incident_count || 0; }, cell: function (r) { return n(r.incident_count'
    '); } },\n      { head: "Anomalies", num: true, sort: function (r) { return r.anomaly_count || 0; }, c'
    'ell: function (r) { return n(r.anomaly_count); } },\n      { head: "Failed ext.", num: true, sort: fu'
    'nction (r) { return r.failed_extension_count || 0; }, cell: function (r) { return n(r.failed_extensi'
    'on_count) + " / " + n(r.extensions_total); } },\n      { head: "Actions", num: true, sort: function ('
    'r) { return r.action_count || 0; }, cell: function (r) { return n(r.action_count); } },\n      { head'
    ': "Telemetry summary", cls: "w2", cell: function (r) { return telemetryText(r.telemetry_metrics); } '
    '}\n    ]);\n\n    setupTable("advisor-table", [\n      { head: "Impact", sort: sevKey, cls: "nw", cell: '
    'function (r) { return [pill(r.severity, r.severity_label, "Impact " + (r.impact || "")), el("span", '
    '{ className: "sm", textContent: r.advisor_category || "" })]; } },\n      { head: "ID", sort: functio'
    'n (r) { return r.id; }, cls: "nw", cell: function (r) { return el("span", { className: "id", textCon'
    'tent: r.id }); } },\n      { head: "Resource", sort: byName, cls: "w2", cell: function (r) { return r'
    'esourceCell(r.resource_name, r.resource_group, r.resource_type, r.resource_id); } },\n      { head: "'
    'Detected problem", cls: "w2", cell: function (r) { return prose(r.problem); } },\n      { head: "Reco'
    'mmended solution", cls: "wide", cell: function (r) { return [el("div", null, [prose(r.solution)]), e'
    'xtLink(r.learn_url, "Azure Advisor on Microsoft Learn")]; } },\n      { head: "Updated (UTC)", sort: '
    'function (r) { return r.last_updated_utc || ""; }, cls: "nw", cell: function (r) { return el("span",'
    ' { textContent: utc(r.last_updated_utc), title: r.last_updated_utc }); } }\n    ], evId);\n\n    setupT'
    'able("sources-table", [\n      { head: "Source", cls: "nw", cell: function (r) { return el("span", { '
    'className: "id", textContent: r.id }); } },\n      { head: "Status", cls: "nw", cell: function (r) { '
    'var s = STATUS[r.status] || [r.status, "critical"]; return pill(s[1], s[0], r.status); } },\n      { '
    'head: "Records", num: true, cell: function (r) { return n(r.records); } },\n      { head: "Pages", nu'
    'm: true, cell: function (r) { return n(r.pages); } },\n      { head: "Pagination complete", cls: "nw"'
    ', cell: function (r) { return r.pagination_complete ? "Yes" : "No"; } },\n      { head: "Read signatu'
    're and detail", cls: "wide", cell: function (r) {\n        var kids = [breakable(r.read_signature || '
    '"—", "code")];\n        if (Array.isArray(r.workspaces_queried) && r.workspaces_queried.length) {\n   '
    '       kids.push(el("ul", { className: "wslist" }, r.workspaces_queried.map(function (w) {\n         '
    '   return el("li", { textContent: w.workspace_name + " · " + ((STATUS[w.status] || [w.status])[0]) +'
    ' " · " + n(w.records) + " " + plural(w.records, "row", "rows") });\n          })));\n        }\n       '
    ' (r.errors || []).forEach(function (e) {\n          kids.push(el("div", { className: "errbox" }, [el('
    '"b", { textContent: e.code || "error" }), " · " + (e.message || "") + (e.http_status ? " (HTTP " + e'
    '.http_status + ")" : "")]));\n        });\n        return kids;\n      } },\n      { head: "Notes and sc'
    'ope", cls: "w2", cell: function (r) { return r.note || "—"; } }\n    ]);\n  }\n\n  function matchesCommo'
    'nFilter(row, cat, sev, query) {\n    if (cat !== "all" && row.category !== cat) {\n      return false;'
    '\n    }\n    if (sev !== "all" && row.severity !== sev) {\n      return false;\n    }\n    if (query) {\n '
    '     var hay = [row.id, row.title, row.resource_name, row.resource_id, row.resource_group, row.summa'
    'ry, row.metric_or_field, row.signal_type, row.owner_scope, row.recommendation].join(" ").toLowerCase'
    '();\n      if (hay.indexOf(query) < 0) {\n        return false;\n      }\n    }\n    return true;\n  }\n\n  '
    'function renderTables() {\n    var cat = document.getElementById("filter-category").value;\n    var se'
    'v = document.getElementById("filter-severity").value;\n    var hor = document.getElementById("filter-'
    'horizon").value;\n    var rawQuery = (document.getElementById("filter-search").value || "").trim();\n '
    '   var query = rawQuery.toLowerCase();\n    var filterKey = [cat, sev, hor, query].join("\\u0001");\n  '
    '  if (filterKey !== lastFilterKey) {\n      lastFilterKey = filterKey;\n      Object.keys(TABLES).forE'
    'ach(function (id) { TABLES[id].limit = PAGE; });\n    }\n\n    var incidents = (DATA.incidents || []).f'
    'ilter(function (row) { return matchesCommonFilter(row, cat, sev, query); });\n    var anomalies = (DA'
    'TA.anomalies || []).filter(function (row) { return matchesCommonFilter(row, cat, sev, query); });\n  '
    '  var actions = (DATA.actions || []).filter(function (row) {\n      return (hor === "all" || row.hori'
    'zon === hor) && matchesCommonFilter(row, cat, sev, query);\n    });\n    var resources = (DATA.resourc'
    'es || []).filter(function (row) {\n      if (sev !== "all" && row.severity !== sev) {\n        return '
    'false;\n      }\n      if (query) {\n        var hay = [row.resource_name, row.resource_id, row.resourc'
    'e_group, row.resource_type, row.operational_state].join(" ").toLowerCase();\n        if (hay.indexOf('
    'query) < 0) {\n          return false;\n        }\n      }\n      return true;\n    });\n    var advisor ='
    ' (DATA.advisor || []).filter(function (row) { return matchesCommonFilter(row, cat, sev, query); });\n'
    '\n    var counts = { incidents: incidents.length, anomalies: anomalies.length, actions: actions.lengt'
    'h, resources: resources.length, advisor: advisor.length };\n    Object.keys(counts).forEach(function '
    '(key) {\n      document.getElementById(key + "-count").textContent = String(counts[key]);\n      docum'
    'ent.getElementById(key + "-total").textContent = String((DATA[key] || []).length);\n      var nav = d'
    'ocument.getElementById("nav-" + key + "-count");\n      if (nav) {\n        nav.textContent = String(c'
    'ounts[key]);\n      }\n    });\n\n    var active = cat !== "all" || sev !== "all" || hor !== "all" || qu'
    'ery;\n    var status = document.getElementById("filter-status-summary");\n    clear(status);\n    [b(in'
    'cidents.length), " " + plural(incidents.length, "incident", "incidents") + " · ", b(anomalies.length'
    '), " " + plural(anomalies.length, "anomaly", "anomalies") + " · ", b(actions.length), " " + plural(a'
    'ctions.length, "action", "actions") + " · ", b(resources.length), " " + plural(resources.length, "re'
    'source", "resources"), active ? " (filter active)" : " (no filters)"].forEach(function (part) {\n    '
    '  status.appendChild(typeof part === "string" ? document.createTextNode(part) : part);\n    });\n    v'
    'ar labelOf = function (id) { var s = document.getElementById(id); return s.options[s.selectedIndex].'
    'text; };\n    document.getElementById("print-filter-note").textContent = active\n      ? "Filters appl'
    'ied when printing: " + [cat !== "all" ? labelOf("filter-category") : "", sev !== "all" ? "severity "'
    ' + labelOf("filter-severity") : "", hor !== "all" ? "horizon " + labelOf("filter-horizon") : "", que'
    'ry ? "search “" + rawQuery + "”" : ""].filter(Boolean).join(" · ")\n      : "";\n\n    var none = funct'
    'ion (key, filtered, empty) { return (DATA[key] || []).length ? filtered : empty; };\n    fillTable("i'
    'ncidents-table", incidents, none("incidents", "No incidents or alerts match the current filters.", "'
    'No incidents or alerts in the evaluated window."));\n    fillTable("anomalies-table", anomalies, none'
    '("anomalies", "No technical anomalies match the current filters.", "No technical anomalies in the ev'
    'aluated window."));\n    fillTable("actions-table", actions, none("actions", "No recommended actions '
    'match the current filters.", "No recommended actions for this window."));\n    fillTable("resources-t'
    'able", resources, none("resources", "No inventoried resources match the current filter.", "No invent'
    'oried resources in scope."));\n    fillTable("advisor-table", advisor, none("advisor", "No cached Azu'
    're Advisor recommendations match the current filter.", "No cached Azure Advisor recommendations for '
    'the subscription."));\n  }\n\n  function resetFilters(silent) {\n    document.getElementById("filter-cat'
    'egory").value = "all";\n    document.getElementById("filter-severity").value = "all";\n    document.ge'
    'tElementById("filter-horizon").value = "all";\n    document.getElementById("filter-search").value = "'
    '";\n    if (!silent) {\n      renderTables();\n    }\n  }\n\n  function renderCoverage() {\n    var sources'
    ' = DATA.sources || [];\n    document.getElementById("sources-count").textContent = String(sources.len'
    'gth);\n    document.getElementById("nav-sources-count").textContent = String(sources.length);\n    fil'
    'lTable("sources-table", sources, "The data model has no source receipts.");\n\n    var meth = DATA.met'
    'hodology || {};\n    var methList = document.getElementById("methodology-list");\n    clear(methList);'
    '\n    (meth.limitations || []).forEach(function (lim) {\n      methList.appendChild(el("li", { textCon'
    'tent: lim }));\n    });\n    var facts = document.getElementById("method-facts");\n    clear(facts);\n  '
    '  [\n      ["Mode", meth.read_only === false ? "Write" : "Read-only"],\n      ["Official SLA calculati'
    'on", meth.official_sla_calculation ? "Yes" : "No"],\n      ["Schedule", (meth.scheduled_cadence_cron '
    '|| "30 8 1 * *") + " (UTC)"],\n      ["Default period", meth.scheduled_default_period || "previous_mo'
    'nth"],\n      ["Supported periods", (meth.supported_periods || []).join(", ") || "—"]\n    ].forEach(f'
    'unction (f) {\n      facts.appendChild(el("dt", { textContent: f[0] }));\n      facts.appendChild(el("'
    'dd", { textContent: f[1] }));\n    });\n    var streams = document.getElementById("method-streams");\n '
    '   clear(streams);\n    (meth.evidence_streams || []).forEach(function (s) {\n      streams.appendChil'
    'd(el("li", { textContent: s }));\n    });\n\n    var client = (DATA.client || {}).name || "Customer";\n '
    '   document.getElementById("footer-left").textContent = "Generated by Azure SRE Agent · Read-only · '
    'Reference " + utc(DATA.reference_utc) + " UTC · " + (DATA.schema_version || "");\n    document.getEle'
    'mentById("footer-right").textContent = client;\n    var page = el("style", { textContent: "@page{@bot'
    'tom-left{content:\\"" + ("Operations report · " + client + " · " + ((DATA.window || {}).label || "") '
    '+ " · " + utc(DATA.reference_utc) + " UTC").replace(/["\\\\\\r\\n]/g, " ") + "\\";font:8.5pt \'Segoe UI\',s'
    'ans-serif;color:#5A687A}}" });\n    document.head.appendChild(page);\n  }\n\n  function watchSections() '
    '{\n    if (!("IntersectionObserver" in window)) {\n      return;\n    }\n    var links = {};\n    Array.p'
    'rototype.forEach.call(document.querySelectorAll("#section-nav a"), function (a) {\n      links[a.getA'
    'ttribute("href").slice(1)] = a;\n    });\n    var observer = new IntersectionObserver(function (entrie'
    's) {\n      entries.forEach(function (entry) {\n        if (entry.isIntersecting) {\n          Object.k'
    'eys(links).forEach(function (k) { links[k].removeAttribute("aria-current"); });\n          if (links['
    'entry.target.id]) {\n            links[entry.target.id].setAttribute("aria-current", "true");\n       '
    '   }\n        }\n      });\n    }, { rootMargin: "-35% 0px -60% 0px" });\n    Array.prototype.forEach.ca'
    'll(document.querySelectorAll("#top, .sec"), function (section) {\n      observer.observe(section);\n  '
    '  });\n  }\n\n  /* ---------- Exports ---------- */\n\n  function downloadBlob(filename, content, mime) {'
    '\n    var blob = new Blob([content], { type: mime });\n    var url = URL.createObjectURL(blob);\n    va'
    'r link = document.createElement("a");\n    link.href = url;\n    link.download = filename;\n    documen'
    't.body.appendChild(link);\n    link.click();\n    document.body.removeChild(link);\n    setTimeout(func'
    'tion () { URL.revokeObjectURL(url); }, 500);\n  }\n\n  function csvEscape(val) {\n    if (val === null |'
    '| val === undefined) {\n      return \'""\';\n    }\n    var str = typeof val === "object" ? JSON.stringi'
    'fy(val) : String(val);\n    if (/^[=+\\-@\\t\\r\\n]/.test(str.trimLeft())) {\n      str = "\'" + str;\n    }'
    '\n    return \'"\' + str.replace(/"/g, \'""\') + \'"\';\n  }\n\n  function exportIncidentsCsv() {\n    var head'
    'ers = ["record_kind", "id", "category", "severity", "title", "resource_name", "resource_group", "met'
    'ric_or_signal", "observed_value", "observed_at_utc", "summary"];\n    var lines = [headers.join(",")]'
    ';\n    (DATA.incidents || []).forEach(function (inc) {\n      lines.push([\n        "incident", inc.id,'
    ' inc.category, inc.severity, inc.title, inc.resource_name,\n        inc.resource_group, inc.signal_ty'
    'pe, inc.native_severity, inc.last_updated_utc, inc.summary\n      ].map(csvEscape).join(","));\n    })'
    ';\n    (DATA.anomalies || []).forEach(function (anom) {\n      lines.push([\n        "anomaly", anom.id'
    ', anom.category, anom.severity, anom.title, anom.resource_name,\n        anom.resource_group, anom.me'
    'tric_or_field, anom.observed_value, anom.observed_at_utc, anom.summary\n      ].map(csvEscape).join("'
    ',"));\n    });\n    downloadBlob("ops-digest-incidents-anomalies.csv", "\\uFEFF" + lines.join("\\r\\n"), '
    '"text/csv;charset=utf-8");\n  }\n\n  function exportActionsCsv() {\n    var headers = ["priority_rank", '
    '"id", "horizon_label", "severity", "category", "title", "resource_name", "resource_group", "owner_sc'
    'ope", "effort_label", "linked_evidence_ids", "recommendation"];\n    var lines = [headers.join(",")];'
    '\n    (DATA.actions || []).forEach(function (act) {\n      lines.push([\n        act.priority_rank, act'
    '.id, act.horizon_label, act.severity, act.category, act.title,\n        act.resource_name, act.resour'
    'ce_group, act.owner_scope, act.effort_label,\n        (act.linked_evidence_ids || []).join(";"), act.'
    'recommendation\n      ].map(csvEscape).join(","));\n    });\n    downloadBlob("ops-digest-recommended-a'
    'ctions.csv", "\\uFEFF" + lines.join("\\r\\n"), "text/csv;charset=utf-8");\n  }\n\n  /* ---------- Wiring -'
    '--------- */\n\n  ["filter-category", "filter-severity", "filter-horizon"].forEach(function (id) {\n   '
    ' document.getElementById(id).addEventListener("change", renderTables);\n  });\n  document.getElementBy'
    'Id("filter-search").addEventListener("input", renderTables);\n  document.getElementById("filter-reset'
    '").addEventListener("click", function () { resetFilters(); });\n\n  document.getElementById("theme-tog'
    'gle").addEventListener("click", function () {\n    var root = document.documentElement;\n    var next '
    '= root.getAttribute("data-theme") === "dark" ? "light" : "dark";\n    root.setAttribute("data-theme",'
    ' next);\n    this.querySelector(".lbl").textContent = next === "dark" ? "Light mode" : "Dark mode";\n '
    '   this.title = this.querySelector(".lbl").textContent;\n    this.querySelector("path").setAttribute('
    '"d", next === "dark" ? PATHS.sun : PATHS.moon);\n  });\n\n  document.getElementById("btn-export-json").'
    'addEventListener("click", function () {\n    downloadBlob("ops-digest-snapshot.json", JSON.stringify('
    'DATA, null, 2), "application/json;charset=utf-8");\n  });\n  document.getElementById("btn-export-incid'
    'ents-csv").addEventListener("click", exportIncidentsCsv);\n  document.getElementById("btn-export-acti'
    'ons-csv").addEventListener("click", exportActionsCsv);\n  document.getElementById("btn-print").addEve'
    'ntListener("click", function () {\n    window.print();\n  });\n\n  renderBranding();\n  renderHero();\n  r'
    'enderKpis();\n  setupTables();\n  renderOverview();\n  renderTables();\n  renderCoverage();\n  watchSecti'
    'ons();\n})();\n</script>\n</body>\n</html>\n'
)
# END BUILD-TIME ASSETS


SIDECAR_TOKEN_ISSUER = "adc-msi-sidecar"


def normalize_sidecar_claims(claims):
    """Map Azure SRE Agent sandbox token claims onto the standard Entra names.

    Python tools in the SRE Agent sandbox receive placeholder tokens issued by the identity sidecar
    (iss "adc-msi-sidecar") that the platform proxy replaces with the real managed identity token at egress.
    They carry tid, clientId and scp instead of aud/appid, so tenant, client and audience stay verifiable.
    """
    if not isinstance(claims, dict) or claims.get("iss") != SIDECAR_TOKEN_ISSUER:
        return claims
    scope = claims.get("scp") if isinstance(claims.get("scp"), str) else ""
    audience = scope[:-len("/.default")] if scope.endswith("/.default") else scope
    if audience.rstrip("/").lower() == "https://management.core.windows.net":
        audience = "https://management.azure.com"
    return dict(claims, appid=claims.get("clientId") or claims.get("cid") or None, aud=audience or None)


class EvidenceError(RuntimeError):
    def __init__(self, code, message, source="digest", http_status=None):
        super().__init__(message)
        self.code = code
        self.source = source
        self.http_status = http_status

    def public(self):
        result = {
            "code": self.code,
            "message": str(self),
            "source_id": self.source,
            "http_status": self.http_status,
        }
        return result


def utc_now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_utc(value, source="normalization"):
    if not isinstance(value, str) or not value or len(value) > 48:
        raise EvidenceError("invalid_timestamp", "Expected an ISO 8601 UTC timestamp.", source)
    cleaned = value.strip()
    if cleaned.endswith("Z"):
        cleaned = cleaned[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(cleaned)
    except ValueError as exc:
        raise EvidenceError("invalid_timestamp", "Could not parse ISO 8601 timestamp.", source) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise EvidenceError("invalid_timestamp", "Timestamp must include an explicit timezone offset.", source)
    return parsed.astimezone(timezone.utc)


def iso_utc(dt):
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def obj(value, source="normalization"):
    if not isinstance(value, dict):
        raise EvidenceError("invalid_shape", "Expected a JSON object from source.", source)
    return value


def array(value, source="normalization"):
    if not isinstance(value, list) or any(not isinstance(row, dict) for row in value):
        raise EvidenceError("invalid_shape", "Expected a JSON array of objects from source.", source)
    return value


def pick(value, *keys):
    current = value
    for key in keys:
        if not isinstance(current, dict) or key not in current:
            return None
        current = current[key]
    return current


def text(value, source="normalization", maximum=8192):
    if value is None:
        return None
    if not isinstance(value, str) or len(value) > maximum or any(ord(ch) < 32 and ch not in ("\t", "\n", "\r") for ch in value):
        raise EvidenceError("invalid_field", "Source text field has an invalid type, control char, or length.", source)
    return value.strip()


def number(value, source="normalization"):
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise EvidenceError("invalid_field", "Source numeric value must be a finite number.", source)
    return float(value)


def grouped(value):
    return format(value, ",") if isinstance(value, (int, float)) and not isinstance(value, bool) else str(value)


def boolean(value, source="normalization"):
    if value is not None and not isinstance(value, bool):
        raise EvidenceError("invalid_field", "Source boolean field has an invalid type.", source)
    return value


def tags_map(value, source="normalization"):
    if value is None:
        return {}
    raw_tags = obj(value, source)
    sanitized = {}
    for key, item in raw_tags.items():
        k = text(str(key), source, 256)
        if not k:
            continue
        if any(word in k.lower() for word in ("secret", "password", "token", "key", "sas", "credential", "connectionstring")):
            continue
        if isinstance(item, (str, int, float, bool)) or item is None:
            sanitized[k] = text(str(item), source, 512) if item is not None else None
    return sanitized


def validate_guid(value, field_name):
    try:
        if not isinstance(value, str) or str(UUID(value)) != value.lower() or UUID(value).int == 0:
            raise ValueError
    except (ValueError, AttributeError) as exc:
        raise EvidenceError(
            "configuration_required",
            "Configure the explicit GUID constant " + field_name + " before running live collection.",
            "configuration",
        ) from exc
    return value.lower()


def validate_logo(uri, alt=CLIENT_LOGO_ALT):
    if uri == "":
        return
    if not isinstance(uri, str) or len(uri) > 140_000:
        raise EvidenceError("invalid_logo", "Optional logo must be a bounded inline PNG/JPEG data URI.", "branding")
    match = re.fullmatch(r"data:image/(png|jpeg);base64,([A-Za-z0-9+/=]+)", uri)
    if not match:
        raise EvidenceError("invalid_logo", "Only inline PNG/JPEG MIME with canonical base64 is allowed.", "branding")
    try:
        data = base64.b64decode(match[2], validate=True)
    except (ValueError, binascii.Error) as exc:
        raise EvidenceError("invalid_logo", "Invalid logo base64 payload.", "branding") from exc
    if not 1 <= len(data) <= MAX_LOGO_BYTES:
        raise EvidenceError("invalid_logo", "Optional raster logo must contain 1..100000 bytes.", "branding")
    if not isinstance(alt, str) or not alt.strip() or len(alt) > 120 or re.search(r"[\x00-\x1f\x7f]", alt):
        raise EvidenceError("invalid_logo", "Provide 1..120 plain characters of descriptive logo alt text.", "branding")
    try:
        from PIL import Image, ImageFile, UnidentifiedImageError
    except ImportError as exc:
        raise EvidenceError("dependency_missing", "A configured logo requires Pillow for raster validation.", "branding") from exc
    if ImageFile.LOAD_TRUNCATED_IMAGES:
        raise EvidenceError("unsafe_decoder_settings", "Truncated-image decoding must not be enabled.", "branding")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data), formats=["PNG", "JPEG"]) as image:
                width, height = image.size
                if (
                    image.format != ("PNG" if match[1] == "png" else "JPEG")
                    or not 1 <= width <= MAX_LOGO_DIMENSION
                    or not 1 <= height <= MAX_LOGO_DIMENSION
                    or getattr(image, "n_frames", 1) != 1
                ):
                    raise EvidenceError("invalid_logo", "Use one PNG/JPEG frame, matching MIME, at most 2048x2048 pixels.", "branding")
                image.verify()
            with Image.open(io.BytesIO(data), formats=["PNG", "JPEG"]) as image:
                image.load()
    except (OSError, ValueError, SyntaxError, UnidentifiedImageError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise EvidenceError("invalid_logo", "The optional logo is not a complete, valid single-frame PNG/JPEG raster.", "branding") from exc


def validate_config():
    validate_logo(CLIENT_LOGO_DATA_URI, CLIENT_LOGO_ALT)
    if not isinstance(CLIENT_NAME, str) or not 1 <= len(CLIENT_NAME.strip()) <= 120 or re.search(r"[\x00-\x1f\x7f]", CLIENT_NAME):
        raise EvidenceError("configuration_required", "CLIENT_NAME must be 1..120 plain characters.", "configuration")
    if not isinstance(CLIENT_LOGO_ALT, str) or not 1 <= len(CLIENT_LOGO_ALT.strip()) <= 120 or re.search(r"[\x00-\x1f\x7f]", CLIENT_LOGO_ALT):
        raise EvidenceError("configuration_required", "CLIENT_LOGO_ALT must be 1..120 plain characters.", "configuration")
    sub_id = validate_guid(SUBSCRIPTION_ID, "SUBSCRIPTION_ID")
    client_id = validate_guid(MANAGED_IDENTITY_CLIENT_ID, "MANAGED_IDENTITY_CLIENT_ID")
    if not isinstance(APPROVED_LOG_WORKSPACES, list) or len(APPROVED_LOG_WORKSPACES) > MAX_WORKSPACES:
        raise EvidenceError("configuration_required", "Configure 0..10 entries in APPROVED_LOG_WORKSPACES.", "configuration")
    workspaces = []
    seen_names = set()
    seen_ids = set()
    for item in APPROVED_LOG_WORKSPACES:
        if not isinstance(item, dict):
            raise EvidenceError("configuration_required", "Each APPROVED_LOG_WORKSPACES entry must be a dict.", "configuration")
        w_name = item.get("name")
        w_rg = item.get("resource_group")
        if not isinstance(w_name, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", w_name):
            raise EvidenceError("configuration_required", "Configure a valid workspace name in APPROVED_LOG_WORKSPACES.", "configuration")
        if not isinstance(w_rg, str) or not re.fullmatch(r"[A-Za-z0-9_.()-]{1,90}", w_rg):
            raise EvidenceError("configuration_required", "Configure a valid resource_group in APPROVED_LOG_WORKSPACES.", "configuration")
        w_guid = validate_guid(item.get("customer_id"), "APPROVED_LOG_WORKSPACES.customer_id")
        if w_name.lower() in seen_names or w_guid in seen_ids:
            raise EvidenceError("configuration_required", "Duplicate workspace name or customer_id in APPROVED_LOG_WORKSPACES.", "configuration")
        seen_names.add(w_name.lower())
        seen_ids.add(w_guid)
        workspaces.append({
            "name": w_name,
            "customer_id": w_guid,
            "resource_group": w_rg,
        })
    return {
        "subscription_id": sub_id,
        "client_id": client_id,
        "workspaces": workspaces,
        "client_name": CLIENT_NAME.strip(),
    }


def compute_window(period, reference_str):
    ref_dt = parse_utc(reference_str, "parameters")
    if period == "previous_month":
        end_dt = ref_dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        start_dt = (end_dt - timedelta(days=1)).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        label = "Previous calendar month (" + start_dt.strftime("%Y-%m") + ")"
        cadence = "Scheduled monthly run (30 8 1 * * UTC) / closed month"
        grain = "PT1H"
    elif period == "last_30d":
        end_dt = ref_dt.replace(microsecond=0)
        start_dt = end_dt - timedelta(days=30)
        label = "Last 30 days (rolling)"
        cadence = "On demand (rolling 30-day window)"
        grain = "PT1H"
    elif period == "last_7d":
        end_dt = ref_dt.replace(microsecond=0)
        start_dt = end_dt - timedelta(days=7)
        label = "Last 7 days (rolling)"
        cadence = "On demand (rolling 7-day weekly window)"
        grain = "PT1H"
    elif period == "last_24h":
        end_dt = ref_dt.replace(microsecond=0)
        start_dt = end_dt - timedelta(hours=24)
        label = "Last 24 hours"
        cadence = "On demand (24-hour on-call shift)"
        grain = "PT5M"
    else:
        raise EvidenceError("invalid_parameter", "period must use its declared enum.", "parameters")
    start_iso = iso_utc(start_dt)
    end_iso = iso_utc(end_dt)
    duration_hours = max(1, int(round((end_dt - start_dt).total_seconds() / 3600.0)))
    return {
        "period": period,
        "label": label,
        "cadence": cadence,
        "start_utc": start_iso,
        "end_utc": end_iso,
        "timespan_iso": start_iso + "/" + end_iso,
        "grain": grain,
        "duration_hours": duration_hours,
    }


def validate_parameters(
    operation="report",
    period="previous_month",
    view="summary",
    category="all",
    severity="all",
    resource_name="",
    limit=25,
    offset=0,
    reference_utc=None,
):
    for key, value, choices in (
        ("operation", operation, OPERATIONS),
        ("period", period, PERIODS),
        ("view", view, VIEWS),
        ("category", category, CATEGORIES),
        ("severity", severity, SEVERITIES),
    ):
        if not isinstance(value, str) or value not in choices:
            raise EvidenceError("invalid_parameter", key + " must use its declared enum.", "parameters")
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
        raise EvidenceError("invalid_parameter", "limit must be an integer from 1 to 100.", "parameters")
    if isinstance(offset, bool) or not isinstance(offset, int) or not 0 <= offset <= 500_000:
        raise EvidenceError("invalid_parameter", "offset must be an integer from 0 to 500000.", "parameters")
    if not isinstance(resource_name, str) or len(resource_name) > 128 or (
        resource_name and not re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", resource_name)
    ):
        raise EvidenceError(
            "invalid_parameter",
            "resource_name must be a bounded resource name (^[A-Za-z0-9_.-]{0,128}$), never a path, URL, or query.",
            "parameters",
        )
    has_filters = any((view != "summary", category != "all", severity != "all", bool(resource_name), limit != 25, offset != 0))
    if operation == "report" and has_filters:
        raise EvidenceError(
            "invalid_combination",
            "operation=report writes complete unfiltered evidence for the requested period; use defaults for view/category/severity/resource_name/limit/offset.",
            "parameters",
        )
    if operation == "query":
        if view in ("summary", "coverage") and any((category != "all", severity != "all", bool(resource_name))):
            raise EvidenceError(
                "invalid_combination",
                "summary and coverage views do not accept category, severity, or resource_name filters.",
                "parameters",
            )
        if view == "resources" and category != "all":
            raise EvidenceError(
                "invalid_combination",
                "view=resources aggregates across categories; use category=all.",
                "parameters",
            )
        if view == "incidents" and category not in ("all", "native_alert", "service_health"):
            raise EvidenceError(
                "invalid_combination",
                "view=incidents supports category in ('all', 'native_alert', 'service_health').",
                "parameters",
            )
        if view == "anomalies" and category not in ("all", "extension_failure", "connectivity_posture", "telemetry_anomaly"):
            raise EvidenceError(
                "invalid_combination",
                "view=anomalies supports category in ('all', 'extension_failure', 'connectivity_posture', 'telemetry_anomaly').",
                "parameters",
            )
        if view == "advisor" and category not in ("all", "advisor_recommendation"):
            raise EvidenceError(
                "invalid_combination",
                "view=advisor supports category in ('all', 'advisor_recommendation').",
                "parameters",
            )
    ref = reference_utc or utc_now()
    window = compute_window(period, ref)
    return {
        "operation": operation,
        "period": period,
        "view": view,
        "category": category,
        "severity": severity,
        "resource_name": resource_name,
        "limit": limit,
        "offset": offset,
        "window": window,
    }


def response_bytes(value):
    return len(json.dumps(value, allow_nan=False).encode("utf-8"))


def ensure_response(value):
    if response_bytes(value) > TRANSPORT_BYTES:
        raise EvidenceError(
            "transport_size_exceeded",
            "Default-serialized response exceeds 3500 bytes; no malformed or truncated JSON is returned.",
            "transport",
        )
    return value


def arm_resource_id(value, subscription_id=None, source="scope"):
    raw = text(value, source, 2048)
    if not raw:
        raise EvidenceError("invalid_resource_id", "A scoped ARM resource ID is required.", source)
    if re.search(r"[\x00-\x1f\x7f?#\\%]", raw):
        raise EvidenceError("invalid_resource_id", "Resource ID contains unsafe characters.", source)
    cleaned = raw.rstrip("/")
    parts = cleaned.split("/")
    if (
        len(parts) < 5
        or parts[0] != ""
        or parts[1].lower() != "subscriptions"
        or any(part in ("", ".", "..") for part in parts[1:])
    ):
        raise EvidenceError("invalid_resource_id", "Resource ID has invalid ARM path structure.", source)
    try:
        sub_guid = str(UUID(parts[2])).lower()
    except ValueError as exc:
        raise EvidenceError("invalid_resource_id", "Resource ID subscription is not a valid GUID.", source) from exc
    if subscription_id and sub_guid != subscription_id.lower():
        raise EvidenceError("invalid_resource_id", "Resource ID belongs to a different subscription.", source)
    return cleaned


def extract_rg_and_type(resource_id):
    if not isinstance(resource_id, str) or not resource_id.startswith("/"):
        return "subscription-scope", "microsoft.resources/subscriptions", resource_id or "subscription"
    parts = resource_id.rstrip("/").split("/")
    rg = "subscription-scope"
    if len(parts) >= 5 and parts[3].lower() == "resourcegroups":
        rg = parts[4]
    if "providers" in [p.lower() for p in parts]:
        idx = [p.lower() for p in parts].index("providers")
        if idx + 2 < len(parts):
            provider = parts[idx + 1]
            type_segments = parts[idx + 2::2]
            rtype = (provider + "/" + "/".join(type_segments)).lower()
            rname = parts[-1]
            return rg, rtype, rname
    return rg, "microsoft.resources/resource", parts[-1]


def source_receipt(source_id, reference, status="complete", note="", window=None, **extra):
    return {
        "id": source_id,
        "status": status,
        "time": reference,
        "records": 0,
        "pages": 0,
        "pagination_complete": status == "complete",
        "errors": [],
        "note": note,
        "window": window,
        **extra,
    }


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def verify_jwt_claims(token_str, expected_client, expected_aud):
    try:
        encoded = token_str.split(".")[1]
        claims = json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))
        claims = normalize_sidecar_claims(claims)
    except (AttributeError, IndexError, ValueError, binascii.Error) as exc:
        raise EvidenceError("authentication_failed", "Identity provider returned an unreadable JWT.", "identity") from exc
    tenant = pick(claims, "tid")
    client = pick(claims, "appid") or pick(claims, "azp")
    aud = pick(claims, "aud")
    try:
        valid_tid = isinstance(tenant, str) and str(UUID(tenant)) == tenant.lower() and UUID(tenant).int != 0
    except ValueError:
        valid_tid = False
    expected_norm = expected_aud.rstrip("/").lower()
    aud_norm = aud.rstrip("/").lower() if isinstance(aud, str) else ""
    if expected_norm == ARM_ORIGIN.lower():
        aud_valid = aud_norm in ARM_TOKEN_AUDIENCES
    elif expected_norm == LOGS_ORIGIN.lower():
        aud_valid = aud_norm in LOGS_TOKEN_AUDIENCES
    else:
        aud_valid = aud_norm == expected_norm
    if not (valid_tid and isinstance(client, str) and client.lower() == expected_client.lower() and aud_valid):
        raise EvidenceError("identity_mismatch", "Token client identity or audience differs from the fixed configuration.", "identity")
    return claims


class Identity:
    def __init__(self, config):
        try:
            from azure.identity import ManagedIdentityCredential
        except ImportError as exc:
            raise EvidenceError("dependency_missing", "Live reads require azure-identity; no fallback credential is permitted.", "identity") from exc
        self.config = config
        self.credential = ManagedIdentityCredential(client_id=config["client_id"])
        self.deadline = time.monotonic() + MAX_COLLECTION_SECONDS
        self.request_count = 0
        self.cached_tokens = {}

    def guard_budget(self):
        if time.monotonic() >= self.deadline:
            raise EvidenceError("collection_deadline", "Collection time bound reached; remaining reads are marked incomplete.", "collection")
        if self.request_count >= MAX_HTTP_ATTEMPTS:
            raise EvidenceError("request_cap", "Collection HTTP request bound reached.", "collection")
        self.request_count += 1

    def token(self, origin):
        from azure.core.exceptions import ClientAuthenticationError, ServiceRequestError
        from azure.identity import CredentialUnavailableError

        cached = self.cached_tokens.get(origin)
        if cached is not None and cached[1] > time.time() + 60:
            return cached[0]
        self.guard_budget()
        scope = origin.rstrip("/") + "/.default"
        try:
            tok = self.credential.get_token(scope)
        except (ClientAuthenticationError, CredentialUnavailableError, ServiceRequestError) as exc:
            raise EvidenceError("authentication_failed", "The configured managed identity could not acquire a token.", "identity") from exc
        verify_jwt_claims(tok.token, self.config["client_id"], origin)
        self.cached_tokens[origin] = (tok.token, getattr(tok, "expires_on", time.time() + 300))
        return tok.token

    def arm_token(self):
        return self.token(ARM_ORIGIN)

    def logs_token(self):
        return self.token(LOGS_ORIGIN)

    def close(self):
        self.credential.close()


class HttpReader:
    def __init__(self, identity, origin=ARM_ORIGIN, token_kind="arm"):
        self.identity = identity
        self.origin = origin
        self.token_kind = token_kind
        self.context = ssl.create_default_context()
        if self.context.verify_mode != ssl.CERT_REQUIRED or not self.context.check_hostname:
            raise EvidenceError("unsafe_tls", "TLS certificate and hostname verification are mandatory.", "tls")
        self.opener = build_opener(NoRedirect(), HTTPSHandler(context=self.context))
        self.allowed = set()

    def allow(self, url, method="GET"):
        parsed = urlsplit(url)
        if (
            parsed.scheme != "https"
            or (parsed.scheme + "://" + parsed.netloc.lower()) != self.origin.lower()
            or parsed.fragment
            or parsed.username
            or parsed.password
            or "\\" in parsed.path
            or any(part in (".", "..") for part in unquote(parsed.path).split("/"))
        ):
            raise EvidenceError("unsafe_endpoint", "Read URL changed the fixed HTTPS origin or path safety rules.", "scope")
        if method not in ("GET", "POST"):
            raise EvidenceError("unsafe_method", "Only read-only GET and POST queries (ARG / Log Analytics) are permitted.", "scope")
        lowered = parsed.path.lower()
        if any(forbidden in lowered for forbidden in ("/write", "/delete", "/action", "/runcommand", "/listkeys", "/secrets")):
            raise EvidenceError("unsafe_endpoint", "Write actions, command execution, and secret reads are forbidden.", "scope")
        if method == "POST" and not (
            lowered == "/providers/microsoft.resourcegraph/resources"
            or re.fullmatch(r"/v1/workspaces/[0-9a-f-]{36}/query", lowered)
        ):
            raise EvidenceError("unsafe_method", "POST is restricted to Azure Resource Graph and Log Analytics query endpoints.", "scope")
        self.allowed.add((method, parsed.path))
        return url

    def _bearer(self):
        return self.identity.arm_token() if self.token_kind == "arm" else self.identity.logs_token()

    def request(self, method, url, source, body=None):
        parsed = urlsplit(url)
        if (
            (parsed.scheme + "://" + parsed.netloc.lower()) != self.origin.lower()
            or parsed.fragment
            or parsed.username
            or parsed.password
            or len(url) > 16384
            or (method, parsed.path) not in self.allowed
        ):
            raise EvidenceError("unsafe_endpoint", "Request was not registered in the scoped read allowlist.", source)
        payload = None if body is None else json.dumps(body, allow_nan=False).encode("utf-8")
        for attempt in range(3):
            bearer = self._bearer()
            self.identity.guard_budget()
            headers = {
                "Authorization": "Bearer " + bearer,
                "Accept": "application/json",
                "Content-Type": "application/json",
            }
            if self.token_kind == "logs":
                headers["Prefer"] = "wait=90"
            req = Request(url, data=payload, method=method, headers=headers)
            try:
                with self.opener.open(req, timeout=30) as response:
                    if response.status != 200:
                        raise EvidenceError("http_error", "Read returned HTTP " + str(response.status) + ".", source, response.status)
                    raw = response.read(HTTP_BYTES + 1)
                    if len(raw) > HTTP_BYTES:
                        raise EvidenceError("response_cap", "Response exceeded the byte safety cap.", source)
            except HTTPError as exc:
                if exc.code in (429, 500, 502, 503, 504) and attempt < 2:
                    retry = exc.headers.get("Retry-After", "") if exc.headers else ""
                    time.sleep(min(int(retry), 4) if re.fullmatch(r"[0-9]{1,4}", retry) else attempt + 1)
                    continue
                raise EvidenceError(
                    "access_denied" if exc.code in (401, 403) else "http_error",
                    "Read returned HTTP " + str(exc.code) + "; raw error bodies are excluded.",
                    source,
                    exc.code,
                ) from exc
            except (URLError, TimeoutError, ssl.SSLError, OSError) as exc:
                reason = getattr(exc, "reason", exc)
                code = "tls_failed" if isinstance(reason, ssl.SSLError) else "transport_failed"
                raise EvidenceError(code, "Transport or TLS error during read-only request.", source) from exc
            try:
                decoded = json.loads(raw)
                return obj(decoded, source)
            except (ValueError, UnicodeDecodeError) as exc:
                raise EvidenceError("invalid_json", "Source returned malformed JSON.", source) from exc
        raise EvidenceError("http_error", "Bounded HTTP retries exhausted.", source)


def next_arm_link(link, initial):
    if not isinstance(link, str) or not link or len(link) > 16384:
        raise EvidenceError("invalid_pagination", "Invalid ARM continuation link.", "pagination")
    current, first = urlsplit(link), urlsplit(initial)
    if (
        current.scheme != "https"
        or current.netloc.lower() != first.netloc.lower()
        or unquote(current.path) != unquote(first.path)
        or current.fragment
        or current.username
        or current.password
        or "\\" in current.path
    ):
        raise EvidenceError("invalid_pagination", "ARM continuation changed origin or path.", "pagination")
    try:
        pairs = parse_qsl(current.query, keep_blank_values=True, strict_parsing=True)
        original = dict(parse_qsl(first.query, keep_blank_values=True, strict_parsing=True))
    except ValueError as exc:
        raise EvidenceError("invalid_pagination", "Malformed continuation query parameters.", "pagination") from exc
    values = dict(pairs)
    paging = {"$skiptoken", "skiptoken", "$skipToken", "skipToken", "$skip", "$top"}
    if len(values) != len(pairs) or any(key not in original and key not in paging for key in values):
        raise EvidenceError("invalid_pagination", "ARM continuation added an unapproved query parameter.", "pagination")
    if any(values.get(key) != value for key, value in original.items() if key not in paging):
        raise EvidenceError("invalid_pagination", "ARM continuation modified api-version or scope filter.", "pagination")
    return link


def arg_alerts_query():
    return (
        "alertsmanagementresources "
        "| where type =~ 'microsoft.alertsmanagement/alerts' "
        "| extend ess = properties.essentials "
        "| project id, name, "
        "severity=tostring(ess.severity), "
        "alertState=tostring(ess.alertState), "
        "monitorCondition=tostring(ess.monitorCondition), "
        "signalType=tostring(ess.signalType), "
        "monitorService=tostring(ess.monitorService), "
        "targetResource=tostring(ess.targetResource), "
        "targetResourceName=tostring(ess.targetResourceName), "
        "targetResourceGroup=tostring(ess.targetResourceGroup), "
        "targetResourceType=tostring(ess.targetResourceType), "
        "startDateTime=tostring(ess.startDateTime), "
        "lastModifiedDateTime=tostring(ess.lastModifiedDateTime), "
        "resolvedDateTime=tostring(ess.monitorConditionResolvedDateTime), "
        "description=tostring(ess.description) "
        "| order by startDateTime desc, id asc"
    )


def arg_inventory_query():
    types_literal = ", ".join("'" + t + "'" for t in ESTATE_RESOURCE_TYPES)
    return (
        "resources "
        "| where type in~ (" + types_literal + ") "
        "| project id, name, type, resourceGroup, location, skuName=tostring(sku.name), tags, "
        "provisioningState=tostring(properties.provisioningState), "
        "arcStatus=tostring(properties.status), "
        "arcAgentVersion=tostring(properties.agentVersion), "
        "arcLastStatusChange=tostring(properties.lastStatusChange), "
        "osName=tostring(coalesce(properties.osName, properties.storageProfile.osDisk.osType)), "
        "osSku=tostring(properties.osSku), "
        "osVersion=tostring(properties.osVersion), "
        "vmSize=tostring(properties.hardwareProfile.vmSize), "
        "powerState=tostring(coalesce(properties.extended.instanceView.powerState.code, properties.powerState.code)), "
        "kubernetesVersion=tostring(properties.kubernetesVersion), "
        "runningState=tostring(coalesce(properties.runningStatus, properties.state)) "
        "| order by id asc"
    )


def arg_extensions_query():
    types_literal = ", ".join("'" + t + "'" for t in EXTENSION_RESOURCE_TYPES)
    return (
        "resources "
        "| where type in~ (" + types_literal + ") "
        "| project id, name, type, resourceGroup, location, "
        "publisher=tostring(properties.publisher), "
        "extType=tostring(properties.type), "
        "version=tostring(coalesce(properties.typeHandlerVersion, properties.instanceView.typeHandlerVersion)), "
        "provisioningState=tostring(properties.provisioningState), "
        "enableAutomaticUpgrade=properties.enableAutomaticUpgrade, "
        "autoUpgradeMinorVersion=properties.autoUpgradeMinorVersion "
        "| order by id asc"
    )


def read_arg_query(reader, subscription_id, query, source_id, reference, window, normalize_fn):
    url = ARM_ORIGIN + "/providers/Microsoft.ResourceGraph/resources?api-version=" + ARG_API_VERSION
    reader.allow(url, "POST")
    receipt = source_receipt(
        source_id,
        reference,
        window=window,
        page_cap=MAX_PAGES,
        row_cap=MAX_ROWS,
        pagination_complete=False,
        read_signature="POST " + url,
    )
    rows = []
    seen_ids = set()
    seen_tokens = set()
    skip_token = None
    try:
        for page_num in range(1, MAX_PAGES + 1):
            options = {"$top": 1000, "resultFormat": "objectArray"}
            if skip_token is not None:
                options["$skipToken"] = skip_token
            body = {
                "subscriptions": [subscription_id],
                "query": query,
                "options": options,
            }
            payload = reader.request("POST", url, source_id, body=body)
            receipt["pages"] = page_num
            data = array(payload.get("data", []), source_id)
            if len(rows) + len(data) > MAX_ROWS:
                raise EvidenceError("row_cap", "Resource Graph row safety cap reached.", source_id)
            for raw in data:
                normalized = normalize_fn(raw)
                if normalized is None:
                    continue
                row_id = str(normalized.get("id") or normalized.get("resource_id") or "").lower()
                if not row_id or row_id in seen_ids:
                    raise EvidenceError("invalid_pagination", "Resource Graph row ID is missing or duplicated.", source_id)
                seen_ids.add(row_id)
                rows.append(normalized)
            receipt["records"] = len(rows)
            next_token = payload.get("$skipToken")
            if not next_token:
                receipt["pagination_complete"] = True
                return rows, receipt
            next_token = text(next_token, source_id, 8192)
            if not next_token or next_token in seen_tokens:
                raise EvidenceError("pagination_loop", "Resource Graph repeated or emptied $skipToken.", source_id)
            seen_tokens.add(next_token)
            skip_token = next_token
        raise EvidenceError("page_cap", "Resource Graph page cap reached.", source_id)
    except EvidenceError as exc:
        receipt["status"] = "partial" if rows else "denied" if exc.http_status in (401, 403) else "error"
        receipt["records"] = len(rows)
        receipt["errors"].append(exc.public())
        return rows, receipt


def read_arm_pages(reader, url, source_id, reference, window, normalize_fn):
    reader.allow(url, "GET")
    receipt = source_receipt(
        source_id,
        reference,
        window=window,
        page_cap=MAX_PAGES,
        row_cap=MAX_ROWS,
        pagination_complete=False,
        read_signature="GET " + url,
    )
    rows = []
    seen_ids = set()
    seen_pages = set()
    current = url
    try:
        for page_num in range(1, MAX_PAGES + 1):
            if current in seen_pages:
                raise EvidenceError("pagination_loop", "ARM pagination repeated a page URL.", source_id)
            seen_pages.add(current)
            payload = reader.request("GET", current, source_id)
            receipt["pages"] = page_num
            page = array(payload.get("value", []), source_id)
            if len(rows) + len(page) > MAX_ROWS:
                raise EvidenceError("row_cap", "ARM list row safety cap reached.", source_id)
            for raw in page:
                normalized = normalize_fn(raw)
                if normalized is None:
                    continue
                row_id = str(normalized.get("id") or "").lower()
                if not row_id or row_id in seen_ids:
                    raise EvidenceError("invalid_pagination", "ARM row identity is missing or repeated.", source_id)
                seen_ids.add(row_id)
                rows.append(normalized)
            receipt["records"] = len(rows)
            continuation = payload.get("nextLink")
            if not continuation:
                receipt["pagination_complete"] = True
                return rows, receipt
            current = next_arm_link(continuation, url)
        raise EvidenceError("page_cap", "ARM list page cap reached.", source_id)
    except EvidenceError as exc:
        receipt["status"] = "partial" if rows else "denied" if exc.http_status in (401, 403) else "error"
        receipt["records"] = len(rows)
        receipt["errors"].append(exc.public())
        return rows, receipt


def map_alert_severity(sev_str):
    mapping = {
        "sev0": "critical",
        "sev1": "high",
        "sev2": "medium",
        "sev3": "low",
        "sev4": "low",
    }
    return mapping.get((sev_str or "").strip().lower(), "medium")


def normalize_alert_row(raw, subscription_id, window, reference):
    source_id = "arg_alerts_incidents"
    alert_id = text(raw.get("id"), source_id, 2048)
    name = text(raw.get("name"), source_id, 256) or (alert_id.split("/")[-1] if alert_id else None)
    if not alert_id or not name:
        raise EvidenceError("invalid_alert", "Alert row is missing id or name.", source_id)
    native_sev = text(raw.get("severity"), source_id, 32) or "Sev2"
    sev = map_alert_severity(native_sev)
    alert_state = text(raw.get("alertState"), source_id, 64) or "New"
    monitor_cond = text(raw.get("monitorCondition"), source_id, 64) or "Fired"
    signal_type = text(raw.get("signalType"), source_id, 64) or "Metric"
    monitor_service = text(raw.get("monitorService"), source_id, 128) or "Platform"
    target_res = text(raw.get("targetResource"), source_id, 2048)
    if target_res and target_res.lower().startswith("/subscriptions/"):
        target_res = arm_resource_id(target_res, subscription_id, source_id)
    rg, rtype, inferred_name = extract_rg_and_type(target_res or "")
    target_name = text(raw.get("targetResourceName"), source_id, 256) or inferred_name
    target_rg = text(raw.get("targetResourceGroup"), source_id, 128) or rg
    target_type = (text(raw.get("targetResourceType"), source_id, 180) or rtype).lower()
    start_str = text(raw.get("startDateTime"), source_id, 64)
    mod_str = text(raw.get("lastModifiedDateTime"), source_id, 64) or start_str or reference
    res_str = text(raw.get("resolvedDateTime"), source_id, 64)
    start_dt = parse_utc(start_str, source_id) if start_str else parse_utc(mod_str, source_id)
    mod_dt = parse_utc(mod_str, source_id)
    w_start = parse_utc(window["start_utc"], source_id)
    w_end = parse_utc(window["end_utc"], source_id)
    is_active = monitor_cond.lower() == "fired" or alert_state.lower() in ("new", "acknowledged")
    in_window = (w_start <= start_dt <= w_end) or (w_start <= mod_dt <= w_end) or is_active
    if not in_window:
        return None
    desc = text(raw.get("description"), source_id, 2048) or (
        "Native alert " + native_sev + " (" + monitor_cond + " / " + alert_state + ") on " + target_name + "."
    )
    short_hash = hashlib.sha256(alert_id.lower().encode("utf-8")).hexdigest()[:10]
    return {
        "id": "INC-ALR-" + short_hash,
        "native_id": alert_id,
        "record_kind": "incident",
        "category": "native_alert",
        "category_label": CATEGORY_LABELS["native_alert"],
        "severity": sev,
        "severity_label": SEVERITY_LABELS[sev],
        "native_severity": native_sev,
        "state": alert_state,
        "monitor_condition": monitor_cond,
        "title": "Alert " + native_sev + " (" + monitor_service + "): " + target_name,
        "signal_type": signal_type,
        "monitor_service": monitor_service,
        "resource_id": target_res or ("/subscriptions/" + subscription_id),
        "resource_name": target_name,
        "resource_group": target_rg,
        "resource_type": target_type,
        "start_time_utc": iso_utc(start_dt),
        "last_updated_utc": iso_utc(mod_dt),
        "resolved_time_utc": iso_utc(parse_utc(res_str, source_id)) if res_str else None,
        "observed_at_utc": reference,
        "source_id": source_id,
        "summary": desc,
        "learn_url": "https://learn.microsoft.com/azure/azure-monitor/alerts/alerts-overview",
    }


def normalize_service_health_row(raw, subscription_id, window, reference):
    source_id = "arm_service_health"
    event_id = text(raw.get("id"), source_id, 2048)
    tracking_id = text(raw.get("name"), source_id, 128)
    if not event_id or not tracking_id or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}", tracking_id):
        raise EvidenceError("invalid_service_health", "Service Health event is missing a valid tracking ID.", source_id)
    props = obj(raw.get("properties", {}), source_id)
    event_type = text(props.get("eventType"), source_id, 64)
    if event_type not in ("ServiceIssue", "PlannedMaintenance"):
        return None
    status = text(props.get("status"), source_id, 64) or "Active"
    title = text(props.get("title"), source_id, 512) or ("Event " + event_type + " (" + tracking_id + ")")
    level = (text(props.get("level"), source_id, 64) or "").lower()
    if event_type == "ServiceIssue":
        sev = "critical" if level == "critical" else "high"
    else:
        sev = "medium"
    start_str = text(props.get("impactStartTime"), source_id, 64) or text(props.get("lastUpdateTime"), source_id, 64) or reference
    update_str = text(props.get("lastUpdateTime"), source_id, 64) or start_str
    mitigation_str = text(props.get("impactMitigationTime"), source_id, 64)
    start_dt = parse_utc(start_str, source_id)
    update_dt = parse_utc(update_str, source_id)
    w_start = parse_utc(window["start_utc"], source_id)
    w_end = parse_utc(window["end_utc"], source_id)
    in_window = (w_start <= start_dt <= w_end) or (w_start <= update_dt <= w_end) or status.lower() == "active"
    if not in_window:
        return None
    impacts = props.get("impact") if isinstance(props.get("impact"), list) else []
    services = []
    regions = []
    for imp in impacts:
        if isinstance(imp, dict):
            svc = text(imp.get("impactedService"), source_id, 128)
            if svc and svc not in services:
                services.append(svc)
            reg_list = imp.get("impactedRegions") if isinstance(imp.get("impactedRegions"), list) else []
            for reg in reg_list:
                if isinstance(reg, dict):
                    rname = text(reg.get("impactedRegion"), source_id, 64)
                    if rname and rname not in regions:
                        regions.append(rname)
    service_label = ", ".join(services) if services else "Azure Platform"
    region_label = ", ".join(regions) if regions else "Global"
    summary_text = text(props.get("summary"), source_id, 2048) or (
        event_type + " " + tracking_id + " (" + status + ") affecting " + service_label + " [" + region_label + "]."
    )
    return {
        "id": "INC-SH-" + tracking_id,
        "native_id": event_id,
        "tracking_id": tracking_id,
        "record_kind": "incident",
        "category": "service_health",
        "category_label": CATEGORY_LABELS["service_health"],
        "severity": sev,
        "severity_label": SEVERITY_LABELS[sev],
        "native_severity": event_type,
        "state": status,
        "monitor_condition": status,
        "title": title,
        "signal_type": event_type,
        "monitor_service": service_label,
        "regions": regions,
        "resource_id": "/subscriptions/" + subscription_id,
        "resource_name": service_label,
        "resource_group": "subscription-scope",
        "resource_type": "microsoft.resourcehealth/events",
        "start_time_utc": iso_utc(start_dt),
        "last_updated_utc": iso_utc(update_dt),
        "resolved_time_utc": iso_utc(parse_utc(mitigation_str, source_id)) if mitigation_str else None,
        "observed_at_utc": reference,
        "source_id": source_id,
        "summary": summary_text,
        "learn_url": "https://learn.microsoft.com/azure/service-health/service-health-overview",
    }


def normalize_estate_resource(raw, subscription_id, reference):
    source_id = "arg_posture_anomalies"
    res_id = arm_resource_id(raw.get("id"), subscription_id, source_id)
    name = text(raw.get("name"), source_id, 256)
    rtype = (text(raw.get("type"), source_id, 180) or "").lower()
    rg = text(raw.get("resourceGroup"), source_id, 128)
    location = text(raw.get("location"), source_id, 64)
    if not name or not rtype or not rg or not location or rtype not in ESTATE_RESOURCE_TYPES:
        raise EvidenceError("invalid_inventory", "Inventory row is missing required identity fields.", source_id)
    hosting = "arc" if rtype in ("microsoft.hybridcompute/machines", "microsoft.kubernetes/connectedclusters") else "azure"
    prov_state = text(raw.get("provisioningState"), source_id, 64) or "Succeeded"
    arc_status = text(raw.get("arcStatus"), source_id, 64)
    arc_version = text(raw.get("arcAgentVersion"), source_id, 64)
    arc_last_change = text(raw.get("arcLastStatusChange"), source_id, 64)
    if arc_last_change:
        arc_last_change = iso_utc(parse_utc(arc_last_change, source_id))
    power_state = text(raw.get("powerState"), source_id, 64)
    running_state = text(raw.get("runningState"), source_id, 64)
    op_state = arc_status or power_state or running_state or prov_state
    return {
        "id": res_id,
        "resource_id": res_id,
        "name": name,
        "resource_name": name,
        "resource_group": rg,
        "resource_type": rtype,
        "location": location,
        "hosting": hosting,
        "sku": text(raw.get("skuName"), source_id, 64),
        "provisioning_state": prov_state,
        "operational_state": op_state,
        "arc_status": arc_status,
        "arc_agent_version": arc_version,
        "arc_last_status_change_utc": arc_last_change,
        "os_name": text(raw.get("osName"), source_id, 128),
        "os_sku": text(raw.get("osSku"), source_id, 128),
        "os_version": text(raw.get("osVersion"), source_id, 64),
        "vm_size": text(raw.get("vmSize"), source_id, 64),
        "power_state": power_state,
        "kubernetes_version": text(raw.get("kubernetesVersion"), source_id, 64),
        "tags": tags_map(raw.get("tags"), source_id),
        "observed_at_utc": reference,
        "source_id": source_id,
    }


def normalize_extension_row(raw, subscription_id, reference):
    source_id = "arg_guest_extensions"
    ext_id = arm_resource_id(raw.get("id"), subscription_id, source_id)
    parts = ext_id.split("/")
    if len(parts) < 11 or parts[9].lower() != "extensions":
        raise EvidenceError("invalid_extension", "Extension ID is not a valid child resource ID.", source_id)
    parent_id = "/".join(parts[:9])
    parent_name = parts[8]
    parent_type = (parts[6] + "/" + parts[7]).lower()
    ext_name = text(raw.get("name"), source_id, 256) or parts[-1]
    rg = text(raw.get("resourceGroup"), source_id, 128) or parts[4]
    location = text(raw.get("location"), source_id, 64) or ""
    publisher = text(raw.get("publisher"), source_id, 256) or "UnknownPublisher"
    ext_type = text(raw.get("extType"), source_id, 256) or ext_name
    version = text(raw.get("version"), source_id, 64) or "unknown"
    prov_state = text(raw.get("provisioningState"), source_id, 64) or "Unknown"
    return {
        "id": ext_id,
        "extension_id": ext_id,
        "name": ext_name,
        "extension_name": ext_name,
        "resource_id": parent_id,
        "resource_name": parent_name,
        "resource_group": rg,
        "resource_type": parent_type,
        "hosting": "arc" if "hybridcompute" in parent_type else "azure",
        "location": location,
        "publisher": publisher,
        "extension_type": ext_type,
        "version": version,
        "provisioning_state": prov_state,
        "enable_automatic_upgrade": boolean(raw.get("enableAutomaticUpgrade"), source_id),
        "auto_upgrade_minor_version": boolean(raw.get("autoUpgradeMinorVersion"), source_id),
        "observed_at_utc": reference,
        "source_id": source_id,
    }


def detect_posture_and_extension_anomalies(resources, extensions, reference):
    anomalies = []
    for ext in extensions:
        state = (ext.get("provisioning_state") or "").strip()
        if state.lower() in ("succeeded", "creating", "updating"):
            continue
        token_haystack = (ext["extension_name"] + " " + ext["extension_type"] + " " + ext["publisher"]).lower()
        is_crit_ext = any(tok in token_haystack for tok in CRITICAL_EXTENSION_TOKENS)
        sev = "high" if state.lower() == "failed" and is_crit_ext else "medium"
        short_hash = hashlib.sha256(ext["extension_id"].lower().encode("utf-8")).hexdigest()[:10]
        anomalies.append({
            "id": "ANM-EXT-" + short_hash,
            "record_kind": "anomaly",
            "category": "extension_failure",
            "category_label": CATEGORY_LABELS["extension_failure"],
            "anomaly_kind": "guest_extension_provisioning_failed",
            "severity": sev,
            "severity_label": SEVERITY_LABELS[sev],
            "title": "Extension " + ext["extension_name"] + " in state " + state + " (" + ext["resource_name"] + ")",
            "resource_id": ext["resource_id"],
            "resource_name": ext["resource_name"],
            "resource_group": ext["resource_group"],
            "resource_type": ext["resource_type"],
            "hosting": ext["hosting"],
            "metric_or_field": "properties.provisioningState (" + ext["publisher"] + "/" + ext["extension_type"] + ")",
            "observed_value": state,
            "baseline_or_expected": "Succeeded",
            "unit": "State",
            "sample_count": 1,
            "window_grain": "PointInTime",
            "observed_at_utc": reference,
            "source_id": "arg_posture_anomalies",
            "workspace_name": "",
            "extension_name": ext["extension_name"],
            "extension_version": ext["version"],
            "summary": (
                "Extension " + ext["extension_name"] + " (" + ext["publisher"] + "/" + ext["extension_type"]
                + ", version " + ext["version"] + ") on " + ext["resource_name"]
                + " reports provisioningState=" + state + "."
            ),
            "learn_url": "https://learn.microsoft.com/azure/azure-arc/servers/manage-vm-extensions",
        })

    for res in resources:
        rtype = res["resource_type"]
        rname = res["resource_name"]
        short_hash = hashlib.sha256(res["resource_id"].lower().encode("utf-8")).hexdigest()[:10]
        if rtype in ("microsoft.hybridcompute/machines", "microsoft.kubernetes/connectedclusters"):
            arc_st = (res.get("arc_status") or "").strip()
            if arc_st.lower() in ("expired", "disconnected", "error"):
                sev = "high" if arc_st.lower() in ("expired", "error") else "medium"
                changed = res.get("arc_last_status_change_utc") or "no_timestamp"
                ver = res.get("arc_agent_version") or "unknown"
                anomalies.append({
                    "id": "ANM-ARC-" + short_hash,
                    "record_kind": "anomaly",
                    "category": "connectivity_posture",
                    "category_label": CATEGORY_LABELS["connectivity_posture"],
                    "anomaly_kind": "arc_agent_" + arc_st.lower(),
                    "severity": sev,
                    "severity_label": SEVERITY_LABELS[sev],
                    "title": "Azure Arc agent in state " + arc_st + " (" + rname + ")",
                    "resource_id": res["resource_id"],
                    "resource_name": rname,
                    "resource_group": res["resource_group"],
                    "resource_type": rtype,
                    "hosting": "arc",
                    "metric_or_field": "properties.status (agentVersion=" + ver + ")",
                    "observed_value": arc_st,
                    "baseline_or_expected": "Connected",
                    "unit": "State",
                    "sample_count": 1,
                    "window_grain": "PointInTime",
                    "observed_at_utc": reference,
                    "source_id": "arg_posture_anomalies",
                    "workspace_name": "",
                    "summary": (
                        "Hybrid resource " + rname + " (" + (res.get("os_sku") or res.get("os_name") or rtype)
                        + ") reports status=" + arc_st + " (last change: " + changed + ", agent " + ver + ")."
                    ),
                    "learn_url": "https://learn.microsoft.com/azure/azure-arc/servers/troubleshoot-agent-onboard",
                })
        if rtype == "microsoft.containerservice/managedclusters":
            pstate = (res.get("power_state") or "").strip()
            prov = (res.get("provisioning_state") or "").strip()
            if prov.lower() == "failed" or (pstate and pstate.lower() not in ("running", "succeeded")):
                sev = "high" if prov.lower() == "failed" else "medium"
                observed_st = prov if prov.lower() == "failed" else pstate
                anomalies.append({
                    "id": "ANM-AKS-" + short_hash,
                    "record_kind": "anomaly",
                    "category": "connectivity_posture",
                    "category_label": CATEGORY_LABELS["connectivity_posture"],
                    "anomaly_kind": "aks_cluster_non_running",
                    "severity": sev,
                    "severity_label": SEVERITY_LABELS[sev],
                    "title": "AKS cluster " + rname + " in state " + observed_st,
                    "resource_id": res["resource_id"],
                    "resource_name": rname,
                    "resource_group": res["resource_group"],
                    "resource_type": rtype,
                    "hosting": "azure",
                    "metric_or_field": "properties.powerState.code / provisioningState",
                    "observed_value": observed_st,
                    "baseline_or_expected": "Running / Succeeded",
                    "unit": "State",
                    "sample_count": 1,
                    "window_grain": "PointInTime",
                    "observed_at_utc": reference,
                    "source_id": "arg_posture_anomalies",
                    "workspace_name": "",
                    "summary": (
                        "AKS cluster " + rname + " (k8s " + (res.get("kubernetes_version") or "n/a")
                        + ") is in state " + observed_st + " (provisioningState=" + prov + ")."
                    ),
                    "learn_url": "https://learn.microsoft.com/azure/aks/start-stop-cluster",
                })
        elif (res.get("provisioning_state") or "").lower() == "failed":
            anomalies.append({
                "id": "ANM-PRV-" + short_hash,
                "record_kind": "anomaly",
                "category": "connectivity_posture",
                "category_label": CATEGORY_LABELS["connectivity_posture"],
                "anomaly_kind": "resource_provisioning_failed",
                "severity": "high",
                "severity_label": SEVERITY_LABELS["high"],
                "title": "Resource " + rname + " with provisioningState=Failed",
                "resource_id": res["resource_id"],
                "resource_name": rname,
                "resource_group": res["resource_group"],
                "resource_type": rtype,
                "hosting": res["hosting"],
                "metric_or_field": "properties.provisioningState",
                "observed_value": "Failed",
                "baseline_or_expected": "Succeeded",
                "unit": "State",
                "sample_count": 1,
                "window_grain": "PointInTime",
                "observed_at_utc": reference,
                "source_id": "arg_posture_anomalies",
                "workspace_name": "",
                "summary": "Resource " + rname + " (" + rtype + ") reports provisioningState=Failed in Azure Resource Manager.",
                "learn_url": "https://learn.microsoft.com/azure/azure-resource-manager/troubleshooting/troubleshooting-deployment-errors",
            })
        elif rtype == "microsoft.compute/virtualmachines":
            pstate = (res.get("power_state") or "").strip().lower()
            if pstate in ("powerstate/deallocated", "powerstate/stopped", "deallocated", "stopped"):
                anomalies.append({
                    "id": "ANM-VM-" + short_hash,
                    "record_kind": "anomaly",
                    "category": "connectivity_posture",
                    "category_label": CATEGORY_LABELS["connectivity_posture"],
                    "anomaly_kind": "vm_stopped_or_deallocated",
                    "severity": "low",
                    "severity_label": SEVERITY_LABELS["low"],
                    "title": "Virtual machine " + rname + " in state " + (res.get("power_state") or "Stopped"),
                    "resource_id": res["resource_id"],
                    "resource_name": rname,
                    "resource_group": res["resource_group"],
                    "resource_type": rtype,
                    "hosting": "azure",
                    "metric_or_field": "instanceView.powerState.code",
                    "observed_value": res.get("power_state") or "Stopped",
                    "baseline_or_expected": "PowerState/running",
                    "unit": "State",
                    "sample_count": 1,
                    "window_grain": "PointInTime",
                    "observed_at_utc": reference,
                    "source_id": "arg_posture_anomalies",
                    "workspace_name": "",
                    "summary": (
                        "Virtual machine " + rname + " (" + (res.get("vm_size") or "VM")
                        + ") is stopped or deallocated (" + (res.get("power_state") or "Stopped") + ")."
                    ),
                    "learn_url": "https://learn.microsoft.com/azure/virtual-machines/states-billing",
                })
    return anomalies


def telemetry_kql_query(grain="1h"):
    return (
        "let cpu_im = InsightsMetrics "
        "| where Origin in ('vm.azm.ms', 'azuremonitor') and Namespace == 'Processor' and Name == 'UtilizationPercentage' "
        "| summarize bin_val=avg(Val), samples=count() by _ResourceId=tolower(_ResourceId), bin(TimeGenerated, " + grain + ") "
        "| extend metric_key='cpu_percent', unit='Percent'; "
        "let mem_im = InsightsMetrics "
        "| where Origin in ('vm.azm.ms', 'azuremonitor') and Namespace == 'Memory' and Name == 'AvailableMB' "
        "| summarize bin_val=min(Val), samples=count() by _ResourceId=tolower(_ResourceId), bin(TimeGenerated, " + grain + ") "
        "| extend metric_key='memory_available_mb', unit='MB'; "
        "let disk_im = InsightsMetrics "
        "| where Origin in ('vm.azm.ms', 'azuremonitor') and Namespace == 'LogicalDisk' and Name == 'FreeSpacePercentage' "
        "| where tostring(parse_json(Tags)['vm.azm.ms/mountId']) !startswith '/snap/' "
        "| summarize bin_val=min(Val), samples=count() by _ResourceId=tolower(_ResourceId), bin(TimeGenerated, " + grain + ") "
        "| extend metric_key='disk_free_percent', unit='Percent'; "
        "let perf_cpu = Perf "
        "| where ObjectName in ('Processor', 'Processor Information') and CounterName == '% Processor Time' and InstanceName in ('_Total', 'Total') "
        "| summarize bin_val=avg(CounterValue), samples=count() by _ResourceId=tolower(_ResourceId), bin(TimeGenerated, " + grain + ") "
        "| extend metric_key='cpu_percent', unit='Percent'; "
        "let combined = union isfuzzy=true cpu_im, mem_im, disk_im, perf_cpu "
        "| where isnotempty(_ResourceId) "
        "| summarize avg_val=round(avg(bin_val), 2), max_val=round(max(bin_val), 2), min_val=round(min(bin_val), 2), "
        "median_val=round(percentile(bin_val, 50), 2), p95_val=round(percentile(bin_val, 95), 2), "
        "high_bins=countif(metric_key == 'cpu_percent' and bin_val >= 85.0), "
        "low_mem_bins=countif(metric_key == 'memory_available_mb' and bin_val <= 512.0), "
        "low_disk_bins=countif(metric_key == 'disk_free_percent' and bin_val <= 15.0), "
        "bins_total=count(), sample_count=sum(samples), last_seen_utc=max(TimeGenerated) "
        "by _ResourceId, metric_key, unit; "
        "let hb = Heartbeat "
        "| where isnotempty(_ResourceId) "
        "| summarize avg_val=round(todouble(count()), 2), max_val=round(todouble(datetime_diff('minute', now(), max(TimeGenerated))), 2), "
        "min_val=0.0, median_val=0.0, p95_val=0.0, high_bins=0, low_mem_bins=0, low_disk_bins=0, "
        "bins_total=count(), sample_count=count(), last_seen_utc=max(TimeGenerated) "
        "by _ResourceId=tolower(_ResourceId) "
        "| extend metric_key='heartbeat_silence_minutes', unit='Minutes'; "
        "union isfuzzy=true combined, hb"
    )


def parse_log_table(payload, source_id):
    if payload.get("error") is not None:
        raise EvidenceError("partial_log_query", "Log Analytics returned a partial/error payload.", source_id)
    tables = payload.get("tables")
    if not isinstance(tables, list) or not tables or not isinstance(tables[0], dict):
        raise EvidenceError("invalid_log_result", "Log Analytics response is missing its primary table.", source_id)
    table = tables[0]
    columns = table.get("columns")
    rows = table.get("rows")
    if not isinstance(columns, list) or not isinstance(rows, list) or len(rows) > MAX_ROWS:
        raise EvidenceError("invalid_log_result", "Log Analytics table columns or rows are invalid.", source_id)
    col_names = [text(col.get("name"), source_id, 128) for col in columns if isinstance(col, dict)]
    if len(col_names) != len(columns) or len(set(col_names)) != len(col_names):
        raise EvidenceError("invalid_log_result", "Log Analytics table column names are invalid or duplicated.", source_id)
    parsed = []
    for row in rows:
        if not isinstance(row, list) or len(row) != len(col_names):
            raise EvidenceError("invalid_log_result", "Log Analytics row length does not match columns.", source_id)
        parsed.append(dict(zip(col_names, row)))
    return parsed


def evaluate_telemetry_row(raw, workspace_name, subscription_id, window, reference):
    source_id = "logs_telemetry_anomalies"
    raw_res_id = text(raw.get("_ResourceId"), source_id, 2048)
    if not raw_res_id or not raw_res_id.lower().startswith("/subscriptions/" + subscription_id.lower() + "/"):
        return None
    res_id = arm_resource_id(raw_res_id, subscription_id, source_id)
    rg, rtype, rname = extract_rg_and_type(res_id)
    hosting = "arc" if "hybridcompute" in rtype or "connectedclusters" in rtype else "azure"
    metric_key = text(raw.get("metric_key"), source_id, 64) or ""
    unit = text(raw.get("unit"), source_id, 32) or "Percent"
    avg_val = number(raw.get("avg_val"), source_id)
    max_val = number(raw.get("max_val"), source_id)
    min_val = number(raw.get("min_val"), source_id)
    median_val = number(raw.get("median_val"), source_id)
    p95_val = number(raw.get("p95_val"), source_id)
    high_bins = int(number(raw.get("high_bins"), source_id) or 0)
    low_mem_bins = int(number(raw.get("low_mem_bins"), source_id) or 0)
    low_disk_bins = int(number(raw.get("low_disk_bins"), source_id) or 0)
    bins_total = int(number(raw.get("bins_total"), source_id) or 0)
    sample_count = int(number(raw.get("sample_count"), source_id) or 0)
    last_seen = text(raw.get("last_seen_utc"), source_id, 64) or reference
    last_seen_iso = iso_utc(parse_utc(last_seen, source_id))
    short_hash = hashlib.sha256((res_id.lower() + "|" + metric_key + "|" + workspace_name).encode("utf-8")).hexdigest()[:10]

    if metric_key == "cpu_percent" and max_val is not None and median_val is not None:
        delta = round(max_val - median_val, 2)
        sustained = high_bins >= 3 or (avg_val is not None and avg_val >= 85.0)
        spike = max_val >= 95.0 or (max_val >= 85.0 and delta >= 25.0)
        if sustained or spike:
            sev = "critical" if (sustained and max_val >= 95.0) else "high" if sustained or max_val >= 95.0 else "medium"
            kind = "sustained_high_cpu" if sustained else "cpu_statistical_spike"
            return {
                "id": "ANM-TEL-" + short_hash,
                "record_kind": "anomaly",
                "category": "telemetry_anomaly",
                "category_label": CATEGORY_LABELS["telemetry_anomaly"],
                "anomaly_kind": kind,
                "severity": sev,
                "severity_label": SEVERITY_LABELS[sev],
                "title": "CPU anomaly on " + rname + " (peak " + grouped(max_val) + "%, median " + grouped(median_val) + "%)",
                "resource_id": res_id,
                "resource_name": rname,
                "resource_group": rg,
                "resource_type": rtype,
                "hosting": hosting,
                "metric_or_field": "Processor/UtilizationPercentage (" + window["grain"] + ")",
                "observed_value": max_val,
                "baseline_or_expected": median_val,
                "average_value": avg_val,
                "p95_value": p95_val,
                "high_bins": high_bins,
                "bins_total": bins_total,
                "unit": unit,
                "sample_count": sample_count,
                "window_grain": window["grain"],
                "observed_at_utc": last_seen_iso,
                "source_id": source_id,
                "workspace_name": workspace_name,
                "summary": (
                    "Telemetry in " + workspace_name + " for " + rname + ": CPU peak=" + grouped(max_val)
                    + "%, average=" + grouped(avg_val) + "%, median=" + grouped(median_val) + "% (Δ+" + grouped(delta)
                    + " pp, " + grouped(high_bins) + "/" + grouped(bins_total) + " intervals >=85%, "
                    + grouped(sample_count) + " samples)."
                ),
                "learn_url": "https://learn.microsoft.com/azure/azure-monitor/vm/vminsights-performance",
            }

    if metric_key == "memory_available_mb" and min_val is not None:
        if min_val <= 512.0 or low_mem_bins >= 2:
            sev = "high" if min_val <= 256.0 else "medium"
            return {
                "id": "ANM-TEL-" + short_hash,
                "record_kind": "anomaly",
                "category": "telemetry_anomaly",
                "category_label": CATEGORY_LABELS["telemetry_anomaly"],
                "anomaly_kind": "low_available_memory",
                "severity": sev,
                "severity_label": SEVERITY_LABELS[sev],
                "title": "Physical memory pressure on " + rname + " (minimum " + grouped(min_val) + " MB available)",
                "resource_id": res_id,
                "resource_name": rname,
                "resource_group": rg,
                "resource_type": rtype,
                "hosting": hosting,
                "metric_or_field": "Memory/AvailableMB (" + window["grain"] + ")",
                "observed_value": min_val,
                "baseline_or_expected": median_val if median_val is not None else 1024.0,
                "average_value": avg_val,
                "p95_value": p95_val,
                "high_bins": low_mem_bins,
                "bins_total": bins_total,
                "unit": "MB",
                "sample_count": sample_count,
                "window_grain": window["grain"],
                "observed_at_utc": last_seen_iso,
                "source_id": source_id,
                "workspace_name": workspace_name,
                "summary": (
                    "Available memory on " + rname + " fell to " + grouped(min_val) + " MB (median "
                    + grouped(median_val) + " MB, " + grouped(low_mem_bins) + "/" + grouped(bins_total)
                    + " intervals <=512 MB in " + workspace_name + ")."
                ),
                "learn_url": "https://learn.microsoft.com/azure/azure-monitor/vm/vminsights-performance",
            }

    if metric_key == "disk_free_percent" and min_val is not None:
        if min_val <= 15.0 or low_disk_bins >= 1:
            sev = "critical" if min_val <= 5.0 else "high" if min_val <= 10.0 else "medium"
            return {
                "id": "ANM-TEL-" + short_hash,
                "record_kind": "anomaly",
                "category": "telemetry_anomaly",
                "category_label": CATEGORY_LABELS["telemetry_anomaly"],
                "anomaly_kind": "low_disk_free_space",
                "severity": sev,
                "severity_label": SEVERITY_LABELS[sev],
                "title": "Low free disk space on " + rname + " (" + grouped(min_val) + "% free)",
                "resource_id": res_id,
                "resource_name": rname,
                "resource_group": rg,
                "resource_type": rtype,
                "hosting": hosting,
                "metric_or_field": "LogicalDisk/FreeSpacePercentage (" + window["grain"] + ")",
                "observed_value": min_val,
                "baseline_or_expected": 15.0,
                "average_value": avg_val,
                "p95_value": p95_val,
                "high_bins": low_disk_bins,
                "bins_total": bins_total,
                "unit": "Percent",
                "sample_count": sample_count,
                "window_grain": window["grain"],
                "observed_at_utc": last_seen_iso,
                "source_id": source_id,
                "workspace_name": workspace_name,
                "summary": (
                    "Logical volume on " + rname + " recorded " + grouped(min_val)
                    + "% free space (minimum threshold 15%, " + grouped(sample_count)
                    + " samples in " + workspace_name + ")."
                ),
                "learn_url": "https://learn.microsoft.com/azure/azure-monitor/vm/vminsights-performance",
            }

    if metric_key == "heartbeat_silence_minutes" and max_val is not None:
        if max_val >= 15.0:
            sev = "high" if max_val >= 60.0 else "medium"
            return {
                "id": "ANM-HB-" + short_hash,
                "record_kind": "anomaly",
                "category": "telemetry_anomaly",
                "category_label": CATEGORY_LABELS["telemetry_anomaly"],
                "anomaly_kind": "heartbeat_silence_gap",
                "severity": sev,
                "severity_label": SEVERITY_LABELS[sev],
                "title": "Heartbeat silence (" + grouped(int(round(max_val))) + " min without a heartbeat) on " + rname,
                "resource_id": res_id,
                "resource_name": rname,
                "resource_group": rg,
                "resource_type": rtype,
                "hosting": hosting,
                "metric_or_field": "Heartbeat/SilenceMinutes",
                "observed_value": round(max_val, 1),
                "baseline_or_expected": 5.0,
                "average_value": avg_val,
                "p95_value": None,
                "high_bins": 1,
                "bins_total": bins_total,
                "unit": "Minutes",
                "sample_count": sample_count,
                "window_grain": window["grain"],
                "observed_at_utc": last_seen_iso,
                "source_id": source_id,
                "workspace_name": workspace_name,
                "summary": (
                    "Resource " + rname + " has sent no heartbeat for " + grouped(round(max_val, 1))
                    + " minutes in the Heartbeat table of " + workspace_name
                    + " (last heartbeat: " + last_seen_iso + ")."
                ),
                "learn_url": "https://learn.microsoft.com/azure/azure-monitor/agents/azure-monitor-agent-troubleshoot",
            }
    return None


def collect_logs_telemetry(logs_reader, config, window, reference):
    workspaces = config["workspaces"]
    if not workspaces:
        receipt = source_receipt(
            "logs_telemetry_anomalies",
            reference,
            status="not_configured",
            window=window,
            note="No Log Analytics workspaces configured in APPROVED_LOG_WORKSPACES.",
            workspaces_queried=[],
        )
        return [], [], receipt

    grain_kql = "5m" if window["grain"] == "PT5M" else "1h"
    query = telemetry_kql_query(grain_kql)
    anomalies_by_key = {}
    telemetry_summaries = []
    ws_receipts = []
    total_records = 0
    errors = []

    for ws in workspaces:
        url = LOGS_ORIGIN + "/v1/workspaces/" + ws["customer_id"] + "/query"
        logs_reader.allow(url, "POST")
        body = {"query": query, "timespan": window["timespan_iso"]}
        try:
            payload = logs_reader.request("POST", url, "logs_telemetry_anomalies", body=body)
            rows = parse_log_table(payload, "logs_telemetry_anomalies")
            total_records += len(rows)
            ws_receipts.append({
                "workspace_name": ws["name"],
                "customer_id": ws["customer_id"],
                "status": "complete",
                "records": len(rows),
            })
            for row in rows:
                telemetry_summaries.append({
                    "workspace_name": ws["name"],
                    "resource_id": text(row.get("_ResourceId"), "logs_telemetry_anomalies", 2048),
                    "metric_key": text(row.get("metric_key"), "logs_telemetry_anomalies", 64),
                    "avg_val": number(row.get("avg_val"), "logs_telemetry_anomalies"),
                    "max_val": number(row.get("max_val"), "logs_telemetry_anomalies"),
                    "min_val": number(row.get("min_val"), "logs_telemetry_anomalies"),
                    "median_val": number(row.get("median_val"), "logs_telemetry_anomalies"),
                    "sample_count": int(number(row.get("sample_count"), "logs_telemetry_anomalies") or 0),
                })
                anom = evaluate_telemetry_row(row, ws["name"], config["subscription_id"], window, reference)
                if anom is not None:
                    dedup_key = (anom["resource_id"].lower(), anom["anomaly_kind"])
                    existing = anomalies_by_key.get(dedup_key)
                    if existing is None or SEVERITY_RANK[anom["severity"]] < SEVERITY_RANK[existing["severity"]]:
                        anomalies_by_key[dedup_key] = anom
        except EvidenceError as exc:
            err_doc = exc.public()
            err_doc["workspace_name"] = ws["name"]
            errors.append(err_doc)
            ws_receipts.append({
                "workspace_name": ws["name"],
                "customer_id": ws["customer_id"],
                "status": "denied" if exc.http_status in (401, 403) else "error",
                "records": 0,
                "error": err_doc,
            })

    ok_count = sum(w["status"] == "complete" for w in ws_receipts)
    if ok_count == len(ws_receipts):
        status = "complete"
    elif ok_count > 0:
        status = "partial"
    elif any(w["status"] == "denied" for w in ws_receipts):
        status = "denied"
    else:
        status = "error"

    receipt = source_receipt(
        "logs_telemetry_anomalies",
        reference,
        status=status,
        records=total_records,
        pages=len(ws_receipts),
        pagination_complete=status == "complete",
        errors=errors,
        window=window,
        workspaces_queried=ws_receipts,
        read_signature="POST https://api.loganalytics.io/v1/workspaces/{workspace_id}/query",
        note="Bounded KQL queries over InsightsMetrics, Perf, and Heartbeat in the approved Log Analytics workspaces.",
    )
    sorted_anomalies = sorted(
        anomalies_by_key.values(),
        key=lambda a: (SEVERITY_RANK[a["severity"]], a["resource_name"].lower(), a["id"]),
    )
    return sorted_anomalies, telemetry_summaries, receipt


def normalize_advisor_row(raw, subscription_id, reference):
    source_id = "arm_advisor_recommendations"
    rec_id = text(raw.get("id"), source_id, 2048)
    name = text(raw.get("name"), source_id, 256)
    if not rec_id or not name:
        raise EvidenceError("invalid_advisor", "Advisor recommendation is missing id or name.", source_id)
    props = obj(raw.get("properties", {}), source_id)
    adv_cat = text(props.get("category"), source_id, 64) or "HighAvailability"
    impact = text(props.get("impact"), source_id, 32) or "Medium"
    sev_map = {"high": "high", "medium": "medium", "low": "low"}
    sev = sev_map.get(impact.lower(), "medium")
    short_desc = obj(props.get("shortDescription", {}), source_id) if props.get("shortDescription") else {}
    problem = text(short_desc.get("problem"), source_id, 1024) or ("Azure Advisor recommendation (" + adv_cat + ")")
    solution = text(short_desc.get("solution"), source_id, 1024) or problem
    res_meta = obj(props.get("resourceMetadata", {}), source_id) if props.get("resourceMetadata") else {}
    target_id = text(res_meta.get("resourceId"), source_id, 2048) or rec_id.split("/providers/Microsoft.Advisor/")[0]
    if target_id and target_id.lower().startswith("/subscriptions/"):
        target_id = arm_resource_id(target_id, subscription_id, source_id)
    rg, rtype, rname = extract_rg_and_type(target_id)
    impacted_val = text(props.get("impactedValue"), source_id, 256) or rname
    updated = text(props.get("lastUpdated"), source_id, 64) or reference
    updated_iso = iso_utc(parse_utc(updated, source_id))
    short_hash = hashlib.sha256(rec_id.lower().encode("utf-8")).hexdigest()[:10]
    return {
        "id": "ADV-" + short_hash,
        "recommendation_id": name,
        "native_id": rec_id,
        "record_kind": "advisor",
        "category": "advisor_recommendation",
        "category_label": CATEGORY_LABELS["advisor_recommendation"],
        "advisor_category": adv_cat,
        "impact": impact,
        "severity": sev,
        "severity_label": SEVERITY_LABELS[sev],
        "problem": problem,
        "solution": solution,
        "title": problem,
        "resource_id": target_id,
        "resource_name": impacted_val,
        "resource_group": rg,
        "resource_type": rtype,
        "last_updated_utc": updated_iso,
        "observed_at_utc": reference,
        "source_id": source_id,
        "summary": "[" + adv_cat + " / Impact " + impact + "] " + problem + " — " + solution,
        "learn_url": "https://learn.microsoft.com/azure/advisor/advisor-overview",
    }


def synthesize_actions(incidents, anomalies, advisor_rows):
    actions = []

    for inc in incidents:
        is_active = (inc.get("monitor_condition") or "").lower() in ("fired", "active") or (inc.get("state") or "").lower() in ("new", "acknowledged", "active")
        if inc["category"] == "native_alert":
            horizon = "immediate_24h" if (is_active and inc["severity"] in ("critical", "high")) else "short_term_7d"
            effort = "low" if inc["severity"] in ("medium", "low") else "medium"
            owner = "Reliability engineering / Monitoring operations"
            rec_text = (
                "Check the firing condition (" + inc["monitor_condition"] + " / " + inc["state"]
                + ") in Azure Monitor for " + inc["resource_name"] + ", correlate it with recent changes, and document the operational closure."
            )
        else:
            horizon = "immediate_24h" if (is_active and inc["signal_type"] == "ServiceIssue") else "short_term_7d"
            effort = "low"
            owner = "Cloud governance / Platform incident management"
            rec_text = (
                "Review the official tracking ID " + (inc.get("tracking_id") or inc["id"])
                + " in Azure Service Health (" + inc["monitor_service"]
                + "), assess the maintenance window or mitigation, and confirm the actual impact on dependent workloads."
            )
        actions.append({
            "_sort_key": (
                0 if horizon == "immediate_24h" else 1,
                SEVERITY_RANK[inc["severity"]],
                inc["resource_name"].lower(),
                inc["id"],
            ),
            "category": inc["category"],
            "category_label": inc["category_label"],
            "severity": inc["severity"],
            "severity_label": inc["severity_label"],
            "horizon": horizon,
            "horizon_label": HORIZON_LABELS[horizon],
            "effort": effort,
            "effort_label": EFFORT_LABELS[effort],
            "title": "Address " + ("active alert " if is_active else "recorded incident ") + "on " + inc["resource_name"],
            "resource_id": inc["resource_id"],
            "resource_name": inc["resource_name"],
            "resource_group": inc["resource_group"],
            "resource_type": inc["resource_type"],
            "owner_scope": owner,
            "linked_evidence_ids": [inc["id"]],
            "source_ids": [inc["source_id"]],
            "evidence_summary": inc["summary"],
            "recommendation": rec_text,
            "learn_url": inc["learn_url"],
        })

    ext_by_resource = {}
    for anom in anomalies:
        if anom["category"] == "extension_failure":
            ext_by_resource.setdefault(anom["resource_id"], []).append(anom)
        elif anom["category"] == "connectivity_posture":
            is_arc = anom["hosting"] == "arc"
            is_aks = "managedclusters" in anom["resource_type"]
            horizon = "short_term_7d" if anom["severity"] in ("critical", "high", "medium") else "monthly_cycle"
            owner = (
                "Hybrid operations / Azure Arc administration"
                if is_arc
                else "Container platform / AKS operations"
                if is_aks
                else "Cloud infrastructure operations"
            )
            if is_arc:
                rec_text = (
                    "Inspect the himds service and the outbound TLS connectivity of the Azure Connected Machine agent on "
                    + anom["resource_name"] + " (current state: " + str(anom["observed_value"])
                    + "); renew the credentials or reconnect the machine if its identity certificate has expired."
                )
            elif is_aks:
                rec_text = (
                    "Confirm whether the stop/state (" + str(anom["observed_value"]) + ") of AKS cluster "
                    + anom["resource_name"] + " is a planned cost-saving measure or a control plane failure; "
                    + "avoid keeping clusters stopped for more than 12 months so that the Kubernetes version stays supported."
                )
            else:
                rec_text = (
                    "Review the operational state (" + str(anom["observed_value"]) + ") of "
                    + anom["resource_name"] + " and confirm that it matches the catalog of active services."
                )
            actions.append({
                "_sort_key": (
                    1 if horizon == "short_term_7d" else 2,
                    SEVERITY_RANK[anom["severity"]],
                    anom["resource_name"].lower(),
                    anom["id"],
                ),
                "category": anom["category"],
                "category_label": anom["category_label"],
                "severity": anom["severity"],
                "severity_label": anom["severity_label"],
                "horizon": horizon,
                "horizon_label": HORIZON_LABELS[horizon],
                "effort": "medium" if is_arc or is_aks else "low",
                "effort_label": EFFORT_LABELS["medium" if is_arc or is_aks else "low"],
                "title": "Review and fix the operational state of " + anom["resource_name"] + " (" + str(anom["observed_value"]) + ")",
                "resource_id": anom["resource_id"],
                "resource_name": anom["resource_name"],
                "resource_group": anom["resource_group"],
                "resource_type": anom["resource_type"],
                "owner_scope": owner,
                "linked_evidence_ids": [anom["id"]],
                "source_ids": [anom["source_id"]],
                "evidence_summary": anom["summary"],
                "recommendation": rec_text,
                "learn_url": anom["learn_url"],
            })
        elif anom["category"] == "telemetry_anomaly":
            horizon = "immediate_24h" if anom["severity"] == "critical" else "short_term_7d"
            actions.append({
                "_sort_key": (
                    0 if horizon == "immediate_24h" else 1,
                    SEVERITY_RANK[anom["severity"]],
                    anom["resource_name"].lower(),
                    anom["id"],
                ),
                "category": "telemetry_anomaly",
                "category_label": CATEGORY_LABELS["telemetry_anomaly"],
                "severity": anom["severity"],
                "severity_label": SEVERITY_LABELS[anom["severity"]],
                "horizon": horizon,
                "horizon_label": HORIZON_LABELS[horizon],
                "effort": "medium",
                "effort_label": EFFORT_LABELS["medium"],
                "title": "Investigate telemetry anomaly on " + anom["resource_name"] + " (" + anom["metric_or_field"] + ")",
                "resource_id": anom["resource_id"],
                "resource_name": anom["resource_name"],
                "resource_group": anom["resource_group"],
                "resource_type": anom["resource_type"],
                "owner_scope": "Capacity and observability engineering",
                "linked_evidence_ids": [anom["id"]],
                "source_ids": [anom["source_id"]],
                "evidence_summary": anom["summary"],
                "recommendation": (
                    "Analyze the processes and pressure intervals on " + anom["resource_name"]
                    + " reported in Log Analytics (" + (anom.get("workspace_name") or "workspace")
                    + "), check the SKU sizing and possible resource leaks, and tune the preventive alert thresholds."
                ),
                "learn_url": anom["learn_url"],
            })

    for res_id, ext_anoms in sorted(ext_by_resource.items()):
        highest = min(ext_anoms, key=lambda x: SEVERITY_RANK[x["severity"]])
        ext_names = ", ".join(sorted({x.get("extension_name") or x["title"] for x in ext_anoms}))
        ev_ids = [x["id"] for x in ext_anoms]
        horizon = "short_term_7d"
        actions.append({
            "_sort_key": (
                1,
                SEVERITY_RANK[highest["severity"]],
                highest["resource_name"].lower(),
                ev_ids[0],
            ),
            "category": "extension_failure",
            "category_label": CATEGORY_LABELS["extension_failure"],
            "severity": highest["severity"],
            "severity_label": SEVERITY_LABELS[highest["severity"]],
            "horizon": horizon,
            "horizon_label": HORIZON_LABELS[horizon],
            "effort": "medium",
            "effort_label": EFFORT_LABELS["medium"],
            "title": "Remediate failed extensions (" + ext_names + ") on " + highest["resource_name"],
            "resource_id": res_id,
            "resource_name": highest["resource_name"],
            "resource_group": highest["resource_group"],
            "resource_type": highest["resource_type"],
            "owner_scope": "Endpoint security and hybrid operations (MDE / Entra ID / AMA)",
            "linked_evidence_ids": ev_ids,
            "source_ids": ["arg_posture_anomalies"],
            "evidence_summary": "; ".join(x["summary"] for x in ext_anoms),
            "recommendation": (
                "First verify the base agent connectivity on " + highest["resource_name"]
                + ", review the local installation logs of " + ext_names
                + ", and reprovision the extensions in a controlled change window."
            ),
            "learn_url": "https://learn.microsoft.com/azure/azure-arc/servers/troubleshoot-vm-extensions",
        })

    for adv in advisor_rows:
        horizon = "short_term_7d" if adv["severity"] == "high" else "monthly_cycle"
        actions.append({
            "_sort_key": (
                1 if horizon == "short_term_7d" else 2,
                SEVERITY_RANK[adv["severity"]],
                adv["resource_name"].lower(),
                adv["id"],
            ),
            "category": "advisor_recommendation",
            "category_label": CATEGORY_LABELS["advisor_recommendation"],
            "severity": adv["severity"],
            "severity_label": SEVERITY_LABELS[adv["severity"]],
            "horizon": horizon,
            "horizon_label": HORIZON_LABELS[horizon],
            "effort": "medium" if adv["severity"] == "high" else "low",
            "effort_label": EFFORT_LABELS["medium" if adv["severity"] == "high" else "low"],
            "title": "Evaluate Azure Advisor recommendation (" + adv["advisor_category"] + ") on " + adv["resource_name"],
            "resource_id": adv["resource_id"],
            "resource_name": adv["resource_name"],
            "resource_group": adv["resource_group"],
            "resource_type": adv["resource_type"],
            "owner_scope": "Cloud architecture and WAF continuous improvement",
            "linked_evidence_ids": [adv["id"]],
            "source_ids": ["arm_advisor_recommendations"],
            "evidence_summary": adv["summary"],
            "recommendation": adv["solution"],
            "learn_url": adv["learn_url"],
        })

    actions.sort(key=lambda item: item["_sort_key"])
    finalized = []
    for idx, item in enumerate(actions, start=1):
        clean = {k: v for k, v in item.items() if k != "_sort_key"}
        short_hash = hashlib.sha256((clean["resource_id"].lower() + "|" + clean["title"] + "|" + str(idx)).encode("utf-8")).hexdigest()[:8]
        clean["id"] = f"ACT-{idx:03d}-{short_hash}"
        clean["priority_rank"] = idx
        finalized.append(clean)
    return finalized


def rollup_resources(estate_resources, extensions, incidents, anomalies, actions, telemetry_summaries):
    by_id = {}
    for res in estate_resources:
        rid = res["resource_id"].lower()
        by_id[rid] = {
            **res,
            "incident_count": 0,
            "anomaly_count": 0,
            "failed_extension_count": 0,
            "extensions_total": 0,
            "action_count": 0,
            "highest_severity": "low",
            "status": "healthy",
            "telemetry_metrics": {},
        }

    for ext in extensions:
        rid = ext["resource_id"].lower()
        if rid in by_id:
            by_id[rid]["extensions_total"] += 1
            if (ext.get("provisioning_state") or "").lower() not in ("succeeded", "creating", "updating"):
                by_id[rid]["failed_extension_count"] += 1

    for t_row in telemetry_summaries:
        rid = (t_row.get("resource_id") or "").lower()
        if rid in by_id and t_row.get("metric_key"):
            by_id[rid]["telemetry_metrics"][t_row["metric_key"]] = {
                "avg": t_row.get("avg_val"),
                "max": t_row.get("max_val"),
                "min": t_row.get("min_val"),
                "median": t_row.get("median_val"),
                "samples": t_row.get("sample_count"),
            }

    def bump_sev(entry, sev):
        if entry["status"] == "healthy" or SEVERITY_RANK[sev] < SEVERITY_RANK[entry["highest_severity"]]:
            entry["highest_severity"] = sev

    for inc in incidents:
        rid = inc["resource_id"].lower()
        if rid in by_id:
            by_id[rid]["incident_count"] += 1
            bump_sev(by_id[rid], inc["severity"])
            by_id[rid]["status"] = "attention"

    for anom in anomalies:
        rid = anom["resource_id"].lower()
        if rid in by_id:
            by_id[rid]["anomaly_count"] += 1
            bump_sev(by_id[rid], anom["severity"])
            if anom["severity"] in ("critical", "high", "medium"):
                by_id[rid]["status"] = "attention"
            elif by_id[rid]["status"] == "healthy":
                by_id[rid]["status"] = "review"

    for act in actions:
        rid = act["resource_id"].lower()
        if rid in by_id:
            by_id[rid]["action_count"] += 1

    rolled = []
    for entry in by_id.values():
        sev = entry["highest_severity"] if entry["status"] != "healthy" else "low"
        entry["severity"] = sev
        entry["severity_label"] = SEVERITY_LABELS[sev] if entry["status"] != "healthy" else "Normal"
        rolled.append(entry)

    rolled.sort(
        key=lambda r: (
            0 if r["status"] == "attention" else 1 if r["status"] == "review" else 2,
            SEVERITY_RANK[r["severity"]],
            r["resource_name"].lower(),
        )
    )
    return rolled


def collect_live(config, window, reference):
    identity = Identity(config)
    try:
        arm_reader = HttpReader(identity, ARM_ORIGIN, "arm")
        logs_reader = HttpReader(identity, LOGS_ORIGIN, "logs")
        sub_id = config["subscription_id"]

        alerts, alerts_receipt = read_arg_query(
            arm_reader,
            sub_id,
            arg_alerts_query(),
            "arg_alerts_incidents",
            reference,
            window,
            lambda raw: normalize_alert_row(raw, sub_id, window, reference),
        )
        alerts_receipt["note"] = "Azure Monitor native alerts (alertsmanagementresources) active or updated in the window."

        sh_query = urlencode({
            "api-version": RESOURCE_HEALTH_API_VERSION,
            "queryStartTime": window["start_utc"],
        })
        sh_url = ARM_ORIGIN + "/subscriptions/" + sub_id + "/providers/Microsoft.ResourceHealth/events?" + sh_query
        sh_events, sh_receipt = read_arm_pages(
            arm_reader,
            sh_url,
            "arm_service_health",
            reference,
            window,
            lambda raw: normalize_service_health_row(raw, sub_id, window, reference),
        )
        sh_receipt["note"] = "Official Azure Service Health communications from Microsoft.ResourceHealth (ServiceIssue and PlannedMaintenance)."

        estate_resources, posture_receipt = read_arg_query(
            arm_reader,
            sub_id,
            arg_inventory_query(),
            "arg_posture_anomalies",
            reference,
            window,
            lambda raw: normalize_estate_resource(raw, sub_id, reference),
        )
        posture_receipt["note"] = "Azure Resource Graph operational inventory (VMs, Azure Arc, AKS, Container Apps, Web Apps, Storage, Key Vault, DBs)."

        extensions, ext_receipt = read_arg_query(
            arm_reader,
            sub_id,
            arg_extensions_query(),
            "arg_guest_extensions",
            reference,
            window,
            lambda raw: normalize_extension_row(raw, sub_id, reference),
        )
        ext_receipt["note"] = "Extension metadata of VMs and Azure Arc servers (settings and protectedSettings are never read)."

        telemetry_anomalies, telemetry_summaries, logs_receipt = collect_logs_telemetry(
            logs_reader, config, window, reference
        )

        adv_url = (
            ARM_ORIGIN + "/subscriptions/" + sub_id
            + "/providers/Microsoft.Advisor/recommendations?api-version=" + ADVISOR_API_VERSION
        )
        advisor_rows, advisor_receipt = read_arm_pages(
            arm_reader,
            adv_url,
            "arm_advisor_recommendations",
            reference,
            window,
            lambda raw: normalize_advisor_row(raw, sub_id, reference),
        )
        advisor_receipt["note"] = "Cached Azure Advisor recommendations for the subscription (Microsoft.Advisor)."

        sources = [
            alerts_receipt,
            sh_receipt,
            posture_receipt,
            ext_receipt,
            logs_receipt,
            advisor_receipt,
        ]
        if all(s["status"] in ("denied", "error") for s in (alerts_receipt, posture_receipt)):
            first_err = (alerts_receipt["errors"] or posture_receipt["errors"] or [{}])[0]
            raise EvidenceError(
                first_err.get("code", "all_sources_failed"),
                "Primary Azure Resource Graph sources failed; no synthetic or empty report is generated.",
                first_err.get("source_id", "arg_posture_anomalies"),
                first_err.get("http_status"),
            )

        return {
            "subscription_id": sub_id,
            "alerts": alerts,
            "service_health": sh_events,
            "estate_resources": estate_resources,
            "extensions": extensions,
            "telemetry_anomalies": telemetry_anomalies,
            "telemetry_summaries": telemetry_summaries,
            "advisor": advisor_rows,
            "sources": sources,
        }
    finally:
        identity.close()


def finish_snapshot(raw, window, reference, provenance="LIVE"):
    if provenance not in ("LIVE", "SIMULATED"):
        raise EvidenceError("invalid_provenance", "provenance must be LIVE or SIMULATED.", "digest")
    validate_logo(CLIENT_LOGO_DATA_URI, CLIENT_LOGO_ALT)

    incidents = sorted(
        list(raw.get("alerts", [])) + list(raw.get("service_health", [])),
        key=lambda item: (SEVERITY_RANK[item["severity"]], item["start_time_utc"], item["id"]),
    )
    posture_anomalies = detect_posture_and_extension_anomalies(
        raw.get("estate_resources", []),
        raw.get("extensions", []),
        reference,
    )
    anomalies = sorted(
        posture_anomalies + list(raw.get("telemetry_anomalies", [])),
        key=lambda item: (SEVERITY_RANK[item["severity"]], item["category"], item["resource_name"].lower(), item["id"]),
    )
    advisor_rows = sorted(
        list(raw.get("advisor", [])),
        key=lambda item: (SEVERITY_RANK[item["severity"]], item["advisor_category"], item["id"]),
    )
    actions = synthesize_actions(incidents, anomalies, advisor_rows)
    resources = rollup_resources(
        raw.get("estate_resources", []),
        raw.get("extensions", []),
        incidents,
        anomalies,
        actions,
        raw.get("telemetry_summaries", []),
    )
    sources = list(raw.get("sources", []))

    native_alert_count = sum(i["category"] == "native_alert" for i in incidents)
    sh_count = sum(i["category"] == "service_health" for i in incidents)
    ext_fail_count = sum(a["category"] == "extension_failure" for a in anomalies)
    posture_count = sum(a["category"] == "connectivity_posture" for a in anomalies)
    tel_anom_count = sum(a["category"] == "telemetry_anomaly" for a in anomalies)
    imm_actions = sum(act["horizon"] == "immediate_24h" for act in actions)
    short_actions = sum(act["horizon"] == "short_term_7d" for act in actions)
    month_actions = sum(act["horizon"] == "monthly_cycle" for act in actions)
    attention_res = sum(r["status"] == "attention" for r in resources)
    degraded_sources = [s["id"] for s in sources if s["status"] not in ("complete", "not_configured")]

    counts = {
        "incidents_total": len(incidents),
        "native_alerts_total": native_alert_count,
        "service_health_total": sh_count,
        "anomalies_total": len(anomalies),
        "extension_failures_total": ext_fail_count,
        "connectivity_posture_total": posture_count,
        "telemetry_anomalies_total": tel_anom_count,
        "advisor_recommendations_total": len(advisor_rows),
        "actions_total": len(actions),
        "actions_immediate_24h": imm_actions,
        "actions_short_term_7d": short_actions,
        "actions_monthly_cycle": month_actions,
        "resources_total": len(resources),
        "resources_attention": attention_res,
        "extensions_evaluated": len(raw.get("extensions", [])),
        "severity_breakdown": {
            sev: sum(item["severity"] == sev for item in (incidents + anomalies))
            for sev in ("critical", "high", "medium", "low")
        },
    }

    executive_messages = [
        (
            "Evaluation window: " + window["label"] + " (" + window["start_utc"] + " → " + window["end_utc"]
            + ") over " + grouped(counts["resources_total"]) + " inventoried resources ("
            + grouped(counts["resources_attention"]) + " need operational attention)."
        ),
        (
            "Consolidated incidents: " + grouped(counts["incidents_total"]) + " recorded ("
            + grouped(native_alert_count) + " Azure Monitor native alerts and "
            + grouped(sh_count) + " official Azure Service Health communications)."
        ),
        (
            "Technical anomalies detected: " + grouped(counts["anomalies_total"]) + " in total ("
            + grouped(ext_fail_count) + " VM/Arc extension failures, "
            + grouped(posture_count) + " connectivity/control plane anomalies, and "
            + grouped(tel_anom_count) + " telemetry statistical/threshold anomalies)."
        ),
        (
            "Recommended action plan: " + grouped(counts["actions_total"]) + " prioritized actions ("
            + grouped(imm_actions) + " Immediate <24h, "
            + grouped(short_actions) + " Short term 1-7 days, and "
            + grouped(month_actions) + " Monthly cycle), correlated with "
            + grouped(counts["advisor_recommendations_total"]) + " Azure Advisor recommendations."
        ),
        (
            "Source coverage: " + grouped(len(sources) - len(degraded_sources)) + " of " + grouped(len(sources))
            + " evidence streams completed in read-only mode, without changing resources or agents."
        ),
    ]

    return {
        "schema_version": "operations-digest-v1",
        "provenance": provenance,
        "reference_utc": reference,
        "subscription_id": raw["subscription_id"],
        "client": {
            "name": CLIENT_NAME.strip(),
            "logo_data_uri": CLIENT_LOGO_DATA_URI,
            "logo_alt": CLIENT_LOGO_ALT.strip(),
        },
        "window": window,
        "counts": counts,
        "executive_messages": executive_messages,
        "incidents": incidents,
        "anomalies": anomalies,
        "actions": actions,
        "resources": resources,
        "extensions": raw.get("extensions", []),
        "advisor": advisor_rows,
        "sources": sources,
        "methodology": {
            "read_only": True,
            "official_sla_calculation": False,
            "scheduled_cadence_cron": "30 8 1 * *",
            "scheduled_default_period": "previous_month",
            "supported_periods": list(PERIODS),
            "evidence_streams": [
                "arg_alerts_incidents (microsoft.alertsmanagement/alerts)",
                "arm_service_health (Microsoft.ResourceHealth/events)",
                "arg_posture_anomalies & arg_guest_extensions (Azure Resource Graph)",
                "logs_telemetry_anomalies (Log Analytics InsightsMetrics, Perf, Heartbeat)",
                "arm_advisor_recommendations (Microsoft.Advisor/recommendations)",
            ],
            "limitations": [
                "Native alerts and Service Health events reflect the state and timestamps that Azure Monitor and Resource Health recorded at query time.",
                "Extension and Azure Arc agent state in Azure Resource Graph is a control plane observation; the tool doesn't read protected settings or run commands inside the guest operating system.",
                "Telemetry anomalies are calculated over the approved Log Analytics workspaces, for the resources that emit InsightsMetrics, Perf, or Heartbeat data in the window.",
                "Recommended actions are prioritized operational guidance for human review; the agent operates strictly in read-only mode.",
            ],
        },
    }


def collection_disclosure(snapshot):
    return {
        "reference_utc": snapshot["reference_utc"],
        "fresh_collection": True,
        "provenance": snapshot["provenance"],
        "subscription_id": snapshot["subscription_id"],
        "window": snapshot["window"],
        "source_status_counts": dict(Counter(s["status"] for s in snapshot["sources"])),
        "source_total": len(snapshot["sources"]),
        "source_details_view": "coverage",
        "paging_basis": "Local offset in this fresh collection; not a persistent cross-call cursor.",
    }


def summary_row(snapshot):
    return {
        "subscription_id": snapshot["subscription_id"],
        "reference_utc": snapshot["reference_utc"],
        "window": snapshot["window"],
        "counts": snapshot["counts"],
        "executive_messages": snapshot["executive_messages"],
        "official_sla_calculation": False,
    }


def snapshot_rows(snapshot, view):
    return {
        "summary": [summary_row(snapshot)],
        "incidents": snapshot["incidents"],
        "anomalies": snapshot["anomalies"],
        "actions": snapshot["actions"],
        "resources": snapshot["resources"],
        "advisor": snapshot["advisor"],
        "coverage": snapshot["sources"],
    }[view]


def query_snapshot(snapshot, params):
    view = params["view"]
    rows = snapshot_rows(snapshot, view)

    def matches(row):
        if params["category"] != "all" and row.get("category") != params["category"]:
            return False
        if params["severity"] != "all" and row.get("severity") != params["severity"]:
            return False
        if params["resource_name"]:
            target = params["resource_name"].lower()
            rname = str(row.get("resource_name") or row.get("name") or "").lower()
            if target != rname and target not in rname:
                return False
        return True

    matched = [row for row in rows if matches(row)]
    selected = matched[params["offset"]:params["offset"] + params["limit"]]
    partial = any(s["status"] not in ("complete", "not_configured") for s in snapshot["sources"])
    result = {
        "status": "partial" if partial else "ok",
        "operation": "query",
        "view": view,
        "collection": collection_disclosure(snapshot),
        "total_matched": len(matched),
        "offset": params["offset"],
        "requested_limit": params["limit"],
        "returned": len(selected),
        "has_more": params["offset"] + len(selected) < len(matched),
        "next_offset": params["offset"] + len(selected) if params["offset"] + len(selected) < len(matched) else None,
        "transport_capped": False,
        "rows": selected,
    }
    while selected and response_bytes(result) > TRANSPORT_BYTES:
        selected = selected[:-1]
        result.update(
            rows=selected,
            returned=len(selected),
            transport_capped=True,
            has_more=params["offset"] + len(selected) < len(matched),
            next_offset=params["offset"] + len(selected) if selected and params["offset"] + len(selected) < len(matched) else None,
        )
    if not selected and params["offset"] < len(matched):
        return ensure_response({
            "status": "error",
            "operation": "query",
            "view": view,
            "error": {
                "code": "query_row_too_large",
                "message": "A single row exceeds the 3500-byte JSON transport budget; inspect the full snapshot JSON.",
            },
            "total_matched": len(matched),
            "offset": params["offset"],
            "requested_limit": params["limit"],
            "returned": 0,
            "has_more": True,
            "next_offset": None,
            "transport_capped": True,
            "collection": collection_disclosure(snapshot),
        })
    return ensure_response(result)


def safe_json(snapshot):
    document = json.dumps(snapshot, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    escaped = (
        document.replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )
    if json.loads(escaped) != snapshot:
        raise EvidenceError("round_trip_failed", "Embedded JSON failed lossless round-trip verification.", "renderer")
    return escaped


def render_html(snapshot):
    if HTML_TEMPLATE.count("__REPORT_DATA_JSON__") != 1:
        raise EvidenceError("template_missing", "Build the HTML template into the standalone tool with build_tool.py.", "renderer")
    validate_logo(snapshot["client"]["logo_data_uri"], snapshot["client"].get("logo_alt", CLIENT_LOGO_ALT))
    return HTML_TEMPLATE.replace("__REPORT_DATA_JSON__", safe_json(snapshot))


def csv_cell(value):
    if value is None:
        return ""
    text_val = json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":")) if isinstance(value, (dict, list)) else str(value)
    return "'" + text_val if text_val.lstrip().startswith(("=", "+", "-", "@", "\t", "\r", "\n")) else text_val


def csv_document(rows, fields):
    stream = io.StringIO(newline="")
    writer = csv.writer(stream)
    writer.writerow(fields)
    for row in rows:
        writer.writerow([csv_cell(row.get(field)) for field in fields])
    return stream.getvalue()


def incidents_and_anomalies_csv_rows(snapshot):
    rows = []
    for inc in snapshot["incidents"]:
        rows.append({
            "record_kind": "incident",
            "id": inc["id"],
            "category": inc["category"],
            "severity": inc["severity"],
            "state_or_kind": inc["monitor_condition"] + " / " + inc["state"],
            "title": inc["title"],
            "resource_name": inc["resource_name"],
            "resource_group": inc["resource_group"],
            "resource_type": inc["resource_type"],
            "resource_id": inc["resource_id"],
            "metric_or_signal": inc["signal_type"],
            "observed_value": inc["native_severity"],
            "baseline_or_expected": "NoAlert",
            "unit": "Signal",
            "observed_at_utc": inc["last_updated_utc"],
            "source_id": inc["source_id"],
            "summary": inc["summary"],
            "learn_url": inc["learn_url"],
            "details_json": inc,
        })
    for anom in snapshot["anomalies"]:
        rows.append({
            "record_kind": "anomaly",
            "id": anom["id"],
            "category": anom["category"],
            "severity": anom["severity"],
            "state_or_kind": anom["anomaly_kind"],
            "title": anom["title"],
            "resource_name": anom["resource_name"],
            "resource_group": anom["resource_group"],
            "resource_type": anom["resource_type"],
            "resource_id": anom["resource_id"],
            "metric_or_signal": anom["metric_or_field"],
            "observed_value": anom["observed_value"],
            "baseline_or_expected": anom["baseline_or_expected"],
            "unit": anom["unit"],
            "observed_at_utc": anom["observed_at_utc"],
            "source_id": anom["source_id"],
            "summary": anom["summary"],
            "learn_url": anom["learn_url"],
            "details_json": anom,
        })
    return rows


def actions_csv_rows(snapshot):
    return [
        {
            **act,
            "details_json": act,
        }
        for act in snapshot["actions"]
    ]


def artifact_directory():
    try:
        cwd = Path.cwd()
        root = cwd.resolve(strict=True)
        linked = any(part.is_symlink() or getattr(part, "is_junction", lambda: False)() for part in (cwd, *cwd.parents))
    except (OSError, RuntimeError) as exc:
        raise EvidenceError("unsafe_artifact_root", "Runtime cwd must resolve to an existing directory.", "artifact_storage") from exc
    if root == Path(root.anchor) or not root.is_dir() or linked:
        raise EvidenceError("unsafe_artifact_root", "Filesystem roots, symlink/junction cwd ancestors, and non-directories are forbidden.", "artifact_storage")
    if OUTPUT_DIRECTORY != "operations-digest-reports":
        raise EvidenceError("unsafe_artifact_directory", "Only the fixed operations-digest-reports child directory is allowed.", "artifact_storage")
    directory = root / OUTPUT_DIRECTORY
    if directory.is_symlink() or getattr(directory, "is_junction", lambda: False)() or directory.resolve() != directory:
        raise EvidenceError("unsafe_artifact_directory", "Output directory is a symlink/junction or escapes cwd.", "artifact_storage")
    return root, directory


def sharing_fields(root, paths):
    result = {"sharing_mode": "local_files_only", "http_verified": False}
    match = re.fullmatch(
        r"/(?:root/sreagent|usr)/terminalRoot/tmp/ThreadFiles/([0-9a-fA-F-]{36})",
        root.as_posix(),
    )
    if match is None:
        return result
    try:
        if str(UUID(match[1])) != match[1].lower():
            return result
    except ValueError:
        return result
    suffixes = {
        "report_path": ".html",
        "snapshot_path": "-snapshot.json",
        "incidents_csv_path": "-incidents.csv",
        "actions_csv_path": "-actions.csv",
    }
    if set(paths) != set(suffixes):
        raise EvidenceError("unsafe_sharing_path", "Native delivery requires all four guarded report artifacts.", "artifact_storage")
    stem = paths["report_path"].name.removesuffix(".html")
    if not re.fullmatch(r"ops-digest-[0-9]{8}T[0-9]{6}Z-[0-9a-f]{12}", stem):
        raise EvidenceError("unsafe_sharing_path", "Native aliases require this tool's generated ops-digest run filenames.", "artifact_storage")
    expected = root / "operations-digest-reports"
    aliases = {}
    for key, path in paths.items():
        if path.parent != expected or path.name != stem + suffixes[key]:
            raise EvidenceError("unsafe_sharing_path", "Native aliases must reference the same run in operations-digest-reports.", "artifact_storage")
        aliases[key.removesuffix("_path") + "_url"] = (
            "/api/files/tmp/ThreadFiles/" + match[1] + "/operations-digest-reports/" + quote(path.name, safe="")
        )
    return {**result, "sharing_mode": "native_ui", **aliases}


def report_envelope(snapshot, paths, root):
    partial = any(s["status"] not in ("complete", "not_configured") for s in snapshot["sources"])
    result = {
        "status": "partial" if partial else "ok",
        "operation": "report",
        "artifact_status": "written",
        **sharing_fields(root, paths),
        "collection": collection_disclosure(snapshot),
        "counts": snapshot["counts"],
        **{key: str(path) for key, path in paths.items()},
    }
    return ensure_response(result)


def write_report(snapshot):
    root, directory = artifact_directory()
    ref_compact = snapshot["reference_utc"].replace(":", "").replace("-", "")
    prefix = "ops-digest-" + ref_compact + "-" + uuid4().hex[:12]
    paths = {
        key: directory / (prefix + suffix)
        for key, suffix in (
            ("report_path", ".html"),
            ("snapshot_path", "-snapshot.json"),
            ("incidents_csv_path", "-incidents.csv"),
            ("actions_csv_path", "-actions.csv"),
        )
    }
    response = report_envelope(snapshot, paths, root)
    snapshot_document = json.dumps(snapshot, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    if json.loads(snapshot_document) != snapshot:
        raise EvidenceError("round_trip_failed", "Full normalized snapshot JSON did not round-trip.", "artifact_storage")
    documents = {
        "report_path": render_html(snapshot),
        "snapshot_path": snapshot_document,
        "incidents_csv_path": csv_document(
            incidents_and_anomalies_csv_rows(snapshot),
            (
                "record_kind", "id", "category", "severity", "state_or_kind", "title",
                "resource_name", "resource_group", "resource_type", "resource_id",
                "metric_or_signal", "observed_value", "baseline_or_expected", "unit",
                "observed_at_utc", "source_id", "summary", "learn_url", "details_json",
            ),
        ),
        "actions_csv_path": csv_document(
            actions_csv_rows(snapshot),
            (
                "priority_rank", "id", "horizon_label", "severity", "category", "title",
                "resource_name", "resource_group", "resource_type", "resource_id",
                "owner_scope", "effort_label", "linked_evidence_ids", "source_ids",
                "evidence_summary", "recommendation", "learn_url", "details_json",
            ),
        ),
    }
    encoded = {key: value.encode("utf-8-sig" if key.endswith("csv_path") else "utf-8") for key, value in documents.items()}
    if any(len(value) > ARTIFACT_BYTES for value in encoded.values()):
        raise EvidenceError("artifact_size_exceeded", "Complete artifacts exceed 4800000 bytes; no files were written.", "artifact_storage")
    temporary, written = [], []
    try:
        directory.mkdir(exist_ok=True)
        if artifact_directory()[1] != directory or directory.resolve(strict=True) != directory or not directory.is_dir():
            raise EvidenceError("unsafe_artifact_directory", "Output directory changed after creation.", "artifact_storage")
        for key, data in encoded.items():
            if paths[key].exists() or paths[key].is_symlink():
                raise EvidenceError("artifact_collision", "A unique output path already exists; no overwrite.", "artifact_storage")
            fd, filename = tempfile.mkstemp(prefix=prefix + "-", suffix=".tmp", dir=directory)
            temp_path = Path(filename)
            temporary.append(temp_path)
            with os.fdopen(fd, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp_path, paths[key])
            temporary.remove(temp_path)
            written.append(paths[key])
        if any(path.read_bytes() != encoded[key] for key, path in paths.items()):
            raise EvidenceError("artifact_readback_failed", "Written artifact bytes differ from prepared content.", "artifact_storage")
        if json.loads(paths["snapshot_path"].read_text(encoding="utf-8")) != snapshot:
            raise EvidenceError("artifact_readback_failed", "Written snapshot JSON differs from normalized data.", "artifact_storage")
    except (OSError, EvidenceError) as exc:
        failures = []
        for path in temporary + written:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                failures.append(path.name)
        if failures:
            raise EvidenceError(
                "artifact_cleanup_failed",
                "Artifact write failed and cleanup failed for: " + ", ".join(failures),
                "artifact_storage",
            ) from exc
        if isinstance(exc, EvidenceError):
            raise
        raise EvidenceError("artifact_write_failed", "Could not atomically write all four artifacts.", "artifact_storage") from exc
    return response


def main(
    operation: str = "report",
    period: str = "previous_month",
    view: str = "summary",
    category: str = "all",
    severity: str = "all",
    resource_name: str = "",
    limit: int = 25,
    offset: int = 0,
) -> dict:
    """Generate the periodic Azure Operations Digest (incidents, anomalies, and prioritized actions) or query views."""
    try:
        reference = utc_now()
        params = validate_parameters(
            operation=operation,
            period=period,
            view=view,
            category=category,
            severity=severity,
            resource_name=resource_name,
            limit=limit,
            offset=offset,
            reference_utc=reference,
        )
        config = validate_config()
        if operation == "report" and HTML_TEMPLATE.count("__REPORT_DATA_JSON__") != 1:
            raise EvidenceError("template_missing", "Use the built standalone tool with embedded HTML_TEMPLATE.", "renderer")
        raw = collect_live(config, params["window"], reference)
        snapshot = finish_snapshot(raw, params["window"], reference, provenance="LIVE")
        return query_snapshot(snapshot, params) if operation == "query" else write_report(snapshot)
    except EvidenceError as exc:
        return ensure_response({
            "status": "error",
            "error": exc.public(),
            "artifact_status": "cleanup_failed" if exc.code == "artifact_cleanup_failed" else "not_written",
            "provenance": "LIVE",
        })
