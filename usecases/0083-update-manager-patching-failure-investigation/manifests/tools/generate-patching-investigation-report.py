"""Read-only Azure Update Manager patching cycle and failure investigation tool. Build assets with build_tool.py before SRE paste."""

import base64
import binascii
import csv
import hashlib
import io
import json
import math
import os
import re
import ssl
import tempfile
import time
import warnings
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, quote, unquote, urlsplit
from urllib.request import HTTPRedirectHandler, HTTPSHandler, Request, build_opener
from uuid import UUID, uuid4


SUBSCRIPTION_ID = "<YOUR_SUBSCRIPTION_ID>"
MANAGED_IDENTITY_CLIENT_ID = "<YOUR_MANAGED_IDENTITY_CLIENT_ID>"
CLIENT_NAME = "Customer"
# Here goes the customer's logo, privately configured as a validated PNG/JPEG
# data URI. Keep generic Git source empty. Use adjacent strings <10K per line.
CLIENT_LOGO_DATA_URI = ""
CLIENT_LOGO_ALT = "Authorized customer logo"
OUTPUT_DIRECTORY = "patching-investigation-reports"

ARM_ORIGIN = "https://management.azure.com"
ARM_TOKEN_AUDIENCES = (
    "https://management.azure.com",
    "https://management.core.windows.net",
)
ARG_API_VERSION = "2022-10-01"
ARG_PATH = "/providers/Microsoft.ResourceGraph/resources"
TRANSPORT_BYTES = 3500
ARTIFACT_BYTES = 4_800_000
HTTP_BYTES = 8_000_000
MAX_PAGES = 25
MAX_ROWS = 15000
MAX_COLLECTION_SECONDS = 240
MAX_HTTP_ATTEMPTS = 120
UTC = timezone.utc

OPERATIONS = ("report", "query")
PERIODS = ("last_30d", "last_14d", "last_7d", "last_24h")
PERIOD_HOURS = {
    "last_30d": 720,
    "last_14d": 336,
    "last_7d": 168,
    "last_24h": 24,
}
VIEWS = (
    "summary",
    "machines",
    "failures",
    "cycles",
    "patches",
    "extensions",
    "coverage",
    "actions",
)
HOSTINGS = ("all", "azure", "arc")
FAILURE_CATEGORIES = (
    "all",
    "maintenance_window_unresponsive",
    "arc_agent_expired_or_disconnected",
    "assessment_stuck_or_readiness_undetermined",
    "hotpatch_or_patch_extension_error",
    "pending_security_patches_unscheduled",
    "unassessed_no_update_manager_telemetry",
    "healthy",
)
CATEGORY_SEVERITY = {
    "maintenance_window_unresponsive": "critical",
    "arc_agent_expired_or_disconnected": "critical",
    "assessment_stuck_or_readiness_undetermined": "high",
    "hotpatch_or_patch_extension_error": "high",
    "pending_security_patches_unscheduled": "medium",
    "unassessed_no_update_manager_telemetry": "low",
    "healthy": "info",
}
CATEGORY_LABELS = {
    "maintenance_window_unresponsive": "Maintenance window unresponsive or run failed",
    "arc_agent_expired_or_disconnected": "Azure Arc agent expired or disconnected",
    "assessment_stuck_or_readiness_undetermined": "Assessment stuck in progress or patch support undetermined",
    "hotpatch_or_patch_extension_error": "Hotpatch or guest management/patch extension error",
    "pending_security_patches_unscheduled": "Pending security/rollup updates with no assigned window",
    "unassessed_no_update_manager_telemetry": "No assessment or installation telemetry in Update Manager",
    "healthy": "Patching verified, no active blockers",
}
SEVERITY_LABELS = {
    "critical": "Critical",
    "high": "High",
    "medium": "Medium",
    "low": "Low",
    "info": "Passed",
}
SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
SOURCE_IDS = (
    "arg_compute_machines",
    "arg_patch_assessments",
    "arg_software_patches_pending",
    "arg_patch_installations",
    "arg_software_patches_installed",
    "arg_maintenance_cycles",
    "arg_patch_extensions",
)

# BEGIN BUILD-TIME ASSETS
HTML_TEMPLATE = (
    '<!doctype html>\n<!--\nTHESIS: An offline Swiss Architectural Industrial Operations Ledger correlates '
    'Azure Update Manager post-patching cycles, assessments, software packages, and guest extensions into'
    ' per-machine root-cause diagnostics without logging into individual hosts.\nOWN-WORLD: Deep anthracit'
    'e slate (#141B24) chrome and verdict band, warm architectural stone (#F6F5F2) ground, 1px structural'
    ' rules (#D8DCE3), industrial vivid orange structural rule (#FF4E00), accessible burnt orange (#C2380'
    '0) and the shared Azure SRE Agent severity scale.\n-->\n<html lang="en">\n<head>\n<meta charset="utf-8">'
    '\n<meta name="viewport" content="width=device-width,initial-scale=1">\n<meta http-equiv="Content-Secur'
    'ity-Policy" content="default-src \'none\'; script-src \'unsafe-inline\'; style-src \'unsafe-inline\'; img-'
    'src data:; connect-src \'none\'; base-uri \'none\'; form-action \'none\'; object-src \'none\'">\n<meta name="'
    'color-scheme" content="light dark">\n<title>Post-patching report and failure investigation · Azure Up'
    'date Manager</title>\n<style>\n:root {\n  color-scheme: light;\n  --canvas: #F6F5F2;\n  --surface: #FFFFF'
    'F;\n  --subtle: #F9FAFB;\n  --wash: #EFECE6;\n  --hover: #FBFAF8;\n  --ink: #141B24;\n  --muted: #475569;'
    '\n  --line: #D8DCE3;\n  --line-soft: #E6E8EC;\n  --field-line: #64748B;\n  --accent: #FF4E00;\n  --accent'
    '-text: #C23800;\n  --accent-hover: #9A2C00;\n  --accent-wash: #FFF3ED;\n  --focus: #C23800;\n  --chrome:'
    ' #141B24;\n  --chrome-hover: #1E293B;\n  --chrome-line: #334155;\n  --chrome-muted: #B8C2CF;\n  --on-chr'
    'ome: #FFFFFF;\n  --hero-bg: #141B24;\n  --hero-panel: #1C2531;\n  --hero-line: rgba(255, 255, 255, 0.16'
    ');\n  --hero-muted: #C5CEDA;\n  --shadow: 0 1px 2px rgba(20, 27, 36, 0.06), 0 8px 24px rgba(20, 27, 36'
    ', 0.08);\n  --edge: rgba(20, 27, 36, 0.18);\n  --crit-ink: #B42318; --crit-bg: #FEE4E2; --crit-bar: #D'
    '92D20;\n  --high-ink: #B93815; --high-bg: #FFEAD5; --high-bar: #EF6820;\n  --med-ink: #93370D; --med-b'
    'g: #FEF0C7; --med-bar: #F79009;\n  --low-ink: #175CD3; --low-bg: #D1E9FF; --low-bar: #2E90FA;\n  --inf'
    'o-ink: #344054; --info-bg: #EAECF0;\n  --ok-ink: #067647; --ok-bg: #DCFAE6; --ok-bar: #17B26A;\n  --no'
    "te-ink: #7A2E0E; --note-bg: #FFFAEB; --note-line: #FEDF89;\n  --font-sans: 'Outfit', 'Segoe UI', syst"
    "em-ui, -apple-system, sans-serif;\n  --font-mono: 'Consolas', ui-monospace, monospace;\n  --bar-h: 61p"
    'x;\n}\n:root[data-theme="dark"] {\n  color-scheme: dark;\n  --canvas: #0F141B;\n  --surface: #161E29;\n  -'
    '-subtle: #1B2430;\n  --wash: #243040;\n  --hover: #1A2330;\n  --ink: #F1F5F9;\n  --muted: #CBD5E1;\n  --l'
    'ine: #334155;\n  --line-soft: #273244;\n  --field-line: #94A3B8;\n  --accent-text: #FF8552;\n  --accent-'
    'hover: #FFA07A;\n  --accent-wash: #2B1912;\n  --focus: #FF8552;\n  --chrome: #0B0F15;\n  --chrome-hover:'
    ' #1B2430;\n  --hero-bg: #0B0F15;\n  --hero-panel: #161E29;\n  --shadow: 0 1px 2px rgba(0, 0, 0, 0.45), '
    '0 8px 24px rgba(0, 0, 0, 0.35);\n  --edge: rgba(0, 0, 0, 0.6);\n  --crit-ink: #FDA29B; --crit-bg: rgba'
    '(217, 45, 32, 0.24);\n  --high-ink: #F9B98A; --high-bg: rgba(239, 104, 32, 0.22);\n  --med-ink: #FEC84'
    'B; --med-bg: rgba(247, 144, 9, 0.2);\n  --low-ink: #84CAFF; --low-bg: rgba(46, 144, 250, 0.22);\n  --i'
    'nfo-ink: #D0D5DD; --info-bg: rgba(152, 162, 179, 0.2);\n  --ok-ink: #75E0A7; --ok-bg: rgba(23, 178, 1'
    '06, 0.2);\n  --note-ink: #FEC84B; --note-bg: #2E2210; --note-line: #6B4E16;\n}\n* { box-sizing: border-'
    'box; }\nhtml { scroll-padding-top: calc(var(--bar-h) + 16px); scrollbar-color: var(--field-line) var('
    '--canvas); -webkit-text-size-adjust: 100%; }\nbody { margin: 0; background: var(--canvas); color: var'
    '(--ink); font: 15px/1.55 var(--font-sans); overflow-wrap: break-word; -webkit-font-smoothing: antial'
    'iased; }\n[hidden] { display: none !important; }\n::selection { background: #FFD5C2; color: #141B24; }'
    '\na { color: var(--accent-text); text-underline-offset: 3px; }\na:hover { color: var(--accent-hover); '
    '}\nbutton, input, select { font: inherit; color: inherit; }\ninput { caret-color: var(--accent-text); '
    '}\n:focus-visible { outline: 2px solid var(--focus); outline-offset: 2px; }\n.bar :focus-visible, .her'
    'o :focus-visible { outline-color: #FF8552; }\nh1, h2, h3 { margin: 0; }\np { margin: 0; }\ncode, .mono '
    '{ font-family: var(--font-mono); font-size: 12.5px; }\n.sr-only { position: absolute; width: 1px; hei'
    'ght: 1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }\n.skip { position: absolute; '
    'left: 16px; top: -100px; z-index: 50; padding: 10px 14px; background: var(--surface); color: var(--i'
    'nk); border: 2px solid var(--accent-text); border-radius: 6px; }\n.skip:focus { top: 12px; }\nsvg { wi'
    'dth: 16px; height: 16px; flex: none; fill: none; stroke: currentColor; stroke-width: 1.8; stroke-lin'
    'ecap: round; stroke-linejoin: round; }\n\n.btn { display: inline-flex; align-items: center; justify-co'
    'ntent: center; gap: 8px; min-height: 38px; padding: 0 14px; border: 1px solid var(--field-line); bor'
    'der-radius: 6px; background: var(--surface); color: var(--ink); font-size: 14px; font-weight: 600; l'
    'ine-height: 1.2; white-space: nowrap; cursor: pointer; transition: background-color 150ms ease, bord'
    'er-color 150ms ease, color 150ms ease; }\n.btn:hover { background: var(--wash); }\n.btn:active { trans'
    'form: translateY(1px); }\n.btn.sm { min-height: 32px; padding: 0 10px; font-size: 13px; }\n\n.bar { pos'
    'ition: sticky; top: 0; z-index: 30; background: var(--chrome); color: var(--on-chrome); border-botto'
    'm: 3px solid var(--accent); }\n.bar-in { max-width: 1440px; margin: 0 auto; min-height: 58px; padding'
    ': 8px 32px; display: flex; align-items: center; gap: 16px; }\n.brand { display: flex; align-items: ce'
    'nter; gap: 12px; min-width: 0; }\n.mark { width: 10px; height: 22px; background: var(--accent); flex:'
    ' none; }\n.wordmark { font-size: 16px; font-weight: 700; letter-spacing: -0.01em; white-space: nowrap'
    '; }\n.brand-sep { width: 1px; height: 22px; background: var(--chrome-line); flex: none; }\n.plaque { d'
    'isplay: flex; align-items: center; height: 36px; padding: 4px 10px; background: #FFFFFF; border-radi'
    'us: 4px; flex: none; }\n.plaque:empty { display: none; }\n.plaque img { display: block; max-height: 28'
    'px; max-width: 168px; width: auto; height: auto; }\n.client { min-width: 0; font-size: 15px; font-wei'
    'ght: 600; color: var(--on-chrome); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }'
    '\n.acts { margin-left: auto; display: flex; align-items: center; gap: 8px; }\n.ro { font-size: 12.5px;'
    ' font-weight: 600; color: var(--chrome-muted); border: 1px solid var(--chrome-line); border-radius: '
    '999px; padding: 4px 11px; white-space: nowrap; }\n.bar .btn { background: transparent; color: var(--o'
    'n-chrome); border-color: var(--chrome-line); }\n.bar .btn:hover { background: var(--chrome-hover); bo'
    'rder-color: var(--chrome-muted); }\n.bar .btn.primary { background: var(--accent); border-color: var('
    '--accent); color: #141B24; }\n.bar .btn.primary:hover { background: #FF6A2B; border-color: #FF6A2B; c'
    'olor: #141B24; }\n.menu-wrap { position: relative; }\n.menu { position: absolute; right: 0; top: calc('
    '100% + 8px); z-index: 40; min-width: 270px; padding: 6px; background: var(--surface); color: var(--i'
    'nk); border: 1px solid var(--line); border-radius: 8px; box-shadow: 0 12px 32px rgba(20, 27, 36, 0.2'
    '2); }\n.menu button { display: flex; flex-direction: column; align-items: flex-start; gap: 1px; width'
    ': 100%; padding: 8px 10px; border: 0; border-radius: 6px; background: none; text-align: left; cursor'
    ': pointer; font-size: 14px; font-weight: 600; }\n.menu button span { font-size: 12.5px; font-weight: '
    '400; color: var(--muted); }\n.menu button:hover { background: var(--wash); }\n\n.hero { background: var'
    '(--hero-bg); color: #FFFFFF; padding: 40px 32px 92px; }\n.hero-in { max-width: 1376px; margin: 0 auto'
    '; display: grid; grid-template-columns: minmax(0, 1fr) 340px; gap: 28px 48px; align-items: start; }\n'
    '.hero h1 { font-size: 42px; line-height: 1.12; font-weight: 700; letter-spacing: -0.02em; text-wrap:'
    ' balance; }\n.lead { margin-top: 14px; font-size: 18px; line-height: 1.5; max-width: 68ch; color: var'
    '(--hero-muted); }\n.lead b { color: #FFFFFF; font-weight: 600; }\n.meta { display: flex; flex-wrap: wr'
    'ap; gap: 8px; margin: 22px 0 0; padding: 0; list-style: none; }\n.meta li { font-size: 13px; padding:'
    ' 4px 11px; border: 1px solid var(--hero-line); border-radius: 999px; color: var(--hero-muted); max-w'
    'idth: 100%; overflow-wrap: anywhere; font-variant-numeric: tabular-nums; }\n.meta li.on { color: #FFF'
    'FFF; font-weight: 600; border-color: rgba(255, 255, 255, 0.4); }\n.verdict { background: var(--hero-p'
    'anel); border: 1px solid var(--hero-line); border-radius: 10px; padding: 20px 22px; }\n.v-k { font-si'
    'ze: 13px; font-weight: 600; color: var(--hero-muted); }\n.v-word { margin-top: 4px; font-size: 28px; '
    'line-height: 1.15; font-weight: 700; letter-spacing: -0.01em; }\n.v-crit .v-word { color: #FDA29B; }\n'
    '.v-high .v-word { color: #F9B98A; }\n.v-med .v-word { color: #FEC84B; }\n.v-ok .v-word { color: #75E0A'
    '7; }\n.v-detail { margin-top: 8px; font-size: 14px; color: var(--hero-muted); font-variant-numeric: t'
    'abular-nums; }\n.dist { grid-column: 1 / -1; }\n.dist-head { display: flex; justify-content: space-bet'
    'ween; gap: 16px; font-size: 13px; color: var(--hero-muted); margin-bottom: 8px; }\n.track { display: '
    'flex; height: 12px; border-radius: 999px; overflow: hidden; background: var(--hero-line); }\n.track i'
    ' { display: block; height: 100%; }\n.legend { display: flex; flex-wrap: wrap; gap: 6px 20px; margin: '
    '10px 0 0; padding: 0; list-style: none; font-size: 13.5px; color: var(--hero-muted); }\n.legend li { '
    'display: inline-flex; align-items: center; gap: 7px; }\n.legend b { color: #FFFFFF; font-variant-nume'
    'ric: tabular-nums; }\n.dot { width: 10px; height: 10px; border-radius: 3px; display: inline-block; fl'
    'ex: none; }\n.s-crit { background: var(--crit-bar); }\n.s-high { background: var(--high-bar); }\n.s-med'
    ' { background: var(--med-bar); }\n.s-low { background: var(--low-bar); }\n.s-ok { background: var(--ok'
    '-bar); }\n\n.kpi-wrap { max-width: 1440px; margin: -58px auto 0; padding: 0 32px; position: relative; '
    'z-index: 2; }\n.kpis { display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)); gap: 1px; bac'
    'kground: var(--line); border: 1px solid var(--line); border-radius: 10px; overflow: hidden; box-shad'
    'ow: var(--shadow); }\n.kpi { background: var(--surface); padding: 18px 20px 16px; min-width: 0; }\n.kv'
    ' { display: block; font-size: 36px; line-height: 1.05; font-weight: 700; letter-spacing: -0.02em; fo'
    'nt-variant-numeric: tabular-nums; }\n.kl { display: block; margin-top: 8px; font-size: 14px; font-wei'
    'ght: 600; line-height: 1.35; }\n.ks { display: block; margin-top: 4px; font-size: 13px; color: var(--'
    'muted); font-variant-numeric: tabular-nums; }\n.tone-crit { color: var(--crit-ink); }\n.tone-high { co'
    'lor: var(--high-ink); }\n.tone-med { color: var(--med-ink); }\n.tone-ok { color: var(--ok-ink); }\n.sim'
    ' { display: flex; gap: 10px; align-items: flex-start; margin-top: 14px; padding: 10px 14px; border: '
    '1px solid var(--note-line); background: var(--note-bg); color: var(--note-ink); border-radius: 8px; '
    'font-size: 14px; font-weight: 600; }\n.sim svg { margin-top: 2px; }\n\n.layout { max-width: 1440px; mar'
    'gin: 36px auto 0; padding: 0 32px 24px; display: grid; grid-template-columns: 200px minmax(0, 1fr); '
    'gap: 32px; align-items: start; }\n.toc { position: sticky; top: calc(var(--bar-h) + 24px); font-size:'
    ' 14px; }\n.toc-h { font-size: 12.5px; font-weight: 600; color: var(--muted); margin: 0 0 8px 10px; }\n'
    '.toc ol { list-style: none; margin: 0; padding: 0; display: grid; gap: 2px; }\n.toc a { display: flex'
    '; justify-content: space-between; align-items: baseline; gap: 8px; padding: 7px 10px; border-radius:'
    ' 6px; color: var(--ink); text-decoration: none; }\n.toc a:hover { background: var(--wash); color: var'
    '(--ink); }\n.toc a[aria-current="true"] { background: var(--surface); color: var(--accent-text); font'
    '-weight: 600; box-shadow: 0 1px 2px rgba(20, 27, 36, 0.08); }\n.toc-n { font-size: 12.5px; color: var'
    '(--muted); font-weight: 400; font-variant-numeric: tabular-nums; }\n.sections { min-width: 0; }\n.sect'
    'ion { margin-top: 44px; }\n.section:first-child { margin-top: 0; }\n.sh { margin-bottom: 14px; }\n.sh h'
    '2 { font-size: 22px; line-height: 1.25; font-weight: 700; letter-spacing: -0.01em; }\n.sh p { margin-'
    'top: 4px; font-size: 14px; color: var(--muted); max-width: 75ch; }\n.grid2 { display: grid; grid-temp'
    'late-columns: repeat(auto-fit, minmax(min(100%, 400px), 1fr)); gap: 16px; }\n.grid2 + .card, .card + '
    '.grid2 { margin-top: 16px; }\n.card { background: var(--surface); border: 1px solid var(--line); bord'
    'er-radius: 10px; padding: 20px 22px; box-shadow: var(--shadow); min-width: 0; }\n.card.flat { padding'
    ': 0; overflow: clip; }\n.card h3 { font-size: 16px; line-height: 1.3; font-weight: 700; }\n.card .sub '
    '{ margin: 3px 0 14px; font-size: 13.5px; color: var(--muted); max-width: 75ch; }\n\n.cats { display: g'
    'rid; gap: 2px; }\n.crow { display: grid; grid-template-columns: minmax(0, 1.7fr) minmax(70px, 1fr) 82'
    'px; gap: 12px; align-items: center; width: 100%; padding: 7px 8px; border: 0; border-radius: 6px; ba'
    'ckground: none; text-align: left; font-size: 14px; cursor: pointer; }\n.crow:hover { background: var('
    '--wash); }\n.crow:disabled { cursor: default; color: var(--muted); }\n.crow:disabled:hover { backgroun'
    'd: none; }\n.ct { height: 10px; border-radius: 999px; background: var(--line-soft); overflow: hidden;'
    ' }\n.ct i { display: block; height: 100%; border-radius: 999px; }\n.cv { text-align: right; font-size:'
    ' 13.5px; color: var(--muted); white-space: nowrap; font-variant-numeric: tabular-nums; }\n.cv b { col'
    'or: var(--ink); }\n.facts { list-style: none; margin: 0; padding: 0; }\n.facts li { padding: 9px 0; bo'
    'rder-top: 1px solid var(--line-soft); font-size: 14px; max-width: 80ch; font-variant-numeric: tabula'
    'r-nums; }\n.facts li:first-child { border-top: 0; padding-top: 0; }\n.facts code { overflow-wrap: brea'
    'k-word; }\n\n.plan { list-style: none; margin: 0; padding: 0; }\n.plan-item { display: grid; grid-templ'
    'ate-columns: 32px minmax(0, 1fr); gap: 16px; padding: 20px 22px; border-top: 1px solid var(--line-so'
    'ft); }\n.plan-item:first-child { border-top: 0; }\n.plan-n { width: 32px; height: 32px; border-radius:'
    ' 50%; background: var(--wash); display: grid; place-items: center; font-size: 14px; font-weight: 700'
    '; font-variant-numeric: tabular-nums; }\n.plan-body { display: grid; grid-template-columns: minmax(0,'
    ' 1.25fr) minmax(0, 1fr); gap: 8px 32px; align-items: start; }\n.plan-head { grid-column: 1 / -1; disp'
    'lay: flex; flex-wrap: wrap; align-items: center; gap: 6px 12px; }\n.plan-head h3 { font-size: 16px; l'
    'ine-height: 1.35; font-weight: 700; }\n.plan-c { font-size: 13px; color: var(--muted); white-space: n'
    'owrap; }\n.plan-act { font-size: 15px; max-width: 75ch; }\n.plan-dx { margin-top: 6px; font-size: 13.5'
    'px; color: var(--muted); max-width: 75ch; }\n.plan-ref { margin-top: 8px; font-size: 13px; color: var'
    '(--muted); }\n.plan-ref code { color: var(--muted); }\n.plan-ms { display: flex; flex-wrap: wrap; alig'
    'n-items: center; gap: 6px; }\n.lab { font-size: 12.5px; font-weight: 600; color: var(--muted); margin'
    '-right: 4px; }\n.mchip { padding: 2px 8px; border: 1px solid var(--line); border-radius: 6px; backgro'
    'und: var(--surface); color: var(--accent-text); font-family: var(--font-mono); font-size: 12.5px; cu'
    'rsor: pointer; }\n.mchip:hover { border-color: var(--accent-text); background: var(--accent-wash); }\n'
    '.empty-state { padding: 22px; color: var(--muted); }\n\n.tools { display: flex; flex-wrap: wrap; gap: '
    '12px; align-items: flex-end; padding: 16px 20px; background: var(--subtle); border-bottom: 1px solid'
    ' var(--line-soft); }\n.fld { display: grid; gap: 4px; flex: 1 1 170px; min-width: 0; font-size: 13px;'
    ' font-weight: 600; color: var(--muted); }\n.fld.grow { flex: 2 1 240px; }\n.fld select, .fld input { w'
    'idth: 100%; min-height: 38px; padding: 0 10px; border: 1px solid var(--field-line); border-radius: 6'
    'px; background: var(--surface); color: var(--ink); font-size: 14px; font-weight: 400; }\n.fld input::'
    'placeholder { color: var(--muted); opacity: 1; }\n.tool-btns { display: flex; flex-wrap: wrap; gap: 8'
    'px; }\n.status-row { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-betw'
    'een; gap: 8px 16px; min-height: 48px; padding: 8px 20px; font-size: 13.5px; color: var(--muted); fon'
    't-variant-numeric: tabular-nums; }\n.table-wrap { position: relative; overflow-x: auto; border-top: 1'
    'px solid var(--line-soft); background: linear-gradient(90deg, var(--surface) 30%, rgba(255, 255, 255'
    ', 0)) left / 40px 100% no-repeat local, linear-gradient(270deg, var(--surface) 30%, rgba(255, 255, 2'
    '55, 0)) right / 40px 100% no-repeat local, radial-gradient(farthest-side at 0 50%, var(--edge), rgba'
    '(0, 0, 0, 0)) left / 14px 100% no-repeat scroll, radial-gradient(farthest-side at 100% 50%, var(--ed'
    'ge), rgba(0, 0, 0, 0)) right / 14px 100% no-repeat scroll; }\n.card > .table-wrap:first-child { borde'
    'r-top: 0; }\ntable { width: 100%; border-collapse: collapse; font-size: 14px; font-variant-numeric: t'
    'abular-nums; }\nth { padding: 10px 14px; background: var(--subtle); border-bottom: 1px solid var(--li'
    'ne); color: var(--muted); font-size: 12.5px; font-weight: 600; text-align: left; vertical-align: bot'
    'tom; }\ntd { padding: 12px 14px; border-bottom: 1px solid var(--line-soft); vertical-align: top; over'
    'flow-wrap: break-word; }\ntbody tr:last-child td { border-bottom: 0; }\ntbody tr:hover td { background'
    ': var(--hover); }\nth.n, td.n { text-align: right; }\nth.nw, td.nw, .nw { white-space: nowrap; }\ntd.em'
    'pty { color: var(--muted); padding: 18px 20px; }\n.sm { display: block; margin-top: 2px; font-size: 1'
    '3px; color: var(--muted); }\n.sort { display: inline-flex; align-items: center; gap: 4px; padding: 0;'
    ' border: 0; background: none; color: inherit; font-size: inherit; font-weight: 600; cursor: pointer;'
    ' text-align: inherit; }\n.sort:hover { color: var(--accent-text); }\n.sort svg { width: 12px; height: '
    '12px; opacity: 0.35; }\nth[aria-sort] .sort { color: var(--ink); }\nth[aria-sort] .sort svg { opacity:'
    ' 1; }\nth[aria-sort="ascending"] .sort svg { transform: rotate(180deg); }\n.reg td { padding-top: 14px'
    '; }\n.nm { font-weight: 700; white-space: nowrap; }\n.dx { min-width: 300px; }\n.dx-t { display: block;'
    ' font-weight: 600; }\n.dx-h { display: block; margin-top: 2px; }\n.tgl { margin-top: 10px; }\n.big { di'
    'splay: block; font-size: 18px; line-height: 1.2; font-weight: 700; }\n.seg { white-space: nowrap; }\n.'
    'wide { min-width: 240px; }\n.reg tr.machine-row:has(+ tr.drawer-row:not([hidden])) td { border-bottom'
    ': 0; }\ntr.drawer-row td, tbody tr.drawer-row:hover td { background: var(--subtle); padding: 0 14px 1'
    '6px; border-bottom: 1px solid var(--line); }\n.drawer { position: sticky; left: 14px; max-width: calc'
    '(var(--wrap-w, 100%) - 28px); display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: '
    '12px 32px; padding: 14px 4px 0; border-top: 1px dashed var(--line); }\n.drawer p { max-width: 75ch; }'
    '\n.drawer * + .dk { margin-top: 12px; }\n.dk { margin: 0 0 4px; font-size: 12.5px; font-weight: 700; c'
    'olor: var(--accent-text); }\n.act { font-weight: 600; }\n.issues, .kbs { list-style: none; margin: 0; '
    'padding: 0; display: grid; gap: 6px; }\n.issues li { display: flex; gap: 8px; align-items: baseline; '
    '}\n.kbs li { font-size: 13.5px; }\ncode.ref { display: inline; color: var(--ink); overflow-wrap: break'
    '-word; }\n.arm { display: grid; gap: 1px; min-width: 150px; }\n.refs { display: grid; gap: 6px; margin'
    '-top: 2px; }\n.ref-arm { display: grid; gap: 1px; }\n.refs .arm { min-width: 0; }`n.refs .src { color:'
    ' var(--muted); }`ntd.host { min-width: 190px; }\n.arm .mono { overflow-wrap: break-word; color: var(-'
    '-ink); }\n.kind b { display: block; font-weight: 600; }\n.stack { display: flex; flex-direction: colum'
    'n; align-items: flex-start; gap: 6px; }\n.v-next { margin-top: 14px; padding-top: 12px; border-top: 1'
    'px solid var(--hero-line); font-size: 14px; color: var(--hero-muted); }\n.v-next a { color: #FF9F73; '
    'font-weight: 600; }\n.v-next a:hover { color: #FFC2A6; }\n.more-row { display: flex; justify-content: '
    'center; padding: 12px; border-top: 1px solid var(--line-soft); }\n\n.pill { display: inline-flex; alig'
    'n-items: center; gap: 6px; padding: 2px 10px; border-radius: 999px; background: var(--info-bg); colo'
    'r: var(--info-ink); font-size: 12.5px; font-weight: 600; line-height: 1.5; white-space: nowrap; }\n.p'
    'ill.sev::before { content: ""; width: 7px; height: 7px; border-radius: 50%; background: currentColor'
    '; flex: none; }\n.pill.crit { background: var(--crit-bg); color: var(--crit-ink); }\n.pill.high { back'
    'ground: var(--high-bg); color: var(--high-ink); }\n.pill.med { background: var(--med-bg); color: var('
    '--med-ink); }\n.pill.low { background: var(--low-bg); color: var(--low-ink); }\n.pill.ok { background:'
    ' var(--ok-bg); color: var(--ok-ink); }\n.pill.neutral { background: var(--info-bg); color: var(--info'
    '-ink); }\n.pill + .sm { margin-top: 6px; }\n\n.error-banner { max-width: 1376px; margin: 24px auto; pad'
    'ding: 18px; border: 1px solid var(--crit-ink); background: var(--crit-bg); color: var(--crit-ink); b'
    'order-radius: 8px; }\n.foot { max-width: 1440px; margin: 0 auto; padding: 24px 32px 40px; display: fl'
    'ex; flex-wrap: wrap; justify-content: space-between; gap: 8px 24px; font-size: 13px; color: var(--mu'
    'ted); }\n\n@media (prefers-reduced-motion: no-preference) {\n  html { scroll-behavior: smooth; }\n}\n@med'
    'ia (prefers-reduced-motion: reduce) {\n  * { transition: none !important; }\n}\n@media (max-width: 1180'
    'px) {\n  .kpis { grid-template-columns: repeat(3, minmax(0, 1fr)); }\n  .hero-in { grid-template-colum'
    'ns: minmax(0, 1fr) 300px; gap: 28px 40px; }\n  .hero h1 { font-size: 36px; }\n}\n@media (max-width: 110'
    '0px) {\n  html { scroll-padding-top: calc(var(--bar-h) + 64px); }\n  .hero-in { grid-template-columns:'
    ' minmax(0, 1fr); }\n  .layout { display: block; margin-top: 24px; }\n  .toc { top: var(--bar-h); z-ind'
    'ex: 20; margin: 0 -32px 28px; padding: 8px 32px; background: var(--canvas); border-bottom: 1px solid'
    ' var(--line); overflow-x: auto; }\n  .toc-h { display: none; }\n  .toc ol { display: flex; gap: 4px; w'
    'idth: max-content; }\n  .toc a { white-space: nowrap; padding: 6px 10px; }\n}\n@media (max-width: 900px'
    ') {\n  .ro { display: none; }\n  .plan-body { grid-template-columns: minmax(0, 1fr); }\n}\n@media (max-w'
    'idth: 640px) {\n  .bar-in { padding: 8px 14px; gap: 10px; }\n  .wordmark, .brand-sep { display: none; '
    '}\n  .bar .btn { padding: 0 10px; }\n  .bar .btn .lbl { position: absolute; width: 1px; height: 1px; o'
    'verflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }\n  .hero { padding: 28px 16px 80px; }\n  '
    '.hero h1 { font-size: 30px; }\n  .lead { font-size: 16px; }\n  .kpi-wrap { padding: 0 16px; }\n  .kpis '
    '{ grid-template-columns: repeat(2, minmax(0, 1fr)); }\n  .kpi { padding: 14px 12px 12px; }\n  .kv { fo'
    'nt-size: 28px; }\n  .ks { font-size: 12.5px; }\n  .layout { padding: 0 16px 16px; }\n  .toc { position:'
    ' static; margin: 0 -16px 24px; padding: 8px 16px; }\n  .card { padding: 16px; }\n  .tools { padding: 1'
    '4px 16px; }\n  .status-row { padding: 8px 16px; }\n  .plan-item { grid-template-columns: minmax(0, 1fr'
    '); gap: 8px; padding: 16px; }\n  .drawer { grid-template-columns: minmax(0, 1fr); }\n  .crow { grid-te'
    'mplate-columns: minmax(0, 1fr) 76px; }\n  .crow .ct { grid-column: 1 / -1; grid-row: 2; }\n  .plan-ref'
    ' code, .drawer code, .facts code, .issues span { overflow-wrap: anywhere; }\n  .plan-ref .seg, .drawe'
    'r .seg { white-space: normal; }\n  .foot { padding: 20px 16px 32px; }\n}\n@page { size: A4; margin: 12m'
    'm 11mm 14mm; @bottom-right { content: "Page " counter(page) " of " counter(pages); font: 9px/1.2 \'Ou'
    "tfit', 'Segoe UI', system-ui, sans-serif; color: #475569; } }\n@media print {\n  * { -webkit-print-col"
    'or-adjust: exact; print-color-adjust: exact; }\n  html { scroll-padding-top: 0; }\n  body { background'
    ': #FFFFFF; font-size: 12px; }\n  .skip, .acts, .toc, .tools, .more-row, .no-print, .tgl, .dlink, .arm'
    ' a { display: none !important; }\n  .bar { position: static; border-bottom-width: 2px; }\n  .bar-in { '
    'min-height: 0; padding: 4px 0 6px; }\n  .hero { padding: 18px 20px 62px; }\n  .hero-in { grid-template'
    '-columns: minmax(0, 1fr) 200px; gap: 12px 24px; }\n  .hero h1 { font-size: 24px; }\n  .lead { font-siz'
    'e: 12.5px; margin-top: 8px; }\n  .meta { margin-top: 10px; gap: 5px; }\n  .meta li { font-size: 10px; '
    'padding: 1px 7px; }\n  .verdict { padding: 12px 14px; }\n  .v-k, .v-detail { font-size: 11px; }\n  .v-w'
    'ord { font-size: 19px; }\n  .dist-head, .legend { font-size: 11px; }\n  .track { height: 9px; }\n  .kpi'
    '-wrap { margin-top: -46px; padding: 0 12px; }\n  .kpis { grid-template-columns: repeat(3, minmax(0, 1'
    'fr)); box-shadow: none; }\n  .kpi { padding: 9px 12px; }\n  .kv { font-size: 21px; }\n  .kl { font-size'
    ': 11.5px; margin-top: 3px; }\n  .ks { font-size: 10.5px; }\n  .sim { font-size: 11px; padding: 5px 10p'
    'x; margin-top: 8px; }\n  .layout { display: block; padding: 0; margin-top: 14px; }\n  .section { margi'
    'n-top: 18px; }\n  .sh { break-inside: avoid; break-after: avoid; margin-bottom: 8px; }\n  .sh h2 { fon'
    't-size: 16px; }\n  .sh p { font-size: 11px; }\n  .card { box-shadow: none; padding: 10px 12px; break-i'
    'nside: auto; }\n  .card.flat { padding: 0; overflow: visible; }\n  .card h3 { font-size: 12.5px; }\n  .'
    'card .sub { font-size: 10.5px; margin-bottom: 8px; }\n  .kpi, .plan-item, .verdict, tr, .crow, .facts'
    ' li { break-inside: avoid; }\n  .grid2 { grid-template-columns: 1fr 1fr; gap: 10px; }\n  .grid2 + .car'
    'd, .card + .grid2 { margin-top: 10px; }\n  .crow { font-size: 11.5px; padding: 3px 0; grid-template-c'
    'olumns: minmax(0, 1.6fr) minmax(40px, 1fr) 54px; gap: 8px; }\n  .cv { font-size: 10.5px; }\n  .facts l'
    'i { font-size: 11.5px; padding: 5px 0; }\n  thead { display: table-header-group; }\n  .table-wrap { ov'
    'erflow: visible; background: none; }\n  table { font-size: 11px; }\n  th { font-size: 10.5px; padding:'
    ' 5px 6px; }\n  td { padding: 6px; }\n  .reg td { padding-top: 7px; }\n  .sm, code, .mono, .plan-ref cod'
    'e { font-size: 10px; }\n  .pill { font-size: 10px; padding: 0 6px; gap: 4px; }\n  .pill.sev::before { '
    'width: 5px; height: 5px; }\n  th.nw, td.nw { white-space: normal; }\n  .dx, .wide, .arm, td.host { min'
    '-width: 0; }\n  .big { font-size: 12px; }\n  tr.drawer-row[hidden] { display: table-row !important; }\n'
    '  tr.drawer-row td { padding: 0 6px 8px; }\n  .drawer { position: static; max-width: none; gap: 4px 1'
    '6px; padding-top: 6px; }\n  .drawer p { font-size: 11px; }\n  .dk { font-size: 10.5px; margin-bottom: '
    '2px; }\n  .drawer * + .dk { margin-top: 6px; }\n  .status-row { min-height: 0; padding: 5px 12px; font'
    '-size: 10.5px; }\n  .plan-item { grid-template-columns: 22px minmax(0, 1fr); gap: 10px; padding: 9px '
    '12px; }\n  .plan-n { width: 22px; height: 22px; font-size: 10.5px; }\n  .plan-body { grid-template-col'
    'umns: minmax(0, 1.3fr) minmax(0, 1fr); gap: 4px 18px; }\n  .plan-head h3 { font-size: 12px; }\n  .plan'
    '-c, .plan-dx, .plan-ref, .lab { font-size: 11px; }\n  .plan-act { font-size: 12px; }\n  .mchip { font-'
    'size: 10px; padding: 0 5px; }\n  .kbs li { font-size: 11px; }\n  .v-next { font-size: 11px; margin-top'
    ': 8px; padding-top: 6px; }\n  .sort { display: contents; }\n  .sort svg { display: none; }\n  .foot { p'
    'adding: 10px 0 0; font-size: 10.5px; }\n  a { color: inherit; text-decoration: none; }\n}\n</style>\n</h'
    'ead>\n<body>\n<a class="skip" href="#main-ledger">Skip to main content</a>\n<header class="bar">\n  <div'
    ' class="bar-in">\n    <div class="brand">\n      <span class="mark" aria-hidden="true"></span>\n      <'
    'span class="wordmark">Azure SRE Agent</span>\n      <span class="brand-sep" aria-hidden="true"></span'
    '>\n      <span class="plaque" id="brand-plaque"></span>\n      <span class="client" id="client-name-la'
    'bel"></span>\n    </div>\n    <div class="acts">\n      <span class="ro">Read-only · Azure Resource Gra'
    'ph</span>\n      <button type="button" class="btn" id="theme-toggle"><svg viewBox="0 0 24 24" aria-hi'
    'dden="true"><circle cx="12" cy="12" r="8"/><path d="M12 4a8 8 0 0 1 0 16z" fill="currentColor"/></sv'
    'g><span class="lbl" id="theme-label">Dark mode</span></button>\n      <div class="menu-wrap">\n       '
    ' <button type="button" class="btn" id="export-menu-btn" aria-expanded="false" aria-controls="export-'
    'menu"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 4v11m0 0-4.5-4.5M12 15l4.5-4.5M5 19h1'
    '4"/></svg><span class="lbl">Export</span></button>\n        <div class="menu" id="export-menu" hidden'
    '>\n          <button type="button" id="export-json-btn">Export JSON<span>Full normalized snapshot</sp'
    'an></button>\n          <button type="button" id="export-machines-csv-btn">Export machine diagnostics'
    ' CSV<span>One row per machine with root cause and action</span></button>\n          <button type="but'
    'ton" id="export-patches-csv-btn">Export cycles and patches CSV<span>Maintenance cycles and softwareP'
    'atches</span></button>\n        </div>\n      </div>\n      <button type="button" class="btn primary" i'
    'd="print-btn"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 9V4h10v5M7 17H5a2 2 0 0 1-2-2v'
    '-4a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2v4a2 2 0 0 1-2 2h-2M7 14h10v6H7z"/></svg><span class="lbl">Print / '
    'PDF</span></button>\n    </div>\n  </div>\n</header>\n\n<main id="main-ledger" tabindex="-1">\n  <div id="'
    'error-box" class="error-banner" role="alert" hidden></div>\n  <div id="report-content" hidden>\n    <s'
    'ection class="hero" id="sec-cover" aria-labelledby="cover-title">\n      <div class="hero-in">\n      '
    '  <div>\n          <h1 id="cover-title">Post-patching report and automated failure investigation</h1>'
    '\n          <p class="lead" id="cover-subtitle"></p>\n          <ul class="meta" id="cover-tags" aria-'
    'label="Scope and provenance"></ul>\n        </div>\n        <div class="verdict" id="verdict-card">\n  '
    '        <p class="v-k">Patching cycle verdict</p>\n          <p class="v-word" id="verdict-label"></p'
    '>\n          <p class="v-detail" id="verdict-detail"></p>\n          <p class="v-next" id="verdict-nex'
    't" hidden></p>\n        </div>\n        <div class="dist">\n          <div class="dist-head"><span>Mach'
    'ines by diagnostic severity</span><span id="dist-total"></span></div>\n          <div class="track" i'
    'd="severity-track" role="img"></div>\n          <ul class="legend" id="severity-legend"></ul>\n       '
    ' </div>\n      </div>\n    </section>\n\n    <div class="kpi-wrap">\n      <div class="kpis" id="kpi-stri'
    'p"></div>\n      <p class="sim" id="sim-note" hidden><svg viewBox="0 0 24 24" aria-hidden="true"><pat'
    'h d="M12 3 2 20h20L12 3zM12 10v4M12 17h.01"/></svg><span id="sim-text"></span></p>\n    </div>\n\n    <'
    'div class="layout">\n      <nav class="toc" aria-labelledby="toc-h">\n        <p class="toc-h" id="toc'
    '-h">Report sections</p>\n        <ol>\n          <li><a href="#sec-cover">Cover and scope</a></li>\n   '
    '       <li><a href="#sec-executive">Executive summary</a></li>\n          <li><a href="#sec-actions">'
    'Action plan <span class="toc-n" id="toc-n-actions"></span></a></li>\n          <li><a href="#sec-inve'
    'stigation">Per-machine investigation <span class="toc-n" id="toc-n-machines"></span></a></li>\n      '
    '    <li><a href="#sec-cycles">Cycles and installations <span class="toc-n" id="toc-n-cycles"></span>'
    '</a></li>\n          <li><a href="#sec-patches">Patches <span class="toc-n" id="toc-n-patches"></span'
    '></a></li>\n          <li><a href="#sec-extensions">Extensions and Hotpatch <span class="toc-n" id="t'
    'oc-n-extensions"></span></a></li>\n          <li><a href="#sec-sources">Sources and method <span clas'
    's="toc-n" id="toc-n-sources"></span></a></li>\n        </ol>\n      </nav>\n\n      <div class="sections'
    '">\n        <section class="section" id="sec-executive" aria-labelledby="h-executive">\n          <div'
    ' class="sh">\n            <h2 id="h-executive">Patching cycle executive summary</h2>\n            <p>W'
    'here the blockers are and what the automated correlation confirmed, without signing in to any host.<'
    '/p>\n          </div>\n          <div class="grid2">\n            <div class="card">\n              <h3>'
    'Machines by diagnostic category</h3>\n              <p class="sub">Primary category of each machine. '
    'Select one to filter the investigation.</p>\n              <div class="cats" id="category-breakdown">'
    '</div>\n            </div>\n            <div class="card">\n              <h3>Verified operational conc'
    'lusions</h3>\n              <p class="sub">Read-only correlation across <code>Microsoft.Compute/<wbr>'
    'virtualMachines</code> and <code>Microsoft.HybridCompute/<wbr>machines</code>.</p>\n              <ul'
    ' class="facts" id="executive-messages"></ul>\n            </div>\n          </div>\n        </section>\n'
    '\n        <section class="section" id="sec-actions" aria-labelledby="h-actions">\n          <div class'
    '="sh">\n            <h2 id="h-actions">Prioritized action plan</h2>\n            <p>What to do first: '
    'one action per blocker type, ordered by severity and by the number of affected machines.</p>\n       '
    '   </div>\n          <ol class="plan card flat" id="actions-table"></ol>\n        </section>\n\n        '
    '<section class="section" id="sec-investigation" aria-labelledby="h-investigation">\n          <div cl'
    'ass="sh">\n            <h2 id="h-investigation">Automated per-machine root-cause investigation</h2>\n '
    '           <p>Why each machine was not patched: assessment state, pending patches, window cycles and'
    ' the exact evidence of the blocker.</p>\n          </div>\n          <div class="card flat">\n         '
    '   <div class="tools">\n              <label class="fld"><span>Failure category</span>\n              '
    '  <select id="filter-category">\n                  <option value="all">All categories</option>\n      '
    '            <option value="maintenance_window_unresponsive">Window unresponsive (ShutdownOrUnrespons'
    'ive / failure)</option>\n                  <option value="arc_agent_expired_or_disconnected">Azure Ar'
    'c agent expired or disconnected</option>\n                  <option value="assessment_stuck_or_readin'
    'ess_undetermined">Assessment in progress (InProgress) / UnableToDetermine</option>\n                 '
    ' <option value="hotpatch_or_patch_extension_error">Hotpatch or guest extension error</option>\n      '
    '            <option value="pending_security_patches_unscheduled">Pending security patches with no as'
    'signed window</option>\n                  <option value="unassessed_no_update_manager_telemetry">No U'
    'pdate Manager telemetry (stopped / not assessed)</option>\n                  <option value="healthy">'
    'No active blockers (healthy)</option>\n                </select>\n              </label>\n             '
    ' <label class="fld"><span>Hosting</span>\n                <select id="filter-hosting">\n              '
    '    <option value="all">All (Azure VM + Azure Arc)</option>\n                  <option value="azure">'
    'Azure VM (microsoft.compute)</option>\n                  <option value="arc">Azure Arc (microsoft.hyb'
    'ridcompute)</option>\n                </select>\n              </label>\n              <label class="fl'
    'd"><span>Severity</span>\n                <select id="filter-severity">\n                  <option val'
    'ue="all">All severities</option>\n                  <option value="critical">Critical</option>\n      '
    '            <option value="high">High</option>\n                  <option value="medium">Medium</opti'
    'on>\n                  <option value="low">Low</option>\n                  <option value="info">Passed'
    '</option>\n                </select>\n              </label>\n              <label class="fld grow"><sp'
    'an>Search</span>\n                <input type="search" id="filter-search" placeholder="Machine, KB, r'
    'esource group or error" autocomplete="off">\n              </label>\n            </div>\n            <d'
    'iv class="status-row">\n              <span id="machines-count-label" aria-live="polite"></span>\n    '
    '          <div class="tool-btns no-print">\n                <button type="button" class="btn sm" id="'
    'filter-reset-btn">Reset filters</button>\n                <button type="button" class="btn sm" id="ma'
    'chines-view-csv-btn"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 4v11m0 0-4.5-4.5M12 15'
    'l4.5-4.5M5 19h14"/></svg>CSV of this view</button>\n                <button type="button" class="btn '
    'sm" id="toggle-all-drawers-btn">Collapse all details</button>\n              </div>\n            </div'
    '>\n            <div class="table-wrap"><table id="machines-table" class="reg"></table></div>\n        '
    '  </div>\n        </section>\n\n        <section class="section" id="sec-cycles" aria-labelledby="h-cyc'
    'les">\n          <div class="sh">\n            <h2 id="h-cycles">Maintenance cycles and installation r'
    'uns</h2>\n            <p>Scheduled runs in <code>maintenanceresources</code> (UpdateSuccessfullyAppli'
    'ed versus ShutdownOrUnresponsive) compared with the results in <code>patchinstallationresources</cod'
    'e>.</p>\n          </div>\n          <div class="card flat">\n            <div class="tools">\n         '
    '     <label class="fld"><span>Cycle or run status</span>\n                <select id="cycle-status-fi'
    'lter">\n                  <option value="all">All statuses</option>\n                  <option value="'
    'ShutdownOrUnresponsive">ShutdownOrUnresponsive</option>\n                  <option value="UpdateSucce'
    'ssfullyApplied">UpdateSuccessfullyApplied</option>\n                  <option value="Succeeded">Succe'
    'eded (installation / configuration)</option>\n                  <option value="Assigned">Assigned (ac'
    'tive assignment)</option>\n                </select>\n              </label>\n              <label clas'
    's="fld grow"><span>Search</span>\n                <input type="search" id="cycle-search-filter" place'
    'holder="Machine, configuration or correlationId" autocomplete="off">\n              </label>\n        '
    '    </div>\n            <div class="status-row"><span id="cycles-count-label" aria-live="polite"></sp'
    'an></div>\n            <div class="table-wrap"><table id="cycles-table"></table></div>\n            <d'
    'iv class="more-row" id="cycles-more-row" hidden><button type="button" class="btn" id="cycles-more-bt'
    'n">Show 80 more records</button></div>\n          </div>\n        </section>\n\n        <section class="'
    'section" id="sec-patches" aria-labelledby="h-patches">\n          <div class="sh">\n            <h2 id'
    '="h-patches">Pending and installed software patches</h2>\n            <p>Pending packages from <code>'
    'patchassessmentresources/<wbr>softwarepatches</code> and records from <code>patchinstallationresourc'
    'es/<wbr>softwarepatches</code> (installed or not selected in the window).</p>\n          </div>\n     '
    '     <div class="card flat">\n            <div class="tools">\n              <label class="fld"><span>'
    'Patch source or state</span>\n                <select id="patch-state-filter">\n                  <opt'
    'ion value="all">All (pending + runs)</option>\n                  <option value="PendingAssessment">Pe'
    'nding installation (PendingAssessment)</option>\n                  <option value="Installed">Installe'
    'd in the window (Installed)</option>\n                  <option value="NotSelected">Not selected in t'
    'he window (NotSelected)</option>\n                </select>\n              </label>\n              <lab'
    'el class="fld"><span>Classification</span>\n                <select id="patch-class-filter">\n        '
    '          <option value="all">All classifications</option>\n                  <option value="Security'
    '">Security / Critical</option>\n                  <option value="UpdateRollUp">UpdateRollUp</option>\n'
    '                  <option value="Definition">Definition</option>\n                  <option value="Up'
    'dates">Updates</option>\n                  <option value="Other">Other</option>\n                </sel'
    'ect>\n              </label>\n              <label class="fld grow"><span>Search</span>\n              '
    '  <input type="search" id="patch-search-filter" placeholder="KB, package or machine" autocomplete="o'
    'ff">\n              </label>\n            </div>\n            <div class="status-row"><span id="patches'
    '-count-label" aria-live="polite"></span></div>\n            <div class="table-wrap"><table id="patche'
    's-table"></table></div>\n            <div class="more-row" id="patches-more-row" hidden><button type='
    '"button" class="btn" id="patches-more-btn">Show 80 more records</button></div>\n          </div>\n    '
    '    </section>\n\n        <section class="section" id="sec-extensions" aria-labelledby="h-extensions">'
    '\n          <div class="sh">\n            <h2 id="h-extensions">Guest extensions and Hotpatch readines'
    's</h2>\n            <p>Read-only inventory of <code>virtualMachines/<wbr>extensions</code> and <code>'
    'HybridCompute/<wbr>machines/<wbr>extensions</code>; <code>settings</code> and <code>protectedSetting'
    's</code> are never read.</p>\n          </div>\n          <div class="card flat"><div class="table-wra'
    'p"><table id="extensions-table"></table></div></div>\n        </section>\n\n        <section class="sec'
    'tion" id="sec-sources" aria-labelledby="h-sources">\n          <div class="sh">\n            <h2 id="h'
    '-sources">Azure Resource Graph receipts and method</h2>\n            <p>What was queried, with what r'
    'esult, and the limits of this report.</p>\n          </div>\n          <div class="card flat"><div cla'
    'ss="table-wrap"><table id="sources-table"></table></div></div>\n          <div class="grid2">\n       '
    '     <div class="card">\n              <h3>Method limits and safety guarantees</h3>\n              <ul'
    ' class="facts" id="methodology-list" style="margin-top:12px"></ul>\n            </div>\n            <d'
    'iv class="card">\n              <h3>Queried tables and cadence</h3>\n              <ul class="facts" i'
    'd="method-tables" style="margin-top:12px"></ul>\n            </div>\n          </div>\n        </sectio'
    'n>\n      </div>\n    </div>\n    <footer class="foot"><span id="foot-left"></span><span id="foot-right'
    '"></span></footer>\n  </div>\n</main>\n\n<script type="application/json" id="report-data">__REPORT_DATA_'
    'JSON__</script>\n<script>\n(function () {\n  "use strict";\n  var D = document;\n  function $(id) { retur'
    'n D.getElementById(id); }\n  function clear(node) {\n    while (node.firstChild) { node.removeChild(no'
    'de.firstChild); }\n  }\n  function el(tag, opts) {\n    var node = D.createElement(tag);\n    if (opts) '
    '{\n      if (opts.className) { node.className = opts.className; }\n      if (opts.text !== undefined &'
    '& opts.text !== null) { node.textContent = String(opts.text); }\n      if (opts.id) { node.id = opts.'
    'id; }\n      if (opts.title) { node.title = opts.title; }\n      if (opts.colspan) { node.setAttribute'
    '("colspan", String(opts.colspan)); }\n      if (opts.src) { node.setAttribute("src", opts.src); }\n   '
    '   if (opts.alt !== undefined) { node.setAttribute("alt", opts.alt); }\n      if (opts.attrs) { Objec'
    't.keys(opts.attrs).forEach(function (k) { node.setAttribute(k, opts.attrs[k]); }); }\n      if (opts.'
    'kids) {\n        opts.kids.forEach(function (kid) {\n          if (kid !== null && kid !== undefined &'
    '& kid !== "") { node.appendChild(typeof kid === "object" ? kid : D.createTextNode(String(kid))); }\n '
    '       });\n      }\n    }\n    return node;\n  }\n  var NF = window.Intl && Intl.NumberFormat ? new Intl'
    '.NumberFormat("en-US") : null;\n  function num(v) { var n = Number(v) || 0; return NF ? NF.format(n) '
    ': String(n); }\n  function pl(n, one, many) { return num(n) + " " + (Number(n) === 1 ? one : many); }'
    '\n  function utc(v) {\n    if (!v) { return "—"; }\n    var m = /^(\\d{4}-\\d{2}-\\d{2})T(\\d{2}:\\d{2})/.ex'
    'ec(String(v));\n    return m ? m[1] + " " + m[2] : String(v);\n  }\n  function day(v) { return v ? Stri'
    'ng(v).slice(0, 10) : "—"; }\n  function breakable(text) {\n    var frag = D.createDocumentFragment();\n'
    '    String(text === null || text === undefined ? "—" : text).split(/(\\s+|[\\/\\\\])/).forEach(function '
    '(part) {\n      if (!part) { return; }\n      if (part === "/" || part === "\\\\") {\n        frag.append'
    'Child(D.createTextNode(part));\n        frag.appendChild(D.createElement("wbr"));\n      } else if (/^'
    '\\s+$/.test(part)) {\n        frag.appendChild(D.createTextNode(" "));\n      } else {\n        frag.app'
    'endChild(el("span", { className: "seg", text: part }));\n      }\n    });\n    return frag;\n  }\n  funct'
    'ion code(text, cls) {\n    var c = el("code", { className: cls || "" });\n    c.appendChild(breakable('
    'text));\n    return c;\n  }\n  function csvCell(v) {\n    if (v === null || v === undefined) { return \'"'
    '"\'; }\n    var s = typeof v === "object" ? JSON.stringify(v) : String(v);\n    if (/^[=+\\-@\\t\\r\\n]/.te'
    'st(s.trimLeft ? s.trimLeft() : s)) { s = "\'" + s; }\n    return \'"\' + s.replace(/"/g, \'""\') + \'"\';\n  '
    '}\n  function downloadBlob(filename, mime, content) {\n    var blob = new Blob([content], { type: mime'
    ' });\n    var url = URL.createObjectURL(blob);\n    var a = D.createElement("a");\n    a.href = url;\n  '
    '  a.download = filename;\n    D.body.appendChild(a);\n    a.click();\n    D.body.removeChild(a);\n    se'
    'tTimeout(function () { URL.revokeObjectURL(url); }, 250);\n  }\n\n  var SEV = {\n    critical: ["crit", '
    '"Critical", "critical", "critical"],\n    high: ["high", "High", "high", "high"],\n    medium: ["med",'
    ' "Medium", "medium", "medium"],\n    low: ["low", "Low", "low", "low"],\n    info: ["ok", "Passed", "p'
    'assed", "passed"]\n  };\n  var SEV_RANK = { critical: 0, high: 1, medium: 2, low: 3, info: 4 };\n  var '
    'TONE = {\n    Failed: "crit", ShutdownOrUnresponsive: "crit", Expired: "crit", Disconnected: "crit", '
    'error: "crit", denied: "crit",\n    InProgress: "med", UnableToDetermine: "med", Warning: "med", Pend'
    'ingAssessment: "med", Pending: "med", partial: "med",\n    Succeeded: "ok", UpdateSuccessfullyApplied'
    ': "ok", Installed: "ok", Connected: "ok", Ready: "ok", Supported: "ok", complete: "ok", running: "ok'
    '"\n  };\n  var KIND = {\n    "microsoft.maintenance/applyupdates": "Window run",\n    "microsoft.mainten'
    'ance/configurationassignments": "Configuration assignment",\n    "microsoft.maintenance/maintenanceco'
    'nfigurations/applyupdates": "Configuration run",\n    "patchinstallationresources": "Patch installati'
    'on"\n  };\n  var SOURCE_STATUS = { complete: "Complete", partial: "Partial", denied: "Denied", error: '
    '"Error" };\n  var CATS = [\n    ["maintenance_window_unresponsive", "Maintenance window unresponsive ('
    'ShutdownOrUnresponsive)", "critical"],\n    ["arc_agent_expired_or_disconnected", "Azure Arc agent ex'
    'pired or disconnected", "critical"],\n    ["assessment_stuck_or_readiness_undetermined", "Assessment '
    'in progress (InProgress) / support UnableToDetermine", "high"],\n    ["hotpatch_or_patch_extension_er'
    'ror", "Hotpatch or guest extension error", "high"],\n    ["pending_security_patches_unscheduled", "Pe'
    'nding security/rollup patches with no assigned window", "medium"],\n    ["unassessed_no_update_manage'
    'r_telemetry", "No Update Manager assessment telemetry (stopped VMs)", "low"],\n    ["healthy", "Patch'
    'ing verified, no active blockers", "info"]\n  ];\n  function sevPill(sev, label) {\n    var s = SEV[sev'
    '] || ["neutral", sev || "—"];\n    return el("span", { className: "pill sev " + s[0], text: label || '
    's[1] });\n  }\n  function statusPill(value) {\n    var raw = value === null || value === undefined || v'
    'alue === "" ? "—" : String(value);\n    var shown = raw.replace(/^PowerState\\//, "");\n    return el("'
    'span", { className: "pill " + (TONE[shown] || "neutral"), text: shown, title: raw !== shown ? raw : '
    'null });\n  }\n  function classPill(c) {\n    var tone = c === "Critical" ? "crit" : c === "Security" ?'
    ' "high" : c === "UpdateRollUp" ? "med" : "neutral";\n    return el("span", { className: "pill " + ton'
    'e, text: c || "—" });\n  }\n  function yesNo(v) { return v === true ? "Yes" : v === false ? "No" : "—"'
    '; }\n  function portal(id) { return "https://portal.azure.com/#resource" + id; }\n  function portalLin'
    'k(id, text) {\n    return el("a", { className: "dlink", text: text || "Azure portal", attrs: { href: '
    'portal(id), target: "_blank", rel: "noopener noreferrer" } });\n  }\n  function armCell(id) {\n    var '
    's = String(id || "");\n    var m = /^\\/subscriptions\\/([^\\/]+)(?:\\/resourceGroups\\/([^\\/]+))?(?:\\/pro'
    'viders\\/(.+))?$/i.exec(s);\n    if (!m) { return code(s || "—", "ref"); }\n    var rest = m[3] ? m[3].'
    'split("/") : [];\n    var shown = rest.length > 3 ? rest.slice(2).filter(function (seg) { return seg.'
    'toLowerCase() !== "providers" && !/^microsoft\\.[a-z]+$/i.test(seg); }).join("/") : (rest.length ? re'
    'st[rest.length - 1] : (m[2] || m[1]));\n    var top = "/subscriptions/" + m[1] + (m[2] ? "/resourceGr'
    'oups/" + m[2] : "") + (rest.length >= 3 ? "/providers/" + rest.slice(0, 3).join("/") : "");\n    var '
    'box = el("span", { className: "arm" });\n    var main = el("span", { className: "mono", title: s });\n'
    '    main.appendChild(breakable(shown));\n    box.appendChild(main);\n    box.appendChild(el("span", { '
    'className: "sm", kids: [m[2] || ("subscription " + m[1]), el("span", { className: "dlink", kids: [" '
    '· ", portalLink(top, "Portal")] })] }));\n    return box;\n  }\n  function refBlock(text) {\n    var box'
    ' = el("span", { className: "refs" });\n    String(text || "—").split(" :: ").forEach(function (part) '
    '{\n      var m = /^([A-Za-z]+)=(\\/subscriptions\\/\\S+)$/.exec(part.trim()) || /^()(\\/subscriptions\\/\\S'
    '+)$/.exec(part.trim());\n      box.appendChild(m ? el("span", { className: "ref-arm", kids: [m[1] ? e'
    'l("span", { className: "sm", text: m[1] }) : null, armCell(m[2])] }) : code(part, /^arg_[a-z_]+$/.te'
    'st(part.trim()) ? "ref src" : "ref"));\n    });\n    return box;\n  }\n\n  var rawJson = $("report-data")'
    '.textContent;\n  var snap = null;\n  try {\n    snap = JSON.parse(rawJson);\n  } catch (err) {\n    var e'
    'rrBox = $("error-box");\n    errBox.hidden = false;\n    errBox.textContent = "Could not decode the em'
    'bedded JSON snapshot: " + String(err);\n    return;\n  }\n  var S = snap.summary || {};\n  var reduceMot'
    'ion = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;\n  function'
    ' goTo(id) {\n    var target = $(id);\n    if (target) { target.scrollIntoView({ behavior: reduceMotion'
    ' ? "auto" : "smooth", block: "start" }); }\n  }\n\n  var MACHINE_COLS = [\n    "machine_name", "hosting"'
    ', "resource_group", "location", "os_type", "os_name",\n    "power_or_arc_state", "assessment_status",'
    ' "vm_guest_patch_readiness",\n    "pending_security_or_critical", "pending_update_rollup", "pending_t'
    'otal",\n    "cycles_succeeded", "cycles_unresponsive", "install_runs_in_window",\n    "failure_categor'
    'y", "severity", "investigation_headline", "root_cause_evidence",\n    "log_or_source_reference", "rec'
    'ommended_human_action", "resource_id"\n  ];\n  function machinesCsv(list) {\n    var lines = [MACHINE_C'
    'OLS.join(",")];\n    list.forEach(function (m) {\n      var row = [\n        m.name, m.hosting, m.resou'
    'rce_group, m.location, m.os_type, m.os_name,\n        m.power_or_arc_state, m.assessment_status, m.vm'
    '_guest_patch_readiness,\n        m.pending_counts ? m.pending_counts.security_or_critical : 0,\n      '
    '  m.pending_counts ? m.pending_counts.update_rollup : 0,\n        m.pending_counts ? m.pending_counts'
    '.total : 0,\n        m.maintenance_cycles_summary ? m.maintenance_cycles_summary.succeeded : 0,\n     '
    '   m.maintenance_cycles_summary ? m.maintenance_cycles_summary.unresponsive : 0,\n        m.installat'
    'ions_summary ? m.installations_summary.runs_in_window : 0,\n        m.failure_category, m.severity, m'
    '.investigation_headline, m.root_cause_evidence,\n        m.log_or_source_reference, m.recommended_hum'
    'an_action, m.resource_id\n      ];\n      lines.push(row.map(csvCell).join(","));\n    });\n    return "'
    '\\uFEFF" + lines.join("\\r\\n");\n  }\n\n  var root = D.documentElement;\n  $("theme-toggle").addEventListe'
    'ner("click", function () {\n    var dark = root.getAttribute("data-theme") !== "dark";\n    if (dark) '
    '{ root.setAttribute("data-theme", "dark"); } else { root.removeAttribute("data-theme"); }\n    $("the'
    'me-label").textContent = dark ? "Light mode" : "Dark mode";\n  });\n  var menuBtn = $("export-menu-btn'
    '");\n  var menu = $("export-menu");\n  function setMenu(open) {\n    menu.hidden = !open;\n    menuBtn.s'
    'etAttribute("aria-expanded", open ? "true" : "false");\n  }\n  menuBtn.addEventListener("click", funct'
    'ion (e) {\n    e.stopPropagation();\n    setMenu(menu.hidden);\n    if (!menu.hidden) { menu.querySelec'
    'tor("button").focus(); }\n  });\n  menu.addEventListener("click", function (e) { if (e.target.closest('
    '"button")) { setMenu(false); } });\n  D.addEventListener("click", function (e) { if (!menu.hidden && '
    '!menu.contains(e.target)) { setMenu(false); } });\n  D.addEventListener("keydown", function (e) {\n   '
    ' if (e.key === "Escape" && !menu.hidden) { setMenu(false); menuBtn.focus(); }\n  });\n  $("print-btn")'
    '.addEventListener("click", function () { window.print(); });\n  $("export-json-btn").addEventListener'
    '("click", function () {\n    downloadBlob("patching-investigation-snapshot.json", "application/json;c'
    'harset=utf-8", JSON.stringify(snap, null, 2));\n  });\n  $("export-machines-csv-btn").addEventListener'
    '("click", function () {\n    downloadBlob("patching-investigation-machines.csv", "text/csv;charset=ut'
    'f-8", machinesCsv(snap.machines || []));\n  });\n  $("export-patches-csv-btn").addEventListener("click'
    '", function () {\n    var cols = ["record_kind", "machine_name", "status_or_state", "classification",'
    ' "kb_id", "name", "version", "timestamp_utc", "reference_id"];\n    var lines = [cols.join(",")];\n   '
    ' ((snap.cycles && snap.cycles.maintenance_cycles) || []).forEach(function (c) {\n      lines.push([c.'
    'type, c.machine_name, c.status, c.maintenance_scope || "MaintenanceCycle", "", c.maintenance_configu'
    'ration_name || c.name, "", c.start_utc || "", c.correlation_id || c.resource_id].map(csvCell).join("'
    ',"));\n    });\n    ((snap.patches && snap.patches.combined) || []).forEach(function (p) {\n      lines'
    '.push([p.record_kind, p.machine_name, p.installation_state, p.primary_classification, p.kb_id, p.pat'
    'ch_name, p.version, p.last_modified_utc || "", p.resource_id].map(csvCell).join(","));\n    });\n    d'
    'ownloadBlob("patching-investigation-patches.csv", "text/csv;charset=utf-8", "\\uFEFF" + lines.join("\\'
    'r\\n"));\n  });\n\n  function rich(node, parts) {\n    clear(node);\n    parts.forEach(function (p) { node'
    '.appendChild(typeof p === "string" ? D.createTextNode(p) : el("b", { text: p.b })); });\n  }\n\n  funct'
    'ion renderCover() {\n    var client = snap.client || {};\n    var name = client.name || "Customer";\n  '
    '  var plaque = $("brand-plaque");\n    var label = $("client-name-label");\n    clear(plaque);\n    lab'
    'el.textContent = name;\n    if (client.logo_data_uri && /^data:image\\/(png|jpeg);base64,[A-Za-z0-9+/='
    ']+$/.test(client.logo_data_uri)) {\n      plaque.appendChild(el("img", { src: client.logo_data_uri, a'
    'lt: client.logo_alt || name }));\n      label.className = "client sr-only";\n    }\n\n    var win = snap'
    '.window || {};\n    var total = S.machines_total || 0;\n    var blockers = S.machines_with_blockers_to'
    'tal || 0;\n    var crit = S.critical_machines_total || 0;\n    var high = S.high_machines_total || 0;\n'
    '    var med = S.medium_machines_total || 0;\n    var low = S.low_machines_total || 0;\n    var ok = S.'
    'healthy_machines_total || 0;\n    var parts = ["Of ", { b: pl(total, "machine", "machines") }, " (" +'
    ' pl(S.azure_vms_total || 0, "Azure VM", "Azure VMs") + " and " + pl(S.arc_machines_total || 0, "Azur'
    'e Arc server", "Azure Arc servers") + "), "];\n    if (!blockers) {\n      parts.push("none have activ'
    'e patching blockers.");\n    } else {\n      var sevBits = [];\n      if (crit) { sevBits.push(pl(crit,'
    ' "critical", "critical")); }\n      if (high) { sevBits.push(pl(high, "high", "high")); }\n      if (b'
    'lockers === 1) {\n        parts.push({ b: "1" }, " has a patching blocker" + (crit ? " of critical se'
    'verity" : high ? " of high severity" : "") + ".");\n      } else {\n        parts.push({ b: num(blocke'
    'rs) }, " have patching blockers");\n        if (sevBits.length) { parts.push(", including ", { b: sev'
    'Bits.join(" and ") }); }\n        parts.push(".");\n      }\n    }\n    var cycles = S.maintenance_cycle'
    's_in_window || 0;\n    var unresp = S.maintenance_cycles_unresponsive || 0;\n    var sec = S.pending_s'
    'ecurity_or_critical_patches || 0;\n    if (!cycles) {\n      parts.push(" There were no maintenance wi'
    'ndow runs in the period");\n    } else if (!unresp) {\n      parts.push(" " + (cycles === 1 ? "The win'
    'dow run was applied" : "All " + num(cycles) + " window runs were applied") + " without ShutdownOrUnr'
    'esponsive");\n    } else {\n      parts.push(" ", { b: num(unresp) + " of " + num(cycles) + " window r'
    'uns" }, " ended in ShutdownOrUnresponsive");\n    }\n    if (sec) {\n      parts.push(", and ", { b: pl'
    '(sec, "security or critical patch", "security or critical patches") }, sec === 1 ? " is pending." : '
    '" are pending.");\n    } else {\n      parts.push(", and no security or critical patches are pending."'
    ');\n    }\n    rich($("cover-subtitle"), parts);\n\n    var sources = snap.sources || [];\n    var comple'
    'te = sources.filter(function (s) { return s.status === "complete"; }).length;\n    var prov = snap.pr'
    'ovenance || "LIVE";\n    var tags = $("cover-tags");\n    clear(tags);\n    [\n      ["Generated " + utc'
    '(snap.reference_utc) + " UTC"],\n      ["Window " + (win.period || "—") + ": " + day(win.start_utc) +'
    ' " to " + day(win.end_utc) + " (" + num(win.hours || 0) + " h)"],\n      ["Provenance " + prov + " · '
    'environment " + (snap.environment || "—"), "on"],\n      ["Subscription " + (snap.subscription_id || '
    '"—")],\n      ["Azure Resource Graph 2022-10-01 · " + complete + "/" + sources.length + " sources com'
    'plete"],\n      ["Monthly schedule " + ((snap.methodology && snap.methodology.scheduled_cadence_cron)'
    ' || "0 8 1 * *")]\n    ].forEach(function (t) { tags.appendChild(el("li", { className: t[1] || "", te'
    'xt: t[0] })); });\n\n    var v = crit ? ["crit", "Action required"] : high ? ["high", "Needs attention'
    '"] : (med || low) ? ["med", "Review"] : ["ok", "No blockers"];\n    $("verdict-card").className = "ve'
    'rdict v-" + v[0];\n    $("verdict-label").textContent = v[1];\n    var counts = [["critical", crit], ['
    '"high", high], ["medium", med], ["low", low], ["info", ok]];\n    var detail = counts.filter(function'
    ' (c) { return c[1]; }).map(function (c) { return num(c[1]) + " " + (c[1] === 1 ? SEV[c[0]][2] : SEV['
    'c[0]][3]); }).join(" · ");\n    if (complete < sources.length) { detail += (detail ? ". " : "") + "Pa'
    'rtial coverage: " + complete + " of " + sources.length + " sources complete."; }\n    $("verdict-deta'
    'il").textContent = detail || "No machines in the inventory.";\n    var first = (snap.actions || [])[0'
    '];\n    if (first) {\n      var next = $("verdict-next");\n      next.hidden = false;\n      next.append'
    'Child(D.createTextNode("Start with: "));\n      next.appendChild(el("a", { text: first.failure_catego'
    'ry_label || first.failure_category, attrs: { href: "#sec-actions" } }));\n      next.appendChild(D.cr'
    'eateTextNode(" · " + pl(first.affected_machines_count || 0, "machine", "machines") + "."));\n    }\n\n '
    '   $("dist-total").textContent = pl(total, "machine", "machines");\n    var track = $("severity-track'
    '");\n    var legend = $("severity-legend");\n    clear(track);\n    clear(legend);\n    var aria = [];\n '
    '   counts.forEach(function (c) {\n      if (!c[1]) { return; }\n      var s = SEV[c[0]];\n      var seg'
    ' = el("i", { className: "s-" + s[0], title: s[1] + ": " + c[1] });\n      seg.style.width = (c[1] * 1'
    '00 / Math.max(1, total)) + "%";\n      track.appendChild(seg);\n      legend.appendChild(el("li", { ki'
    'ds: [el("span", { className: "dot s-" + s[0] }), s[1] + " ", el("b", { text: num(c[1]) })] }));\n    '
    '  aria.push(num(c[1]) + " " + (c[1] === 1 ? s[2] : s[3]));\n    });\n    track.setAttribute("aria-labe'
    'l", "Machines by severity: " + (aria.join(", ") || "none"));\n\n    var prv = snap.provenance === "SIM'
    'ULATED";\n    $("sim-note").hidden = !prv;\n    $("sim-text").textContent = "Simulated data (" + prov '
    '+ " · " + (snap.environment || "—") + "): demonstration figures, not read from a real tenant.";\n\n   '
    ' var cName = name;\n    $("foot-left").textContent = "Azure SRE Agent · Post-patching report and fail'
    'ure investigation · " + cName;\n    $("foot-right").textContent = "Generated " + utc(snap.reference_u'
    'tc) + " UTC · read-only tool";\n    var pageTitle = "Post-patching report · Azure Update Manager · " '
    '+ cName + " · " + utc(snap.reference_utc) + " UTC";\n    var pageStyle = D.createElement("style");\n  '
    '  pageStyle.textContent = \'@page { @bottom-left { content: "\' + pageTitle.replace(/[\\\\"]/g, "\\\\$&").'
    'replace(/[\\r\\n\\f]/g, " ") + \'"; font: 9px/1.2 \\\'Outfit\\\', \\\'Segoe UI\\\', system-ui, sans-serif; color'
    ": #475569; } }';\n    D.head.appendChild(pageStyle);\n  }\n\n  function renderKpis() {\n    var blockers "
    '= S.machines_with_blockers_total || 0;\n    var unresp = S.maintenance_cycles_unresponsive || 0;\n    '
    'var sec = S.pending_security_or_critical_patches || 0;\n    var failedExt = S.guest_extensions_failed'
    ' || 0;\n    var failedRuns = S.installation_runs_failed || 0;\n    var blockTone = S.critical_machines'
    '_total ? "crit" : S.high_machines_total ? "high" : blockers ? "med" : "ok";\n    var kpis = [\n      ['
    'num(S.machines_total || 0), "Machines evaluated", pl(S.azure_vms_total || 0, "Azure VM", "Azure VMs"'
    ') + " · " + pl(S.arc_machines_total || 0, "Arc server", "Arc servers"), ""],\n      [num(blockers), "'
    'Machines with blockers", num(S.critical_machines_total || 0) + " critical · " + num(S.high_machines_'
    'total || 0) + " high", blockTone],\n      [num(S.maintenance_cycles_succeeded || 0) + " / " + num(S.m'
    'aintenance_cycles_in_window || 0), "Window cycles applied", num(unresp) + " ShutdownOrUnresponsive",'
    ' unresp ? "crit" : ""],\n      [num(S.installation_runs_in_window || 0), "Installation runs", pl(S.in'
    'stalled_patches_in_window || 0, "patch installed", "patches installed") + (failedRuns ? " · " + num('
    'failedRuns) + " with failures" : ""), failedRuns ? "high" : ""],\n      [num(sec), "Pending security '
    'or critical patches", num(S.pending_rollup_patches || 0) + " UpdateRollUp · " + num(S.pending_total_'
    'patches || 0) + " in total", sec ? "med" : ""],\n      [num(failedExt), "Extensions in Failed state",'
    ' "of " + pl(S.guest_extensions_total || 0, "guest extension", "guest extensions"), failedExt ? "high'
    '" : ""]\n    ];\n    var strip = $("kpi-strip");\n    clear(strip);\n    kpis.forEach(function (k) {\n   '
    '   strip.appendChild(el("div", { className: "kpi", kids: [\n        el("span", { className: "kv" + (k'
    '[3] ? " tone-" + k[3] : ""), text: k[0] }),\n        el("span", { className: "kl", text: k[1] }),\n   '
    '     el("span", { className: "ks", text: k[2] })\n      ] }));\n    });\n  }\n\n  function renderExecutiv'
    'e() {\n    var msgList = $("executive-messages");\n    clear(msgList);\n    (snap.executive_messages ||'
    ' []).forEach(function (m) { msgList.appendChild(el("li", { text: m })); });\n    var box = $("categor'
    'y-breakdown");\n    clear(box);\n    var catCounts = S.category_counts || {};\n    var total = Math.max'
    '(1, S.machines_total || 0);\n    CATS.forEach(function (info) {\n      var count = catCounts[info[0]] '
    '|| 0;\n      var pct = Math.round((count * 100) / total);\n      var row = el("button", { className: "'
    'crow", attrs: { type: "button", "data-cat": info[0] } });\n      row.appendChild(el("span", { text: i'
    'nfo[1] }));\n      var track = el("span", { className: "ct" });\n      var fill = el("i", { className:'
    ' "s-" + SEV[info[2]][0] });\n      fill.style.width = (count ? Math.max(pct, 2) : 0) + "%";\n      tra'
    'ck.appendChild(fill);\n      row.appendChild(track);\n      row.appendChild(el("span", { className: "c'
    'v", kids: [el("b", { text: num(count) }), " · " + pct + "%"] }));\n      row.setAttribute("aria-label'
    '", info[1] + ": " + pl(count, "machine", "machines") + ". Filter the investigation");\n      if (!cou'
    'nt) { row.disabled = true; }\n      box.appendChild(row);\n    });\n  }\n  $("category-breakdown").addEv'
    'entListener("click", function (e) {\n    var row = e.target.closest("button[data-cat]");\n    if (!row'
    ') { return; }\n    resetMachineFilters();\n    $("filter-category").value = row.getAttribute("data-cat'
    '");\n    applyMachineFilters();\n    goTo("sec-investigation");\n  });\n\n  function renderActions() {\n  '
    '  var list = $("actions-table");\n    clear(list);\n    var acts = snap.actions || [];\n    if (!acts.l'
    'ength) {\n      list.appendChild(el("li", { className: "empty-state", text: "No pending actions: no m'
    'achine has patching blockers in this window." }));\n      return;\n    }\n    acts.forEach(function (a,'
    ' i) {\n      var ms = el("div", { className: "plan-ms", kids: [el("span", { className: "lab", text: "'
    'Machines" })] });\n      (a.affected_machines || []).forEach(function (name) {\n        ms.appendChild'
    '(el("button", { className: "mchip", text: name, attrs: { type: "button", "data-machine": name, "aria'
    '-label": "Show " + name + " in the per-machine investigation" } }));\n      });\n      var body = el("'
    'div", { className: "plan-body", kids: [\n        el("div", { className: "plan-head", kids: [\n        '
    '  sevPill(a.severity, a.severity_label),\n          el("h3", { text: a.failure_category_label || a.fa'
    'ilure_category }),\n          el("span", { className: "plan-c", text: pl(a.affected_machines_count ||'
    ' 0, "affected machine", "affected machines") })\n        ] }),\n        el("div", { kids: [\n          '
    'el("p", { className: "plan-act", text: a.recommended_human_action }),\n          el("p", { className:'
    ' "plan-dx", kids: [el("span", { className: "lab", text: "Diagnosis" }), a.investigation_summary] })\n'
    '        ] }),\n        el("div", { kids: [\n          ms,\n          el("div", { className: "plan-ref",'
    ' kids: [el("span", { className: "lab", text: "Technical reference" }), refBlock(a.sample_source_refe'
    'rence)] }),\n          el("p", { className: "plan-ref", kids: [el("span", { className: "lab", text: "'
    'Category" }), el("code", { text: a.failure_category })] })\n        ] })\n      ] });\n      list.appen'
    'dChild(el("li", { className: "plan-item", kids: [el("span", { className: "plan-n", text: String(i + '
    '1), attrs: { "aria-hidden": "true" } }), body] }));\n    });\n  }\n  $("actions-table").addEventListene'
    'r("click", function (e) {\n    var chip = e.target.closest("button[data-machine]");\n    if (!chip) { '
    'return; }\n    resetMachineFilters();\n    $("filter-search").value = chip.getAttribute("data-machine"'
    ');\n    applyMachineFilters();\n    goTo("sec-investigation");\n  });\n\n  var drawersExpanded = true;\n  '
    'var sortKey = "severity";\n  var sortAsc = false;\n  var SORT_ASC = { severity: false, name: true, pen'
    'ding: false, cycles: false };\n  var currentMachines = [];\n  function sortValue(m, key) {\n    if (key'
    ' === "name") { return String(m.name || "").toLowerCase(); }\n    if (key === "pending") { return (m.p'
    'ending_counts || {}).security_or_critical || 0; }\n    if (key === "cycles") { return (m.maintenance_'
    'cycles_summary || {}).unresponsive || 0; }\n    return SEV_RANK[m.severity] !== undefined ? 4 - SEV_R'
    'ANK[m.severity] : -1;\n  }\n  function sortHead(label, key, cls) {\n    var th = el("th", { className: '
    'cls || "", attrs: { scope: "col" } });\n    if (sortKey === key) { th.setAttribute("aria-sort", sortA'
    'sc ? "ascending" : "descending"); }\n    var b = el("button", { className: "sort", text: label, attrs'
    ': { type: "button", "data-sort": key } });\n    b.insertAdjacentHTML("beforeend", \'<svg viewBox="0 0 '
    '12 12" aria-hidden="true"><path d="M6 2v8M3 7l3 3 3-3"/></svg>\');\n    th.appendChild(b);\n    return '
    'th;\n  }\n  function setToggle(btn, open) {\n    clear(btn);\n    btn.appendChild(D.createTextNode(open '
    '? "Hide root cause" : "Show root cause"));\n    btn.appendChild(el("span", { className: "sr-only", te'
    'xt: " for " + btn.getAttribute("data-name") }));\n    btn.setAttribute("aria-expanded", open ? "true"'
    ' : "false");\n  }\n  function resetMachineFilters() {\n    $("filter-category").value = "all";\n    $("f'
    'ilter-hosting").value = "all";\n    $("filter-severity").value = "all";\n    $("filter-search").value '
    '= "";\n  }\n\n  function applyMachineFilters() {\n    var cat = $("filter-category").value;\n    var host'
    ' = $("filter-hosting").value;\n    var sev = $("filter-severity").value;\n    var q = ($("filter-searc'
    'h").value || "").toLowerCase().trim();\n    var allMachines = snap.machines || [];\n    var filtered ='
    ' allMachines.filter(function (m) {\n      if (cat !== "all" && m.failure_category !== cat && (m.match'
    'ed_categories || []).indexOf(cat) === -1) { return false; }\n      if (host !== "all" && m.hosting !='
    '= host) { return false; }\n      if (sev !== "all" && m.severity !== sev) { return false; }\n      if '
    '(q && JSON.stringify(m).toLowerCase().indexOf(q) === -1) { return false; }\n      return true;\n    })'
    ';\n    filtered = filtered.map(function (m, i) { return [m, i]; }).sort(function (a, b) {\n      var x'
    ' = sortValue(a[0], sortKey);\n      var y = sortValue(b[0], sortKey);\n      var d = typeof x === "num'
    'ber" ? x - y : x.localeCompare(y, "en", { numeric: true });\n      return (sortAsc ? d : -d) || a[1] '
    '- b[1];\n    }).map(function (pair) { return pair[0]; });\n    currentMachines = filtered;\n\n    $("mac'
    'hines-count-label").textContent = "Showing " + filtered.length + " of " + allMachines.length + " mac'
    'hines.";\n\n    var table = $("machines-table");\n    clear(table);\n    var thead = el("thead");\n    va'
    'r trH = el("tr");\n    trH.appendChild(sortHead("Severity", "severity", "nw"));\n    trH.appendChild(s'
    'ortHead("Machine", "name"));\n    trH.appendChild(el("th", { text: "Automated root-cause diagnosis", '
    'attrs: { scope: "col" } }));\n    trH.appendChild(el("th", { text: "Host and assessment", attrs: { sc'
    'ope: "col" } }));\n    trH.appendChild(sortHead("Pending", "pending", "n"));\n    trH.appendChild(sort'
    'Head("Cycles", "cycles", "n"));\n    thead.appendChild(trH);\n    table.appendChild(thead);\n\n    var t'
    'body = el("tbody");\n    if (!filtered.length) {\n      var emptyTr = el("tr");\n      emptyTr.appendCh'
    'ild(el("td", { colspan: 6, className: "empty", text: "No machines match the selected filters. Select'
    ' Reset filters to show all machines." }));\n      tbody.appendChild(emptyTr);\n      table.appendChild'
    '(tbody);\n      return;\n    }\n\n    filtered.forEach(function (m, idx) {\n      var drawerId = "drawer-'
    'machine-" + idx;\n      var tr = el("tr", { className: "machine-row" });\n      tr.appendChild(el("td"'
    ', { className: "nw", kids: [sevPill(m.severity, m.severity_label)] }));\n      tr.appendChild(el("td"'
    ', { kids: [\n        el("span", { className: "nm", text: m.name }),\n        el("span", { className: "'
    'sm nw", text: m.resource_group || "—" }),\n        el("span", { className: "sm nw", text: (m.hosting '
    '=== "arc" ? "Azure Arc" : "Azure VM") + " · " + (m.location || "—") })\n      ] }));\n      var extra '
    '= (m.matched_categories || []).length - 1;\n      var btn = el("button", { className: "btn sm tgl", a'
    'ttrs: { type: "button", "aria-controls": drawerId, "data-drawer": drawerId, "data-name": m.name } })'
    ';\n      setToggle(btn, drawersExpanded);\n      tr.appendChild(el("td", { className: "dx", kids: [\n  '
    '      el("span", { className: "dx-t", text: m.failure_category_label || m.failure_category }),\n     '
    '   el("span", { className: "dx-h", text: m.investigation_headline }),\n        extra > 0 ? el("span",'
    ' { className: "sm", text: "+ " + pl(extra, "additional blocker", "additional blockers") + " in the d'
    'etails" }) : null,\n        btn\n      ] }));\n      tr.appendChild(el("td", { className: "host", kids:'
    ' [\n        statusPill(m.power_or_arc_state),\n        el("span", { className: "sm", text: (m.os_name '
    '|| m.os_type || "—") + (m.agent_version ? " · agent " + m.agent_version : "") }),\n        el("span",'
    ' { className: "sm nw", text: "Assessment: " + (m.assessment_status || "—") }),\n        el("span", { '
    'className: "sm nw", text: "Readiness: " + (m.vm_guest_patch_readiness || "—") })\n      ] }));\n      '
    'var pc = m.pending_counts || {};\n      tr.appendChild(el("td", { className: "n", kids: [\n        el('
    '"span", { className: "big", text: num(pc.security_or_critical || 0) }),\n        el("span", { classNa'
    'me: "sm nw", text: "sec./crit." }),\n        el("span", { className: "sm nw", text: num(pc.update_rol'
    'lup || 0) + " RollUp · " + num(pc.total || 0) + " total" })\n      ] }));\n      var mc = m.maintenanc'
    'e_cycles_summary || {};\n      var ic = m.installations_summary || {};\n      tr.appendChild(el("td", '
    '{ className: "n", kids: [\n        el("span", { className: "nw", text: num(mc.succeeded || 0) + " OK '
    '· " + num(mc.unresponsive || 0) + " unresponsive" }),\n        el("span", { className: "sm nw", text:'
    ' pl(ic.runs_in_window || 0, "installation", "installations") })\n      ] }));\n      tbody.appendChild'
    '(tr);\n\n      var dTr = el("tr", { className: "drawer-row", id: drawerId });\n      dTr.hidden = !draw'
    'ersExpanded;\n      var c1 = el("div", { kids: [\n        el("p", { className: "dk", text: "Correlated'
    ' technical evidence (no host sign-in)" }),\n        el("p", { text: m.root_cause_evidence })\n      ] '
    '});\n      var issues = m.all_detected_issues || [];\n      if (issues.length > 1) {\n        c1.append'
    'Child(el("p", { className: "dk", text: "Blockers detected on this machine (" + issues.length + ")" }'
    '));\n        var ul = el("ul", { className: "issues" });\n        issues.forEach(function (iss) { ul.a'
    'ppendChild(el("li", { kids: [sevPill(iss.severity), el("span", { text: iss.investigation_headline })'
    '] })); });\n        c1.appendChild(ul);\n      }\n      var c2 = el("div", { kids: [\n        el("p", { '
    'className: "dk", text: "Recommended action" }),\n        el("p", { className: "act", text: m.recommen'
    'ded_human_action }),\n        el("p", { className: "dk", text: "ARG source reference or log path" }),'
    '\n        el("div", { kids: [refBlock(m.log_or_source_reference || m.resource_id)] })\n      ] });\n   '
    '   if ((m.pending_security_patches || []).length) {\n        c2.appendChild(el("p", { className: "dk"'
    ', text: "Pending Security/RollUp patches" }));\n        var kbs = el("ul", { className: "kbs" });\n   '
    '     m.pending_security_patches.forEach(function (p) {\n          kbs.appendChild(el("li", { kids: [p'
    '.kb_id ? el("code", { text: "KB" + p.kb_id }) : null, p.kb_id ? " " : null, p.patch_name] }));\n     '
    '   });\n        c2.appendChild(kbs);\n      }\n      c2.appendChild(el("p", { className: "sm", kids: ["'
    'Category ", el("code", { text: m.failure_category }), m.resource_id ? el("span", { className: "dlink'
    '", kids: [" · ", portalLink(m.resource_id, "Open in Azure portal")] }) : null] }));\n      var dTd = '
    'el("td", { colspan: 6 });\n      dTd.appendChild(el("div", { className: "drawer", kids: [c1, c2] }));'
    '\n      dTr.appendChild(dTd);\n      tbody.appendChild(dTr);\n    });\n    table.appendChild(tbody);\n  }'
    '\n  $("machines-table").addEventListener("click", function (e) {\n    var sortBtn = e.target.closest("'
    'button[data-sort]");\n    if (sortBtn) {\n      var key = sortBtn.getAttribute("data-sort");\n      if '
    '(key === sortKey) { sortAsc = !sortAsc; } else { sortKey = key; sortAsc = SORT_ASC[key]; }\n      app'
    'lyMachineFilters();\n      var again = $("machines-table").querySelector(\'button[data-sort="\' + key +'
    ' \'"]\');\n      if (again) { again.focus(); }\n      return;\n    }\n    var tgl = e.target.closest("butt'
    'on[data-drawer]");\n    if (tgl) {\n      var row = $(tgl.getAttribute("data-drawer"));\n      row.hidd'
    'en = !row.hidden;\n      setToggle(tgl, !row.hidden);\n    }\n  });\n\n  function renderTable(tableNode, '
    'cols, rows, emptyText) {\n    clear(tableNode);\n    var thead = el("thead");\n    var trHead = el("tr"'
    ');\n    cols.forEach(function (c) { trHead.appendChild(el("th", { text: c[0], className: c[1] || "", '
    'attrs: { scope: "col" } })); });\n    thead.appendChild(trHead);\n    tableNode.appendChild(thead);\n  '
    '  var tbody = el("tbody");\n    if (!rows.length) {\n      var emptyRow = el("tr");\n      emptyRow.app'
    'endChild(el("td", { colspan: cols.length, className: "empty", text: emptyText || "No records match t'
    'he current criteria." }));\n      tbody.appendChild(emptyRow);\n    }\n    rows.forEach(function (r) {\n'
    '      var tr = el("tr");\n      r.forEach(function (cell, i) {\n        var td = el("td", { className:'
    ' cols[i][1] || "" });\n        if (cell && cell.nodeType) {\n          td.appendChild(cell);\n        }'
    ' else {\n          td.textContent = cell === null || cell === undefined || cell === "" ? "—" : String'
    '(cell);\n        }\n        tr.appendChild(td);\n      });\n      tbody.appendChild(tr);\n    });\n    tab'
    'leNode.appendChild(tbody);\n  }\n\n  var PAGE = 80;\n  var cycleLimit = PAGE;\n  var patchLimit = PAGE;\n '
    ' function applyCycleFilters(keepLimit) {\n    if (!keepLimit) { cycleLimit = PAGE; }\n    var st = $("'
    'cycle-status-filter").value;\n    var q = ($("cycle-search-filter").value || "").toLowerCase().trim()'
    ';\n    var combined = [];\n    ((snap.cycles && snap.cycles.maintenance_cycles) || []).forEach(functio'
    'n (c) {\n      combined.push({\n        kind: c.type,\n        machine: c.machine_name || "Global confi'
    'guration",\n        status: c.status,\n        start: c.start_utc || "",\n        end: c.end_utc || "",'
    '\n        config: c.maintenance_configuration_name || c.name || "—",\n        recur: c.schedule_recur_'
    'every || "",\n        ref: c.correlation_id || c.resource_id\n      });\n    });\n    ((snap.cycles && s'
    'nap.cycles.installation_runs) || []).forEach(function (i) {\n      combined.push({\n        kind: "pat'
    'chinstallationresources",\n        machine: i.machine_name,\n        status: i.status,\n        start: '
    'i.start_utc || "",\n        end: i.last_modified_utc || "",\n        detail: "Installed " + i.installe'
    'd_patch_count + " · failed " + i.failed_patch_count + " · not selected " + i.not_selected_patch_coun'
    't + " · reboot " + i.reboot_status,\n        ref: i.maintenance_run_id || i.resource_id\n      });\n   '
    ' });\n    combined.sort(function (a, b) { return (b.start || "").localeCompare(a.start || ""); });\n  '
    '  var filtered = combined.filter(function (r) {\n      if (st !== "all" && r.status !== st) { return '
    'false; }\n      if (q && JSON.stringify(r).toLowerCase().indexOf(q) === -1) { return false; }\n      r'
    'eturn true;\n    });\n    var shown = filtered.slice(0, cycleLimit);\n    $("cycles-count-label").textC'
    'ontent = "Showing " + shown.length + " of " + filtered.length + " cycle and installation records (co'
    'mbined total: " + combined.length + ").";\n    $("cycles-more-row").hidden = filtered.length <= cycle'
    'Limit;\n    $("toc-n-cycles").textContent = num(combined.length);\n    renderTable(\n      $("cycles-ta'
    'ble"),\n      [["Record"], ["Machine or scope", "nw"], ["Status", "nw"], ["Start and end (UTC)", "nw"'
    '], ["Run details"], ["Reference (correlation or resource)"]],\n      shown.map(function (r) {\n       '
    ' return [\n          el("span", { className: "kind", title: r.kind, kids: [el("b", { text: KIND[r.kin'
    'd] || r.kind }), el("span", { className: "sm", text: r.kind === "patchinstallationresources" ? "patc'
    'hinstallationresources" : "maintenanceresources" })] }),\n          r.machine,\n          statusPill(r'
    '.status),\n          el("span", { kids: [utc(r.start), el("span", { className: "sm", text: r.end ? "t'
    'o " + utc(r.end) : "" })] }),\n          r.config ? el("span", { kids: ["Configuration ", el("span", '
    '{ className: "seg", text: r.config }), r.recur ? " (" + r.recur + ")" : null] }) : r.detail,\n       '
    '   armCell(r.ref)\n        ];\n      })\n    );\n  }\n\n  function applyPatchFilters(keepLimit) {\n    if ('
    '!keepLimit) { patchLimit = PAGE; }\n    var st = $("patch-state-filter").value;\n    var cl = $("patch'
    '-class-filter").value;\n    var q = ($("patch-search-filter").value || "").toLowerCase().trim();\n    '
    'var allPatches = (snap.patches && snap.patches.combined) || [];\n    var filtered = allPatches.filter'
    '(function (p) {\n      if (st !== "all" && p.installation_state !== st) { return false; }\n      if (c'
    'l !== "all") {\n        if (cl === "Security") {\n          if (p.primary_classification !== "Security'
    '" && p.primary_classification !== "Critical") { return false; }\n        } else if (p.primary_classif'
    'ication !== cl) {\n          return false;\n        }\n      }\n      if (q && JSON.stringify(p).toLower'
    'Case().indexOf(q) === -1) { return false; }\n      return true;\n    });\n    var shown = filtered.slic'
    'e(0, patchLimit);\n    $("patches-count-label").textContent = "Showing " + shown.length + " of " + fi'
    'ltered.length + " softwarePatches records (total collected: " + allPatches.length + ").";\n    $("pat'
    'ches-more-row").hidden = filtered.length <= patchLimit;\n    renderTable(\n      $("patches-table"),\n '
    '     [["Machine", "nw"], ["State and classification", "nw"], ["KB / ID"], ["Package or update", "wid'
    'e"], ["Date (UTC)", "nw"]],\n      shown.map(function (p) {\n        var sub = [p.version ? "version "'
    ' + p.version : "", p.reboot_behavior ? "reboot " + p.reboot_behavior : ""].filter(Boolean).join(" · '
    '");\n        return [\n          p.machine_name,\n          el("span", { className: "stack", kids: [sta'
    'tusPill(p.installation_state), classPill(p.primary_classification)] }),\n          code(p.kb_id ? "KB'
    '" + p.kb_id : (p.patch_id || "—"), "ref"),\n          el("span", { kids: [p.patch_name || "—", sub ? '
    'el("span", { className: "sm", text: sub }) : null] }),\n          utc(p.last_modified_utc)\n        ];'
    '\n      })\n    );\n  }\n\n  function renderExtensionsAndSources() {\n    var exts = snap.extensions || []'
    ';\n    renderTable(\n      $("extensions-table"),\n      [["Machine", "nw"], ["Hosting", "nw"], ["Exten'
    'sion"], ["Publisher / type"], ["Version", "nw"], ["State", "nw"], ["AutoUpgrade minor / auto", "nw"]'
    '],\n      exts.map(function (e) {\n        return [\n          e.machine_name,\n          e.hosting === '
    '"arc" ? "Azure Arc" : e.hosting === "azure" ? "Azure VM" : e.hosting,\n          code(e.name, "ref"),'
    '\n          el("span", { kids: [e.publisher || "—", el("span", { className: "sm", text: e.extension_t'
    'ype || "" })] }),\n          code(e.type_handler_version || "—", "ref"),\n          statusPill(e.provi'
    'sioning_state),\n          yesNo(e.auto_upgrade_minor_version) + " / " + yesNo(e.enable_automatic_upg'
    'rade)\n        ];\n      }),\n      "No guest extensions were found on the inventoried machines."\n    )'
    ';\n\n    var sources = snap.sources || [];\n    renderTable(\n      $("sources-table"),\n      [["Source"'
    '], ["Status", "nw"], ["Pages", "n"], ["Records", "n"], ["Observed (UTC)", "nw"], ["Endpoint or note"'
    ']],\n      sources.map(function (s) {\n        return [\n          el("code", { text: s.id }),\n        '
    '  el("span", { className: "pill " + (TONE[s.status] || "neutral"), text: SOURCE_STATUS[s.status] || '
    's.status }),\n          num(s.pages),\n          num(s.records),\n          utc(s.observed_at),\n       '
    '   (s.note || "") + (s.errors && s.errors.length ? " Errors: " + JSON.stringify(s.errors) : "")\n    '
    '    ];\n      })\n    );\n    var complete = sources.filter(function (s) { return s.status === "complet'
    'e"; }).length;\n    $("toc-n-sources").textContent = complete + "/" + sources.length;\n    $("toc-n-ex'
    'tensions").textContent = num(exts.length);\n    $("toc-n-patches").textContent = num(((snap.patches &'
    '& snap.patches.combined) || []).length);\n    $("toc-n-actions").textContent = num((snap.actions || ['
    ']).length);\n    $("toc-n-machines").textContent = num((snap.machines || []).length);\n\n    var method'
    ' = snap.methodology || {};\n    var mList = $("methodology-list");\n    clear(mList);\n    (method.limi'
    'tations || []).forEach(function (item) { mList.appendChild(el("li", { text: item })); });\n    var tL'
    'ist = $("method-tables");\n    clear(tList);\n    (method.arg_tables || []).forEach(function (item) { '
    'tList.appendChild(el("li", { text: item })); });\n    if (method.scheduled_cadence_description) {\n   '
    '   tList.appendChild(el("li", { kids: ["Cadence: " + method.scheduled_cadence_description + " Cron "'
    ', el("code", { text: method.scheduled_cadence_cron || "0 8 1 * *" }), "."] }));\n    }\n  }\n\n  ["filte'
    'r-category", "filter-hosting", "filter-severity", "filter-search"].forEach(function (id) {\n    var n'
    'ode = $(id);\n    node.addEventListener("input", applyMachineFilters);\n    node.addEventListener("cha'
    'nge", applyMachineFilters);\n  });\n  $("filter-reset-btn").addEventListener("click", function () {\n  '
    '  resetMachineFilters();\n    applyMachineFilters();\n  });\n  $("machines-view-csv-btn").addEventListe'
    'ner("click", function () {\n    downloadBlob("patching-investigation-machines-view.csv", "text/csv;ch'
    'arset=utf-8", machinesCsv(currentMachines));\n  });\n  $("toggle-all-drawers-btn").addEventListener("c'
    'lick", function () {\n    drawersExpanded = !drawersExpanded;\n    this.textContent = drawersExpanded '
    '? "Collapse all details" : "Expand all details";\n    applyMachineFilters();\n  });\n  ["cycle-status-f'
    'ilter", "cycle-search-filter"].forEach(function (id) {\n    var node = $(id);\n    node.addEventListen'
    'er("input", function () { applyCycleFilters(false); });\n    node.addEventListener("change", function'
    ' () { applyCycleFilters(false); });\n  });\n  ["patch-state-filter", "patch-class-filter", "patch-sear'
    'ch-filter"].forEach(function (id) {\n    var node = $(id);\n    node.addEventListener("input", functio'
    'n () { applyPatchFilters(false); });\n    node.addEventListener("change", function () { applyPatchFil'
    'ters(false); });\n  });\n  $("cycles-more-btn").addEventListener("click", function () { cycleLimit += '
    'PAGE; applyCycleFilters(true); });\n  $("patches-more-btn").addEventListener("click", function () { p'
    'atchLimit += PAGE; applyPatchFilters(true); });\n\n  function trackSections() {\n    var links = Array.'
    'prototype.slice.call(D.querySelectorAll(".toc a"));\n    var targets = links.map(function (a) { retur'
    'n $(a.getAttribute("href").slice(1)); });\n    var current = null;\n    var queued = false;\n    functi'
    'on update() {\n      queued = false;\n      var line = window.innerHeight * 0.3;\n      var index = 0;\n'
    '      targets.forEach(function (t, i) { if (t && t.getBoundingClientRect().top <= line) { index = i;'
    ' } });\n      if (window.innerHeight + window.scrollY >= D.documentElement.scrollHeight - 2) { index '
    '= targets.length - 1; }\n      if (links[index] !== current) {\n        if (current) { current.removeA'
    'ttribute("aria-current"); }\n        current = links[index];\n        current.setAttribute("aria-curre'
    'nt", "true");\n      }\n    }\n    window.addEventListener("scroll", function () {\n      if (!queued) {'
    ' queued = true; window.requestAnimationFrame(update); }\n    }, { passive: true });\n    update();\n  }'
    '\n\n  function sizeDrawers() {\n    var wrap = $("machines-table").parentNode;\n    wrap.style.setProper'
    'ty("--wrap-w", wrap.clientWidth + "px");\n  }\n  window.addEventListener("resize", sizeDrawers);\n\n  $('
    '"report-content").hidden = false;\n  renderCover();\n  renderKpis();\n  renderExecutive();\n  renderActi'
    'ons();\n  applyMachineFilters();\n  applyCycleFilters(false);\n  applyPatchFilters(false);\n  renderExte'
    'nsionsAndSources();\n  trackSections();\n  sizeDrawers();\n})();\n</script>\n</body>\n</html>\n'
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
    def __init__(self, code, message, source="investigation", http_status=None):
        super().__init__(message)
        self.code = code
        self.source = source
        self.http_status = http_status

    def public(self):
        return {
            "code": self.code,
            "message": str(self),
            "source_id": self.source,
            "http_status": self.http_status,
        }


def utc_now():
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_utc(value, source="normalization", required=False):
    if value is None or value == "":
        if required:
            raise EvidenceError("invalid_timestamp", "Required UTC timestamp is missing.", source)
        return None
    if not isinstance(value, str) or len(value) > 64 or any(ord(c) < 32 for c in value):
        raise EvidenceError("invalid_timestamp", "Timestamp has invalid type or length.", source)
    if value.startswith("0001-01-01"):
        return None
    cleaned = value.strip()
    if cleaned.endswith("Z"):
        cleaned = cleaned[:-1] + "+00:00"
    if "." in cleaned:
        head, tail = cleaned.split(".", 1)
        tz_pos = max(tail.find("+"), tail.find("-"))
        if tz_pos != -1:
            frac, tz_part = tail[:tz_pos], tail[tz_pos:]
        else:
            frac, tz_part = tail, ""
        cleaned = head + "." + frac[:6].ljust(6, "0") + tz_part
    try:
        dt = datetime.fromisoformat(cleaned)
    except ValueError as exc:
        raise EvidenceError("invalid_timestamp", "Malformed ISO-8601 timestamp in source payload.", source) from exc
    if dt.tzinfo is None or dt.utcoffset() is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def format_utc(dt):
    if dt is None:
        return None
    return dt.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def plural(count, one, many):
    return format(count, ",") + " " + (one if count == 1 else many)


def obj(value, source="normalization"):
    if not isinstance(value, dict):
        raise EvidenceError("invalid_shape", "Expected an object in source payload.", source)
    return value


def pick(value, *keys):
    cur = value
    for key in keys:
        if not isinstance(cur, dict) or key not in cur:
            return None
        cur = cur[key]
    return cur


def text(value, source="normalization", maximum=8192):
    if value is None:
        return None
    if not isinstance(value, str):
        value = str(value)
    cleaned = value.replace("\r", " ").replace("\n", " ").strip()
    if len(cleaned) > maximum or any(ord(c) < 32 for c in cleaned):
        raise EvidenceError("invalid_field", "Source text exceeds maximum length or contains control characters.", source)
    return cleaned


def integer(value, source="normalization", default=0):
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise EvidenceError("invalid_field", "Source numeric field is not finite.", source)
    return int(value)


def boolean(value, source="normalization"):
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.lower() in ("true", "false"):
        return value.lower() == "true"
    raise EvidenceError("invalid_field", "Source boolean field has invalid type.", source)


def tags_map(value, source="normalization"):
    if value is None:
        return {}
    result = {}
    for k, v in obj(value, source).items():
        key = text(str(k), source, 256)
        if not key:
            continue
        if any(word in key.lower() for word in ("secret", "password", "token", "key", "sas", "credential", "connectionstring")):
            continue
        if isinstance(v, (str, int, float, bool)) or v is None:
            result[key] = text(str(v), source, 512) if v is not None else None
    return result


def guid(value, field):
    try:
        if not isinstance(value, str) or str(UUID(value)) != value.lower() or UUID(value).int == 0:
            raise ValueError
    except (ValueError, AttributeError) as exc:
        raise EvidenceError("configuration_required", "Configure " + field + " with a valid non-zero GUID.", "configuration") from exc
    return value.lower()


def validate_logo(uri, alt=CLIENT_LOGO_ALT):
    if uri == "":
        return
    if not isinstance(uri, str) or len(uri) > 140000:
        raise EvidenceError("invalid_logo", "Optional logo must be a bounded inline PNG/JPEG data URI.", "branding")
    match = re.fullmatch(r"data:image/(png|jpeg);base64,([A-Za-z0-9+/=]+)", uri)
    if not match:
        raise EvidenceError("invalid_logo", "Only inline PNG/JPEG MIME with canonical base64 is allowed.", "branding")
    try:
        data = base64.b64decode(match[2], validate=True)
    except binascii.Error as exc:
        raise EvidenceError("invalid_logo", "Invalid logo base64.", "branding") from exc
    if base64.b64encode(data).decode("ascii") != match[2] or not 1 <= len(data) <= 100000:
        raise EvidenceError("invalid_logo", "Optional raster logo must contain 1..100000 canonical base64 bytes.", "branding")
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
                    or not 1 <= width <= 2048
                    or not 1 <= height <= 2048
                    or getattr(image, "n_frames", 1) != 1
                ):
                    raise EvidenceError("invalid_logo", "Use one PNG/JPEG frame, matching MIME, at most 2048x2048 px.", "branding")
                image.verify()
            with Image.open(io.BytesIO(data), formats=["PNG", "JPEG"]) as image:
                image.load()
    except (OSError, ValueError, SyntaxError, UnidentifiedImageError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise EvidenceError("invalid_logo", "Logo bytes failed complete raster decode.", "branding") from exc


def validate_config():
    if not isinstance(CLIENT_NAME, str) or not CLIENT_NAME.strip() or len(CLIENT_NAME) > 120 or re.search(r"[\x00-\x1f\x7f]", CLIENT_NAME):
        raise EvidenceError("invalid_configuration", "CLIENT_NAME must be 1..120 plain characters.", "configuration")
    validate_logo(CLIENT_LOGO_DATA_URI, CLIENT_LOGO_ALT)
    subscription_id = guid(SUBSCRIPTION_ID, "SUBSCRIPTION_ID")
    client_id = guid(MANAGED_IDENTITY_CLIENT_ID, "MANAGED_IDENTITY_CLIENT_ID")
    return {
        "subscription_id": subscription_id,
        "client_id": client_id,
        "client_name": CLIENT_NAME.strip(),
        "logo_data_uri": CLIENT_LOGO_DATA_URI,
        "logo_alt": CLIENT_LOGO_ALT.strip(),
    }


def validate_parameters(
    operation="report",
    period="last_30d",
    view="summary",
    hosting="all",
    failure_category="all",
    machine_name="",
    limit=25,
    offset=0,
):
    for field, value, allowed in (
        ("operation", operation, OPERATIONS),
        ("period", period, PERIODS),
        ("view", view, VIEWS),
        ("hosting", hosting, HOSTINGS),
        ("failure_category", failure_category, FAILURE_CATEGORIES),
    ):
        if not isinstance(value, str) or value not in allowed:
            raise EvidenceError("invalid_parameter", "Invalid value for " + field + ".", "parameters")
    if not isinstance(machine_name, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{0,128}", machine_name):
        raise EvidenceError("invalid_parameter", "machine_name must match ^[A-Za-z0-9_.-]{0,128}$.", "parameters")
    if type(limit) is not int or not 1 <= limit <= 100:
        raise EvidenceError("invalid_parameter", "limit must be an integer between 1 and 100.", "parameters")
    if type(offset) is not int or not 0 <= offset <= 500000:
        raise EvidenceError("invalid_parameter", "offset must be an integer between 0 and 500000.", "parameters")
    if operation == "report" and (
        view != "summary"
        or hosting != "all"
        or failure_category != "all"
        or machine_name != ""
        or limit != 25
        or offset != 0
    ):
        raise EvidenceError("invalid_parameter", "operation='report' requires default query/filter/paging arguments.", "parameters")
    return {
        "operation": operation,
        "period": period,
        "view": view,
        "hosting": hosting,
        "failure_category": failure_category,
        "machine_name": machine_name,
        "limit": limit,
        "offset": offset,
    }


def window_for(period, reference_utc):
    end_dt = parse_utc(reference_utc, "window", required=True)
    hours = PERIOD_HOURS[period]
    start_dt = end_dt - timedelta(hours=hours)
    return {
        "period": period,
        "hours": hours,
        "start_utc": format_utc(start_dt),
        "end_utc": format_utc(end_dt),
    }


def arg_queries():
    return {
        "arg_compute_machines": (
            "resources "
            "| where type in~ ('microsoft.compute/virtualmachines', 'microsoft.hybridcompute/machines') "
            "| project id, name, type, resourceGroup, location, tags, properties"
        ),
        "arg_patch_assessments": (
            "patchassessmentresources "
            "| where type !endswith '/softwarepatches' "
            "| project id, name, type, resourceGroup, location, properties"
        ),
        "arg_software_patches_pending": (
            "patchassessmentresources "
            "| where type endswith '/softwarepatches' "
            "| project id, name, type, resourceGroup, location, properties"
        ),
        "arg_patch_installations": (
            "patchinstallationresources "
            "| where type !endswith '/softwarepatches' "
            "| project id, name, type, resourceGroup, location, properties"
        ),
        "arg_software_patches_installed": (
            "patchinstallationresources "
            "| where type endswith '/softwarepatches' "
            "| project id, name, type, resourceGroup, location, properties"
        ),
        "arg_maintenance_cycles": (
            "maintenanceresources "
            "| project id, name, type, resourceGroup, location, properties"
        ),
        "arg_patch_extensions": (
            "resources "
            "| where type in~ ('microsoft.compute/virtualmachines/extensions', 'microsoft.hybridcompute/machines/extensions') "
            "| project id, name, type, resourceGroup, location, "
            "properties=bag_pack("
            "'publisher', properties.publisher, "
            "'type', properties.type, "
            "'typeHandlerVersion', properties.typeHandlerVersion, "
            "'provisioningState', properties.provisioningState, "
            "'autoUpgradeMinorVersion', properties.autoUpgradeMinorVersion, "
            "'enableAutomaticUpgrade', properties.enableAutomaticUpgrade)"
        ),
    }


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise HTTPError(req.full_url, code, "Redirects are disabled for read-only ARG transport.", headers, fp)


class Identity:
    def __init__(self, config):
        try:
            from azure.core.exceptions import ClientAuthenticationError, ServiceRequestError
            from azure.identity import CredentialUnavailableError, ManagedIdentityCredential
        except ImportError as exc:
            raise EvidenceError("dependency_missing", "azure-identity is required for ManagedIdentityCredential.", "identity") from exc
        self.config = config
        self.auth_errors = (CredentialUnavailableError, ClientAuthenticationError, ServiceRequestError)
        self.credential = ManagedIdentityCredential(client_id=config["client_id"])
        self._cached_token = None
        self._expires_on = 0

    def close(self):
        try:
            self.credential.close()
        except Exception:
            pass

    def arm_token(self):
        now = time.time()
        if self._cached_token and self._expires_on > now + 60:
            return self._cached_token
        try:
            token_obj = self.credential.get_token(ARM_ORIGIN + "/.default")
        except self.auth_errors as exc:
            raise EvidenceError("authentication_failed", "ManagedIdentityCredential failed to acquire ARM token.", "identity") from exc
        raw_token = getattr(token_obj, "token", None)
        if not isinstance(raw_token, str) or not raw_token.strip():
            raise EvidenceError("authentication_failed", "ManagedIdentityCredential returned an empty ARM token.", "identity")
        parts = raw_token.split(".")
        if len(parts) >= 2:
            try:
                padded = parts[1] + "=" * (-len(parts[1]) % 4)
                claims = json.loads(base64.urlsafe_b64decode(padded).decode("utf-8"))
                claims = normalize_sidecar_claims(claims)
            except Exception as exc:
                raise EvidenceError("authentication_failed", "ARM JWT payload could not be decoded for claim verification.", "identity") from exc
            app_claim = (claims.get("appid") or claims.get("azp") or "").lower()
            if app_claim and app_claim != self.config["client_id"]:
                raise EvidenceError("identity_mismatch", "Token client_id claim does not match MANAGED_IDENTITY_CLIENT_ID.", "identity")
            aud_claim = (claims.get("aud") or "").rstrip("/").lower()
            if aud_claim and aud_claim not in ARM_TOKEN_AUDIENCES:
                raise EvidenceError("identity_mismatch", "Token audience is not Azure Resource Manager.", "identity")
        self._cached_token = raw_token
        self._expires_on = getattr(token_obj, "expires_on", now + 300)
        return raw_token


class ArgReader:
    def __init__(self, identity, config, deadline=None):
        self.identity = identity
        self.config = config
        self.deadline = deadline
        self.attempts = 0
        context = ssl.create_default_context()
        self.opener = build_opener(NoRedirect(), HTTPSHandler(context=context))
        self.allowed_queries = set(arg_queries().values())

    def query_table(self, source_id, query_text, reference_utc):
        url = ARM_ORIGIN + ARG_PATH + "?api-version=" + ARG_API_VERSION
        receipt = {
            "id": source_id,
            "source_id": source_id,
            "endpoint": "POST " + url,
            "subscription_id": self.config["subscription_id"],
            "status": "complete",
            "pages": 0,
            "records": 0,
            "observed_at": reference_utc,
            "note": "Read-only Azure Resource Graph query (" + source_id + ").",
            "errors": [],
        }
        rows = []
        skip_token = None
        seen_tokens = set()
        try:
            for page_idx in range(1, MAX_PAGES + 1):
                if self.deadline is not None and time.monotonic() >= self.deadline:
                    raise EvidenceError("collection_deadline", "Collection time budget exceeded during " + source_id + ".", source_id)
                options = {"$top": 1000, "resultFormat": "objectArray"}
                if skip_token is not None:
                    options["$skipToken"] = skip_token
                body = {
                    "subscriptions": [self.config["subscription_id"]],
                    "query": query_text,
                    "options": options,
                }
                payload = self._post_arg(url, body, source_id)
                receipt["pages"] = page_idx
                data = payload.get("data")
                if not isinstance(data, list) or any(not isinstance(item, dict) for item in data):
                    raise EvidenceError("invalid_response", "ARG data field must be an objectArray list.", source_id)
                rows.extend(data)
                receipt["records"] = len(rows)
                if len(rows) > MAX_ROWS:
                    raise EvidenceError("row_bound_exceeded", "ARG query exceeded MAX_ROWS=" + str(MAX_ROWS) + ".", source_id)
                next_token = payload.get("$skipToken")
                if next_token is None:
                    break
                if not isinstance(next_token, str) or not next_token or len(next_token) > 8192 or next_token in seen_tokens:
                    raise EvidenceError("pagination_loop", "Invalid or repeated ARG $skipToken.", source_id)
                seen_tokens.add(next_token)
                skip_token = next_token
            else:
                raise EvidenceError("page_bound_exceeded", "ARG pagination exceeded MAX_PAGES=" + str(MAX_PAGES) + ".", source_id)
        except EvidenceError as exc:
            receipt["status"] = "partial" if rows else ("denied" if exc.http_status in (401, 403) else "error")
            receipt["errors"].append(exc.public())
        return rows, receipt

    def _post_arg(self, url, body, source_id):
        parsed = urlsplit(url)
        if (
            parsed.scheme != "https"
            or parsed.netloc.lower() != "management.azure.com"
            or unquote(parsed.path) != ARG_PATH
            or parse_qsl(parsed.query) != [("api-version", ARG_API_VERSION)]
            or not isinstance(body, dict)
            or body.get("subscriptions") != [self.config["subscription_id"]]
            or body.get("query") not in self.allowed_queries
        ):
            raise EvidenceError("unsafe_endpoint", "Only fixed read-only Azure Resource Graph queries are permitted.", source_id)
        encoded_body = json.dumps(body, separators=(",", ":"), allow_nan=False).encode("utf-8")
        headers = {
            "Authorization": "Bearer " + self.identity.arm_token(),
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        for attempt in range(3):
            self.attempts += 1
            if self.attempts > MAX_HTTP_ATTEMPTS:
                raise EvidenceError("http_attempt_bound", "Exceeded MAX_HTTP_ATTEMPTS.", source_id)
            req = Request(url, data=encoded_body, headers=headers, method="POST")
            try:
                with self.opener.open(req, timeout=30) as resp:
                    status = getattr(resp, "status", 200)
                    raw_bytes = resp.read(HTTP_BYTES + 1)
                    if len(raw_bytes) > HTTP_BYTES:
                        raise EvidenceError("response_too_large", "ARG response exceeded HTTP_BYTES bound.", source_id)
                    if status != 200:
                        raise EvidenceError("http_error", "ARG returned HTTP " + str(status) + ".", source_id, status)
                    decoded = json.loads(raw_bytes.decode("utf-8"))
                    if not isinstance(decoded, dict):
                        raise EvidenceError("invalid_response", "ARG response root must be a JSON object.", source_id)
                    return decoded
            except HTTPError as exc:
                if exc.code in (429, 500, 502, 503, 504) and attempt < 2:
                    time.sleep(attempt + 1)
                    continue
                raise EvidenceError(
                    "access_denied" if exc.code in (401, 403) else "http_error",
                    "ARG request failed with HTTP " + str(exc.code) + ".",
                    source_id,
                    exc.code,
                ) from exc
            except URLError as exc:
                if attempt < 2:
                    time.sleep(attempt + 1)
                    continue
                raise EvidenceError("network_error", "ARG transport failed to reach management.azure.com.", source_id) from exc
            except (UnicodeDecodeError, ValueError) as exc:
                raise EvidenceError("invalid_response", "ARG returned malformed JSON.", source_id) from exc
        raise EvidenceError("http_error", "ARG retries exhausted.", source_id)


def parent_machine_id(resource_id, source="normalization"):
    rid = text(resource_id, source, 2048)
    if not rid:
        raise EvidenceError("invalid_resource_id", "Empty resource ID.", source)
    low = rid.lower()
    for marker in (
        "/patchassessmentresults/",
        "/patchinstallationresults/",
        "/providers/microsoft.maintenance/",
        "/extensions/",
    ):
        pos = low.find(marker)
        if pos != -1:
            return low[:pos]
    return low.rstrip("/")


def machine_name_from_id(machine_id):
    if not isinstance(machine_id, str) or "/" not in machine_id:
        return ""
    return machine_id.rstrip("/").split("/")[-1]


def normalize_machine(row, subscription_id, reference_utc):
    source = "arg_compute_machines"
    rid = text(row.get("id"), source, 2048)
    if not rid or not rid.lower().startswith("/subscriptions/" + subscription_id.lower() + "/"):
        raise EvidenceError("scope_mismatch", "Machine resource ID is outside the configured subscription.", source)
    rtype = (text(row.get("type"), source, 128) or "").lower()
    if rtype not in ("microsoft.compute/virtualmachines", "microsoft.hybridcompute/machines"):
        raise EvidenceError("invalid_type", "Unexpected compute resource type: " + rtype, source)
    hosting = "arc" if rtype == "microsoft.hybridcompute/machines" else "azure"
    name = text(row.get("name"), source, 256) or machine_name_from_id(rid)
    rg = text(row.get("resourceGroup"), source, 128) or ""
    location = text(row.get("location"), source, 128) or ""
    props = obj(row.get("properties") or {}, source)
    tags = tags_map(row.get("tags"), source)

    os_profile = props.get("osProfile") if isinstance(props.get("osProfile"), dict) else {}
    win_conf = os_profile.get("windowsConfiguration") if isinstance(os_profile.get("windowsConfiguration"), dict) else {}
    lin_conf = os_profile.get("linuxConfiguration") if isinstance(os_profile.get("linuxConfiguration"), dict) else {}
    patch_settings = (
        win_conf.get("patchSettings")
        if isinstance(win_conf.get("patchSettings"), dict)
        else (lin_conf.get("patchSettings") if isinstance(lin_conf.get("patchSettings"), dict) else {})
    )
    os_disk = pick(props, "storageProfile", "osDisk")
    os_disk = os_disk if isinstance(os_disk, dict) else {}
    ext_view = pick(props, "extended", "instanceView")
    ext_view = ext_view if isinstance(ext_view, dict) else {}
    power_obj = ext_view.get("powerState") if isinstance(ext_view.get("powerState"), dict) else {}

    os_type_raw = props.get("osType") or os_disk.get("osType") or (
        "Windows" if win_conf else ("Linux" if lin_conf else None)
    )
    os_type = text(os_type_raw, source, 64)
    if os_type:
        os_type = "Windows" if os_type.lower().startswith("win") else ("Linux" if os_type.lower().startswith("lin") else os_type)
    os_name = text(props.get("osName") or ext_view.get("osName") or props.get("osSku"), source, 256)
    os_version = text(props.get("osVersion") or ext_view.get("osVersion"), source, 128)
    patch_mode = text(
        patch_settings.get("patchMode") or pick(props, "osProfile", "windowsConfiguration", "patchSettings", "patchMode") or pick(props, "osProfile", "linuxConfiguration", "patchSettings", "patchMode"),
        source,
        128,
    )
    assessment_mode = text(
        patch_settings.get("assessmentMode") or pick(props, "osProfile", "windowsConfiguration", "patchSettings", "assessmentMode") or pick(props, "osProfile", "linuxConfiguration", "patchSettings", "assessmentMode"),
        source,
        128,
    )
    power_state = text(power_obj.get("code") or props.get("powerState"), source, 128)
    arc_status = text(props.get("status"), source, 64) if hosting == "arc" else None
    last_status_change = format_utc(parse_utc(props.get("lastStatusChange"), source))
    agent_version = text(props.get("agentVersion"), source, 128)
    vm_id = text(props.get("vmId"), source, 128)
    provisioning_state = text(props.get("provisioningState"), source, 64)

    return {
        "id": rid.lower(),
        "resource_id": rid,
        "name": name,
        "type": rtype,
        "hosting": hosting,
        "resource_group": rg,
        "location": location,
        "os_type": os_type or "Unknown",
        "os_name": os_name or (os_type or "Unknown"),
        "os_version": os_version,
        "patch_mode": patch_mode,
        "assessment_mode": assessment_mode,
        "power_state": power_state,
        "arc_status": arc_status,
        "last_status_change_utc": last_status_change,
        "agent_version": agent_version,
        "vm_id": vm_id,
        "provisioning_state": provisioning_state,
        "tags": tags,
        "observed_at": reference_utc,
    }


def extract_log_path(message):
    if not isinstance(message, str):
        return None
    match = re.search(r"\[([A-Za-z]:\\[^\]]+|/[A-Za-z0-9_./-]+)\]", message)
    if match:
        return match.group(1)
    return None


def normalize_assessment(row, subscription_id, reference_utc):
    source = "arg_patch_assessments"
    rid = text(row.get("id"), source, 2048)
    if not rid or not rid.lower().startswith("/subscriptions/" + subscription_id.lower() + "/"):
        raise EvidenceError("scope_mismatch", "Assessment resource ID is outside the configured subscription.", source)
    machine_id = parent_machine_id(rid, source)
    props = obj(row.get("properties") or {}, source)
    counts = props.get("availablePatchCountByClassification")
    counts = counts if isinstance(counts, dict) else {}
    conf = props.get("configurationStatus")
    conf = conf if isinstance(conf, dict) else {}
    assess_conf = conf.get("assessmentModeConfiguration") if isinstance(conf.get("assessmentModeConfiguration"), dict) else {}
    patch_conf = conf.get("patchModeConfiguration") if isinstance(conf.get("patchModeConfiguration"), dict) else {}
    readiness_conf = conf.get("vmGuestPatchReadiness") if isinstance(conf.get("vmGuestPatchReadiness"), dict) else {}
    err = props.get("errorDetails") if isinstance(props.get("errorDetails"), dict) else {}
    hotpatch = props.get("hotpatchStatus") if isinstance(props.get("hotpatchStatus"), dict) else None

    hotpatch_err = (hotpatch or {}).get("error") if isinstance((hotpatch or {}).get("error"), dict) else {}
    hotpatch_details = hotpatch_err.get("details") if isinstance(hotpatch_err.get("details"), list) else []
    hotpatch_detail_codes = [
        text(item.get("code"), source, 256)
        for item in hotpatch_details
        if isinstance(item, dict) and item.get("code")
    ]
    hotpatch_detail_msgs = [
        text(item.get("message"), source, 1024)
        for item in hotpatch_details
        if isinstance(item, dict) and item.get("message")
    ]
    hotpatch_msg = text(hotpatch_err.get("message"), source, 2048)
    hotpatch_log_path = extract_log_path(hotpatch_msg or "")

    sec_count = integer(counts.get("security"), source, 0)
    crit_count = integer(counts.get("critical"), source, 0)
    rollup_count = integer(counts.get("updateRollup"), source, 0)
    def_count = integer(counts.get("definition"), source, 0)
    upd_count = integer(counts.get("updates"), source, 0)
    fp_count = integer(counts.get("featurePack"), source, 0)
    sp_count = integer(counts.get("servicePack"), source, 0)
    tools_count = integer(counts.get("tools"), source, 0)
    other_count = integer(counts.get("other"), source, 0)

    return {
        "id": rid.lower(),
        "resource_id": rid,
        "machine_id": machine_id,
        "machine_name": machine_name_from_id(machine_id),
        "assessment_activity_id": text(props.get("assessmentActivityId") or row.get("name"), source, 128),
        "status": text(props.get("status"), source, 64) or "Unknown",
        "reboot_pending": boolean(props.get("rebootPending"), source),
        "start_utc": format_utc(parse_utc(props.get("startDateTime"), source)),
        "last_modified_utc": format_utc(parse_utc(props.get("lastModifiedDateTime"), source)),
        "os_type": text(props.get("osType"), source, 64),
        "counts": {
            "security": sec_count,
            "critical": crit_count,
            "update_rollup": rollup_count,
            "definition": def_count,
            "updates": upd_count,
            "feature_pack": fp_count,
            "service_pack": sp_count,
            "tools": tools_count,
            "other": other_count,
            "security_or_critical": sec_count + crit_count,
            "actionable_non_definition": sec_count + crit_count + rollup_count + upd_count + fp_count + sp_count,
            "total": sec_count + crit_count + rollup_count + def_count + upd_count + fp_count + sp_count + tools_count + other_count,
        },
        "configuration_status": {
            "assessment_mode_status": text(assess_conf.get("status"), source, 64),
            "patch_mode_status": text(patch_conf.get("status"), source, 64),
            "vm_guest_patch_readiness": text(readiness_conf.get("detectedVMGuestPatchSupportState"), source, 64),
            "last_modified_utc": format_utc(parse_utc(conf.get("lastModifiedDateTime") or conf.get("lastModifiedTime"), source)),
        },
        "error_code": text(err.get("code"), source, 128),
        "error_message": text(err.get("message"), source, 2048),
        "hotpatch": None if hotpatch is None else {
            "enablement_status": text(hotpatch.get("hotpatchEnablementStatus"), source, 64),
            "readiness_status": text(hotpatch.get("hotpatchReadinessStatus"), source, 64),
            "last_refreshed_utc": format_utc(parse_utc(hotpatch.get("lastRefreshedTime"), source)),
            "error_code": text(hotpatch_err.get("code"), source, 128),
            "detail_codes": hotpatch_detail_codes,
            "detail_messages": hotpatch_detail_msgs,
            "error_message": hotpatch_msg,
            "log_path": hotpatch_log_path,
        },
        "observed_at": reference_utc,
    }


def normalize_pending_patch(row, subscription_id, reference_utc):
    source = "arg_software_patches_pending"
    rid = text(row.get("id"), source, 2048)
    if not rid or not rid.lower().startswith("/subscriptions/" + subscription_id.lower() + "/"):
        raise EvidenceError("scope_mismatch", "Pending software patch ID is outside the configured subscription.", source)
    machine_id = parent_machine_id(rid, source)
    props = obj(row.get("properties") or {}, source)
    raw_class = props.get("classifications")
    classifications = [
        text(item, source, 64)
        for item in (raw_class if isinstance(raw_class, list) else [])
        if item is not None
    ]
    primary_class = classifications[0] if classifications else "Other"
    return {
        "id": rid.lower(),
        "resource_id": rid,
        "record_kind": "pending_assessment_patch",
        "machine_id": machine_id,
        "machine_name": machine_name_from_id(machine_id),
        "patch_id": text(props.get("patchId") or row.get("name"), source, 256),
        "patch_name": text(props.get("patchName") or row.get("name"), source, 512) or "UnknownPatch",
        "kb_id": text(props.get("kbId"), source, 64) or "",
        "version": text(props.get("version"), source, 128) or "",
        "classifications": classifications,
        "primary_classification": primary_class,
        "msrc_severity": text(props.get("msrcSeverity"), source, 64) or "Unspecified",
        "reboot_behavior": text(props.get("rebootBehavior"), source, 64) or "Unknown",
        "installation_state": "PendingAssessment",
        "published_utc": format_utc(parse_utc(props.get("publishedDateTime"), source)),
        "last_modified_utc": format_utc(parse_utc(props.get("lastModifiedDateTime"), source)),
        "observed_at": reference_utc,
    }


def normalize_installation(row, subscription_id, reference_utc):
    source = "arg_patch_installations"
    rid = text(row.get("id"), source, 2048)
    if not rid or not rid.lower().startswith("/subscriptions/" + subscription_id.lower() + "/"):
        raise EvidenceError("scope_mismatch", "Patch installation ID is outside the configured subscription.", source)
    machine_id = parent_machine_id(rid, source)
    props = obj(row.get("properties") or {}, source)
    err = props.get("errorDetails") if isinstance(props.get("errorDetails"), dict) else {}
    return {
        "id": rid.lower(),
        "resource_id": rid,
        "run_id": text(row.get("name") or props.get("installationActivityId"), source, 128),
        "machine_id": machine_id,
        "machine_name": machine_name_from_id(machine_id),
        "status": text(props.get("status"), source, 64) or "Unknown",
        "start_utc": format_utc(parse_utc(props.get("startDateTime"), source)),
        "last_modified_utc": format_utc(parse_utc(props.get("lastModifiedDateTime"), source)),
        "installed_patch_count": integer(props.get("installedPatchCount"), source, 0),
        "failed_patch_count": integer(props.get("failedPatchCount"), source, 0),
        "pending_patch_count": integer(props.get("pendingPatchCount"), source, 0),
        "not_selected_patch_count": integer(props.get("notSelectedPatchCount"), source, 0),
        "excluded_patch_count": integer(props.get("excludedPatchCount"), source, 0),
        "maintenance_window_exceeded": bool(boolean(props.get("maintenanceWindowExceeded"), source)),
        "reboot_status": text(props.get("rebootStatus"), source, 64) or "Unknown",
        "maintenance_run_id": text(props.get("maintenanceRunId"), source, 2048),
        "started_by": text(props.get("startedBy"), source, 128),
        "os_type": text(props.get("osType"), source, 64),
        "error_code": text(err.get("code"), source, 128),
        "error_message": text(err.get("message"), source, 2048),
        "observed_at": reference_utc,
    }


def normalize_installed_patch(row, subscription_id, reference_utc):
    source = "arg_software_patches_installed"
    rid = text(row.get("id"), source, 2048)
    if not rid or not rid.lower().startswith("/subscriptions/" + subscription_id.lower() + "/"):
        raise EvidenceError("scope_mismatch", "Installed software patch ID is outside the configured subscription.", source)
    machine_id = parent_machine_id(rid, source)
    parts = rid.split("/")
    install_run_id = ""
    for idx, part in enumerate(parts):
        if part.lower() == "patchinstallationresults" and idx + 1 < len(parts):
            install_run_id = parts[idx + 1]
            break
    props = obj(row.get("properties") or {}, source)
    raw_class = props.get("classifications")
    classifications = [
        text(item, source, 64)
        for item in (raw_class if isinstance(raw_class, list) else [])
        if item is not None
    ]
    primary_class = classifications[0] if classifications else "Other"
    return {
        "id": rid.lower(),
        "resource_id": rid,
        "record_kind": "installation_run_patch",
        "installation_run_id": install_run_id,
        "machine_id": machine_id,
        "machine_name": machine_name_from_id(machine_id),
        "patch_id": text(props.get("patchId") or row.get("name"), source, 256),
        "patch_name": text(props.get("patchName") or row.get("name"), source, 512) or "UnknownPatch",
        "kb_id": text(props.get("kbId"), source, 64) or "",
        "version": text(props.get("version"), source, 128) or "",
        "classifications": classifications,
        "primary_classification": primary_class,
        "installation_state": text(props.get("installationState"), source, 64) or "Unknown",
        "reboot_behavior": text(props.get("rebootBehavior"), source, 64) or "Unknown",
        "reboot_required": boolean(props.get("rebootRequired"), source),
        "published_utc": format_utc(parse_utc(props.get("publishedDateTime"), source)),
        "last_modified_utc": format_utc(parse_utc(props.get("lastModifiedDateTime"), source)),
        "observed_at": reference_utc,
    }


def normalize_maintenance_row(row, subscription_id, reference_utc):
    source = "arg_maintenance_cycles"
    rid = text(row.get("id"), source, 2048)
    if not rid or not rid.lower().startswith("/subscriptions/" + subscription_id.lower() + "/"):
        raise EvidenceError("scope_mismatch", "Maintenance resource ID is outside the configured subscription.", source)
    rtype = (text(row.get("type"), source, 128) or "").lower()
    props = obj(row.get("properties") or {}, source)
    target_resource_id = text(props.get("resourceId"), source, 2048)
    machine_id = (target_resource_id or parent_machine_id(rid, source)).lower()
    if "/providers/microsoft.maintenance/" in machine_id:
        machine_id = ""
    maint_conf_id = text(props.get("maintenanceConfigurationId"), source, 2048)
    maint_conf_name = machine_name_from_id(maint_conf_id) if maint_conf_id else ""
    start_utc = format_utc(parse_utc(props.get("startDateTime"), source))
    end_utc = format_utc(parse_utc(props.get("endDateTime"), source))
    status = text(props.get("status"), source, 64) or ("Assigned" if rtype.endswith("configurationassignments") else "Unknown")
    correlation_id = text(props.get("correlationId"), source, 2048)
    error_message = text(props.get("errorMessage"), source, 2048)

    maint_conf_obj = props.get("maintenanceConfiguration") if isinstance(props.get("maintenanceConfiguration"), dict) else {}
    maint_win_obj = pick(maint_conf_obj, "properties", "maintenanceWindow")
    maint_win_obj = maint_win_obj if isinstance(maint_win_obj, dict) else {}
    conf_tags = tags_map(maint_conf_obj.get("tags"), source)

    return {
        "id": rid.lower(),
        "resource_id": rid,
        "name": text(row.get("name"), source, 256),
        "type": rtype,
        "resource_group": text(row.get("resourceGroup"), source, 128) or "",
        "location": text(row.get("location"), source, 128) or "",
        "machine_id": machine_id,
        "machine_name": machine_name_from_id(machine_id) if machine_id else "",
        "status": status,
        "correlation_id": correlation_id,
        "maintenance_configuration_id": maint_conf_id,
        "maintenance_configuration_name": maint_conf_name,
        "maintenance_scope": text(props.get("maintenanceScope") or pick(maint_conf_obj, "properties", "maintenanceScope"), source, 64),
        "start_utc": start_utc,
        "end_utc": end_utc,
        "error_message": error_message,
        "schedule_recur_every": text(maint_win_obj.get("recurEvery"), source, 128),
        "schedule_duration": text(maint_win_obj.get("duration"), source, 64),
        "schedule_time_zone": text(maint_win_obj.get("timeZone"), source, 128),
        "configuration_tags": conf_tags,
        "observed_at": reference_utc,
    }


def normalize_extension(row, subscription_id, reference_utc):
    source = "arg_patch_extensions"
    rid = text(row.get("id"), source, 2048)
    if not rid or not rid.lower().startswith("/subscriptions/" + subscription_id.lower() + "/"):
        raise EvidenceError("scope_mismatch", "Extension resource ID is outside the configured subscription.", source)
    rtype = (text(row.get("type"), source, 128) or "").lower()
    if rtype not in ("microsoft.compute/virtualmachines/extensions", "microsoft.hybridcompute/machines/extensions"):
        raise EvidenceError("invalid_type", "Unexpected extension resource type: " + rtype, source)
    machine_id = parent_machine_id(rid, source)
    props = obj(row.get("properties") or {}, source)
    if "settings" in props or "protectedSettings" in props:
        raise EvidenceError("sensitive_extension_settings_forbidden", "Extension settings and protectedSettings must never be read or retained.", source)
    publisher = text(props.get("publisher"), source, 256) or ""
    ext_type = text(props.get("type"), source, 256) or text(row.get("name"), source, 256) or ""
    is_patch_ext = any(
        token in (publisher + "." + ext_type).lower()
        for token in ("patch", "omsagent", "changetracking", "guestconfiguration")
    )
    return {
        "id": rid.lower(),
        "resource_id": rid,
        "name": text(row.get("name"), source, 256) or ext_type,
        "type": rtype,
        "hosting": "arc" if rtype.startswith("microsoft.hybridcompute/") else "azure",
        "machine_id": machine_id,
        "machine_name": machine_name_from_id(machine_id),
        "resource_group": text(row.get("resourceGroup"), source, 128) or "",
        "location": text(row.get("location"), source, 128) or "",
        "publisher": publisher,
        "extension_type": ext_type,
        "type_handler_version": text(props.get("typeHandlerVersion"), source, 64),
        "provisioning_state": text(props.get("provisioningState"), source, 64) or "Unknown",
        "auto_upgrade_minor_version": boolean(props.get("autoUpgradeMinorVersion"), source),
        "enable_automatic_upgrade": boolean(props.get("enableAutomaticUpgrade"), source),
        "is_patch_related": is_patch_ext,
        "observed_at": reference_utc,
    }


def in_window(timestamp_utc, win_start_dt, win_end_dt):
    dt = parse_utc(timestamp_utc)
    if dt is None:
        return True
    return win_start_dt <= dt <= win_end_dt


def investigate_machines(raw, window, reference_utc):
    win_start_dt = parse_utc(window["start_utc"], "window", required=True)
    win_end_dt = parse_utc(window["end_utc"], "window", required=True)

    machines_by_id = {m["id"]: dict(m) for m in raw["machines"]}
    assessments_by_machine = {}
    for ass in raw["assessments"]:
        prev = assessments_by_machine.get(ass["machine_id"])
        if prev is None or (ass.get("last_modified_utc") or "") >= (prev.get("last_modified_utc") or ""):
            assessments_by_machine[ass["machine_id"]] = ass

    pending_by_machine = {mid: [] for mid in machines_by_id}
    for patch in raw["software_patches_pending"]:
        pending_by_machine.setdefault(patch["machine_id"], []).append(patch)

    installs_by_machine = {mid: [] for mid in machines_by_id}
    window_installations = []
    for inst in raw["installations"]:
        if in_window(inst.get("start_utc") or inst.get("last_modified_utc"), win_start_dt, win_end_dt):
            window_installations.append(inst)
            installs_by_machine.setdefault(inst["machine_id"], []).append(inst)

    installed_patches_by_machine = {mid: [] for mid in machines_by_id}
    window_installed_patches = []
    for sp in raw["software_patches_installed"]:
        if in_window(sp.get("last_modified_utc"), win_start_dt, win_end_dt):
            window_installed_patches.append(sp)
            installed_patches_by_machine.setdefault(sp["machine_id"], []).append(sp)

    cycles_by_machine = {mid: [] for mid in machines_by_id}
    assignments_by_machine = {mid: [] for mid in machines_by_id}
    config_Catalog_runs = []
    window_cycles = []
    for mrow in raw["maintenance_cycles"]:
        if mrow["type"] == "microsoft.maintenance/configurationassignments":
            if mrow["machine_id"]:
                assignments_by_machine.setdefault(mrow["machine_id"], []).append(mrow)
            window_cycles.append(mrow)
        elif mrow["type"] == "microsoft.maintenance/maintenanceconfigurations/applyupdates":
            if in_window(mrow.get("start_utc") or mrow.get("end_utc"), win_start_dt, win_end_dt):
                config_Catalog_runs.append(mrow)
                window_cycles.append(mrow)
        else:
            if in_window(mrow.get("start_utc") or mrow.get("end_utc"), win_start_dt, win_end_dt):
                window_cycles.append(mrow)
                if mrow["machine_id"]:
                    cycles_by_machine.setdefault(mrow["machine_id"], []).append(mrow)

    extensions_by_machine = {mid: [] for mid in machines_by_id}
    for ext in raw["extensions"]:
        extensions_by_machine.setdefault(ext["machine_id"], []).append(ext)

    investigated_machines = []
    failure_records = []

    for mid in sorted(machines_by_id):
        m = machines_by_id[mid]
        ass = assessments_by_machine.get(mid)
        pend = pending_by_machine.get(mid, [])
        insts = sorted(installs_by_machine.get(mid, []), key=lambda x: x.get("start_utc") or "", reverse=True)
        inst_patches = installed_patches_by_machine.get(mid, [])
        m_cycles = sorted(cycles_by_machine.get(mid, []), key=lambda x: x.get("start_utc") or "", reverse=True)
        m_assigns = assignments_by_machine.get(mid, [])
        m_exts = sorted(extensions_by_machine.get(mid, []), key=lambda x: x["name"].lower())

        apply_cycles = [c for c in m_cycles if c["type"] == "microsoft.maintenance/applyupdates"]
        unresponsive_cycles = [c for c in apply_cycles if c["status"] == "ShutdownOrUnresponsive"]
        applied_cycles = [c for c in apply_cycles if c["status"] == "UpdateSuccessfullyApplied"]
        failed_cycles = [
            c for c in apply_cycles
            if c["status"] not in ("UpdateSuccessfullyApplied", "ShutdownOrUnresponsive", "Completed")
        ]

        failed_insts = [
            i for i in insts
            if i["status"] in ("Failed", "Warning")
            or i["failed_patch_count"] > 0
            or i["maintenance_window_exceeded"]
        ]
        succeeded_insts = [i for i in insts if i["status"] == "Succeeded"]

        failed_exts = [e for e in m_exts if e["provisioning_state"].lower() not in ("succeeded", "creating", "updating")]
        sec_patches = [
            p for p in pend
            if any(c.lower() in ("security", "critical") for c in p["classifications"])
        ]
        rollup_patches = [
            p for p in pend
            if any("rollup" in c.lower() for c in p["classifications"])
        ]

        counts = ass["counts"] if ass else {
            "security": len(sec_patches),
            "critical": 0,
            "update_rollup": len(rollup_patches),
            "definition": 0,
            "updates": 0,
            "other": len(pend),
            "security_or_critical": len(sec_patches),
            "actionable_non_definition": len(sec_patches) + len(rollup_patches),
            "total": len(pend),
        }
        readiness = pick(ass, "configuration_status", "vm_guest_patch_readiness") or "NotAssessed"
        patch_mode_status = pick(ass, "configuration_status", "patch_mode_status") or "Unknown"
        hotpatch = pick(ass, "hotpatch")

        detected_issues = []

        # 1. Arc agent expired or disconnected
        if m["hosting"] == "arc" and (m.get("arc_status") or "").lower() in ("expired", "disconnected", "error"):
            detected_issues.append({
                "failure_category": "arc_agent_expired_or_disconnected",
                "severity": "critical",
                "investigation_headline": (
                    "Azure Connected Machine agent (azcmagent) in state '" + str(m.get("arc_status"))
                    + "' since " + str(m.get("last_status_change_utc") or "an unknown date")
                    + " (version " + str(m.get("agent_version") or "unknown") + ")."
                ),
                "root_cause_evidence": (
                    "The hybrid Azure Arc server sends no heartbeat to the Microsoft.HybridCompute control plane. "
                    "With the agent in state '" + str(m.get("arc_status")) + "', Azure Update Manager cannot "
                    "deploy the assessment extension or run scheduled maintenance windows."
                ),
                "log_or_source_reference": (
                    "arg_compute_machines :: " + m["resource_id"]
                    + " :: properties.status=" + str(m.get("arc_status"))
                    + ", lastStatusChange=" + str(m.get("last_status_change_utc"))
                ),
                "recommended_human_action": (
                    "Check whether the physical or virtual server is still in service or should be removed from Azure Arc. "
                    "If the host is still in service, reconnect it or renew the azcmagent certificate ('azcmagent check' / 'azcmagent connect') "
                    "and update the agent before the next monthly cycle."
                ),
            })

        # 2. Maintenance window unresponsive or installation failure
        if unresponsive_cycles or failed_cycles or failed_insts:
            latest_unresp = unresponsive_cycles[0] if unresponsive_cycles else (failed_cycles[0] if failed_cycles else None)
            latest_inst_fail = failed_insts[0] if failed_insts else None
            if latest_unresp:
                corr = latest_unresp.get("correlation_id") or latest_unresp["resource_id"]
                conf_name = latest_unresp.get("maintenance_configuration_name") or "assigned configuration"
                detected_issues.append({
                    "failure_category": "maintenance_window_unresponsive",
                    "severity": "critical",
                    "investigation_headline": (
                        str(len(unresponsive_cycles)) + " of " + str(len(apply_cycles))
                        + " maintenance window runs ended in 'ShutdownOrUnresponsive' ("
                        + str(len(applied_cycles)) + " 'UpdateSuccessfullyApplied')."
                    ),
                    "root_cause_evidence": (
                        "Azure Update Manager recorded status 'ShutdownOrUnresponsive' for configuration '" + conf_name
                        + "' (last failed cycle: " + str(latest_unresp.get("start_utc")) + " -> "
                        + str(latest_unresp.get("end_utc")) + "). The machine was stopped or deallocated, or the guest "
                        "agent did not respond during the scheduled window. Successful installation runs while "
                        "it was running: " + str(len(succeeded_insts)) + "."
                    ),
                    "log_or_source_reference": (
                        "arg_maintenance_cycles :: " + latest_unresp["resource_id"]
                        + " :: correlationId=" + str(corr)
                    ),
                    "recommended_human_action": (
                        "Align the schedule of the maintenance configuration ('" + conf_name + "') with the hours when "
                        "the machine is actually running, or add a pre-maintenance event that starts it before the patching window."
                    ),
                })
            elif latest_inst_fail:
                detected_issues.append({
                    "failure_category": "maintenance_window_unresponsive",
                    "severity": "critical",
                    "investigation_headline": (
                        "Patch installation run failed (" + str(latest_inst_fail["status"])
                        + ", failed patches=" + str(latest_inst_fail["failed_patch_count"])
                        + ", window exceeded=" + str(latest_inst_fail["maintenance_window_exceeded"]) + ")."
                    ),
                    "root_cause_evidence": (
                        "The patchInstallationResults run that started at " + str(latest_inst_fail.get("start_utc"))
                        + " reported code '" + str(latest_inst_fail.get("error_code") or "Error")
                        + "': " + str(latest_inst_fail.get("error_message") or "Failure or maintenance window exceeded.")
                    ),
                    "log_or_source_reference": "arg_patch_installations :: " + latest_inst_fail["resource_id"],
                    "recommended_human_action": (
                        "Extend the maintenance window and review the packages with installationState='Failed' "
                        "in patchinstallationresources."
                    ),
                })

        # 3. Assessment stuck InProgress or readiness UnableToDetermine
        if ass and (
            ass["status"] in ("InProgress", "Failed")
            or readiness in ("UnableToDetermine", "Unsupported")
        ):
            sec_names = ", ".join(
                (p["patch_name"] + (" (" + p["version"] + ")" if p["version"] else ""))
                for p in sec_patches[:5]
            ) or "not listed individually"
            detected_issues.append({
                "failure_category": "assessment_stuck_or_readiness_undetermined",
                "severity": "high",
                "investigation_headline": (
                    "Patch assessment in state '" + str(ass["status"])
                    + "' and guest patch support '" + str(readiness) + "'; pending security updates: "
                    + str(counts["security_or_critical"]) + " of "
                    + str(counts["total"]) + " pending packages."
                ),
                "root_cause_evidence": (
                    "patchassessmentresources reports status='" + str(ass["status"])
                    + "', detectedVMGuestPatchSupportState='" + str(readiness)
                    + "' and patchModeConfiguration.status='" + str(patch_mode_status)
                    + "' (configuration last modified: "
                    + str(pick(ass, "configuration_status", "last_modified_utc") or ass.get("last_modified_utc"))
                    + "). Pending Security patches: " + str(counts["security"]) + " (" + sec_names
                    + "); other packages with no active installation window: " + str(counts["other"]) + "."
                ),
                "log_or_source_reference": (
                    "arg_patch_assessments :: " + ass["resource_id"]
                    + " :: vmGuestPatchReadiness=" + str(readiness)
                ),
                "recommended_human_action": (
                    "Unblock the apt/dpkg process or the package manager on the Linux Arc host, confirm that "
                    "Azure Update Manager supports the distribution (Ubuntu 24.04 + azcmagent) and assign the machine to an "
                    "active maintenance configuration."
                ),
            })

        # 4. Hotpatch or guest patch/management extension error
        has_hotpatch_err = bool(
            hotpatch
            and (
                (hotpatch.get("error_code") or "").lower() not in ("", "success", "0")
                or hotpatch.get("detail_codes")
            )
        )
        if has_hotpatch_err or failed_exts:
            if has_hotpatch_err:
                detail_code = (hotpatch.get("detail_codes") or [hotpatch.get("error_code")])[0]
                detail_msg = (hotpatch.get("detail_messages") or [hotpatch.get("error_message")])[0]
                log_ref = hotpatch.get("log_path") or (ass["resource_id"] if ass else m["resource_id"])
                detected_issues.append({
                    "failure_category": "hotpatch_or_patch_extension_error",
                    "severity": "high",
                    "investigation_headline": (
                        "Hotpatch readiness error '" + str(detail_code)
                        + "' in WindowsPatchExtension (hotpatchEnablementStatus='"
                        + str(hotpatch.get("enablement_status")) + "')."
                    ),
                    "root_cause_evidence": (
                        "The hotpatchStatus object in patchassessmentresources reports code '" + str(detail_code)
                        + "' (" + str(detail_msg) + "). In addition, package '"
                        + ", ".join(p["patch_name"] for p in pend if "RollUp" in (p["primary_classification"] or ""))
                        + "' stayed 'NotSelected' during the scheduled runs because its classification was not "
                        "selected in the window."
                    ),
                    "log_or_source_reference": str(log_ref),
                    "recommended_human_action": (
                        "Enable hotpatching on the Windows Server 2025 VM if patching without reboots is required, or skip "
                        "the hotpatch check and add the 'UpdateRollUp' classification to the maintenance configuration "
                        "so that KB890830 is installed. Review the local log " + str(log_ref) + " only if the extension code persists."
                    ),
                })
            if failed_exts:
                ext_summary = ", ".join(e["name"] + " (" + e["provisioning_state"] + ")" for e in failed_exts)
                detected_issues.append({
                    "failure_category": "hotpatch_or_patch_extension_error",
                    "severity": "high",
                    "investigation_headline": (
                        str(len(failed_exts)) + " of this machine's extensions failed: " + ext_summary + "."
                    ),
                    "root_cause_evidence": (
                        "arg_patch_extensions found provisioningState='Failed' in " + ext_summary
                        + " on machine '" + m["name"] + "' (power state: " + str(m.get("power_state") or "unknown") + ")."
                    ),
                    "log_or_source_reference": "arg_patch_extensions :: " + failed_exts[0]["resource_id"],
                    "recommended_human_action": (
                        "Start the virtual machine during a controlled window and reprovision or update every extension "
                        "in the Failed state (" + ext_summary + ")."
                    ),
                })

        # 5. Pending security/critical/rollup patches without scheduled maintenance execution
        if ass and ass["status"] == "Succeeded" and (counts["security_or_critical"] > 0 or counts["update_rollup"] > 0) and not m_assigns and not insts:
            kb_list = [
                (p["kb_id"] and ("KB" + p["kb_id"]) or p["patch_name"])
                for p in pend
                if any(c.lower() in ("security", "critical", "updaterollup") for c in p["classifications"])
            ]
            kb_text = " (" + ", ".join(kb_list[:6]) + ")" if kb_list else ""
            detected_issues.append({
                "failure_category": "pending_security_patches_unscheduled",
                "severity": "medium",
                "investigation_headline": (
                    str(counts["security"]) + " Security and " + str(counts["update_rollup"])
                    + " UpdateRollUp patches pending" + kb_text
                    + ", with no maintenance configuration assigned and no runs in the period."
                ),
                "root_cause_evidence": (
                    "The automatic assessment on '" + m["name"] + "' completed successfully on "
                    + str(ass.get("last_modified_utc")) + "; available updates: " + str(counts["total"])
                    + " (" + str(counts["security"]) + " Security, "
                    + str(counts["update_rollup"]) + " UpdateRollUp, " + str(counts["updates"])
                    + " Updates, " + str(counts["definition"]) + " Definition), but patchModeConfiguration.status is '"
                    + str(patch_mode_status) + "' and there are 0 assignments in microsoft.maintenance/configurationassignments."
                ),
                "log_or_source_reference": "arg_patch_assessments :: " + ass["resource_id"],
                "recommended_human_action": (
                    "Create the microsoft.maintenance/configurationAssignments link to the approved maintenance "
                    "window to install the pending KBs" + kb_text + "."
                ),
            })

        # 6. Unassessed / no Update Manager telemetry
        if ass is None and not insts and not apply_cycles:
            if not detected_issues:
                detected_issues.append({
                    "failure_category": "unassessed_no_update_manager_telemetry",
                    "severity": "low",
                    "investigation_headline": (
                        "No assessment or installation records in Azure Update Manager (state='"
                        + str(m.get("power_state") or m.get("arc_status") or "Unknown")
                        + "', assessmentMode='" + str(m.get("assessment_mode") or "ImageDefault") + "')."
                    ),
                    "root_cause_evidence": (
                        "Machine '" + m["name"] + "' is in the compute inventory (" + m["type"]
                        + "), but has no record in patchassessmentresources or patchinstallationresources. "
                        "Its current state is '" + str(m.get("power_state") or m.get("arc_status") or "Unknown")
                        + "' with assessmentMode='" + str(m.get("assessment_mode") or "None")
                        + "' and patchMode='" + str(m.get("patch_mode") or "None") + "'."
                    ),
                    "log_or_source_reference": "arg_compute_machines :: " + m["resource_id"],
                    "recommended_human_action": (
                        "If the VM is in operational scope, set assessmentMode='AutomaticByPlatform' "
                        "and schedule periodic assessments while the instance is running."
                    ),
                })

        # Determine primary diagnostic vs healthy state
        if detected_issues:
            # Sort issues by severity order so the most critical operational blocker leads
            detected_issues.sort(key=lambda item: SEVERITY_ORDER.get(item["severity"], 9))
            primary = detected_issues[0]
            matched_cats = list(dict.fromkeys(item["failure_category"] for item in detected_issues))
            for idx, issue in enumerate(detected_issues, start=1):
                failure_records.append({
                    "failure_id": "FAIL-" + hashlib.sha256((mid + ":" + issue["failure_category"] + ":" + str(idx)).encode("utf-8")).hexdigest()[:10],
                    "machine_id": mid,
                    "machine_name": m["name"],
                    "resource_group": m["resource_group"],
                    "hosting": m["hosting"],
                    "os_type": m["os_type"],
                    "os_name": m["os_name"],
                    "power_or_arc_state": m.get("arc_status") if m["hosting"] == "arc" else (m.get("power_state") or "Unknown"),
                    "failure_category": issue["failure_category"],
                    "failure_category_label": CATEGORY_LABELS[issue["failure_category"]],
                    "severity": issue["severity"],
                    "severity_label": SEVERITY_LABELS[issue["severity"]],
                    "investigation_headline": issue["investigation_headline"],
                    "root_cause_evidence": issue["root_cause_evidence"],
                    "log_or_source_reference": issue["log_or_source_reference"],
                    "recommended_human_action": issue["recommended_human_action"],
                    "pending_security_count": counts["security_or_critical"],
                    "pending_rollup_count": counts["update_rollup"],
                    "pending_total_count": counts["total"],
                    "unresponsive_cycles_count": len(unresponsive_cycles),
                    "succeeded_cycles_count": len(applied_cycles),
                    "observed_at": reference_utc,
                })
        else:
            primary = {
                "failure_category": "healthy",
                "severity": "info",
                "investigation_headline": "Assessment and patching cycles completed with no errors and no pending critical patches.",
                "root_cause_evidence": (
                    "Assessment in state 'Succeeded' with no pending reboot and no errors in extensions or maintenance windows."
                ),
                "log_or_source_reference": (ass["resource_id"] if ass else m["resource_id"]),
                "recommended_human_action": "Keep the scheduled cadence in Azure Update Manager.",
            }
            matched_cats = ["healthy"]

        latest_inst = insts[0] if insts else None
        investigated_machines.append({
            **m,
            "power_or_arc_state": m.get("arc_status") if m["hosting"] == "arc" else (m.get("power_state") or "Unknown"),
            "assessment_status": ass["status"] if ass else "NoAssessment",
            "assessment_last_modified_utc": ass.get("last_modified_utc") if ass else None,
            "reboot_pending": ass.get("reboot_pending") if ass else None,
            "vm_guest_patch_readiness": readiness,
            "patch_mode_status": patch_mode_status,
            "pending_counts": counts,
            "pending_security_patches": [
                {
                    "patch_name": p["patch_name"],
                    "kb_id": p["kb_id"],
                    "version": p["version"],
                    "classifications": p["classifications"],
                    "msrc_severity": p["msrc_severity"],
                    "reboot_behavior": p["reboot_behavior"],
                }
                for p in (sec_patches + rollup_patches)[:15]
            ],
            "maintenance_configuration_assignments": [
                c["maintenance_configuration_name"] or c["maintenance_configuration_id"]
                for c in m_assigns
            ],
            "maintenance_cycles_summary": {
                "total": len(apply_cycles),
                "succeeded": len(applied_cycles),
                "unresponsive": len(unresponsive_cycles),
                "other": len(failed_cycles),
            },
            "installations_summary": {
                "runs_in_window": len(insts),
                "succeeded_runs": len(succeeded_insts),
                "failed_runs": len(failed_insts),
                "installed_patches_total": sum(i["installed_patch_count"] for i in insts),
                "not_selected_patches_total": sum(i["not_selected_patch_count"] for i in insts),
                "last_installation_utc": latest_inst.get("last_modified_utc") if latest_inst else None,
                "last_installation_status": latest_inst.get("status") if latest_inst else None,
                "last_reboot_status": latest_inst.get("reboot_status") if latest_inst else None,
            },
            "hotpatch": hotpatch,
            "extensions_count": len(m_exts),
            "failed_extensions_count": len(failed_exts),
            "extensions": [
                {
                    "name": e["name"],
                    "publisher": e["publisher"],
                    "extension_type": e["extension_type"],
                    "version": e["type_handler_version"],
                    "provisioning_state": e["provisioning_state"],
                    "enable_automatic_upgrade": e["enable_automatic_upgrade"],
                }
                for e in m_exts
            ],
            "failure_category": primary["failure_category"],
            "failure_category_label": CATEGORY_LABELS[primary["failure_category"]],
            "matched_categories": matched_cats,
            "severity": primary["severity"],
            "severity_label": SEVERITY_LABELS[primary["severity"]],
            "investigation_headline": primary["investigation_headline"],
            "root_cause_evidence": primary["root_cause_evidence"],
            "log_or_source_reference": primary["log_or_source_reference"],
            "recommended_human_action": primary["recommended_human_action"],
            "all_detected_issues": detected_issues,
        })

    investigated_machines.sort(
        key=lambda item: (
            SEVERITY_ORDER.get(item["severity"], 9),
            item["hosting"],
            item["name"].lower(),
        )
    )
    failure_records.sort(
        key=lambda item: (
            SEVERITY_ORDER.get(item["severity"], 9),
            item["machine_name"].lower(),
            item["failure_category"],
        )
    )
    window_installations.sort(key=lambda item: item.get("start_utc") or "", reverse=True)
    window_cycles.sort(key=lambda item: item.get("start_utc") or item.get("id") or "", reverse=True)

    return {
        "machines": investigated_machines,
        "failures": failure_records,
        "window_installations": window_installations,
        "window_installed_patches": window_installed_patches,
        "window_cycles": window_cycles,
    }


def build_actions(failures):
    grouped = {}
    for item in failures:
        cat = item["failure_category"]
        if cat not in grouped:
            grouped[cat] = {
                "action_id": "ACT-" + cat.upper()[:24],
                "failure_category": cat,
                "failure_category_label": item["failure_category_label"],
                "severity": item["severity"],
                "severity_label": item["severity_label"],
                "affected_machines_count": 0,
                "affected_machines": [],
                "investigation_summary": item["investigation_headline"],
                "recommended_human_action": item["recommended_human_action"],
                "sample_source_reference": item["log_or_source_reference"],
            }
        entry = grouped[cat]
        if item["machine_name"] not in entry["affected_machines"]:
            entry["affected_machines"].append(item["machine_name"])
            entry["affected_machines_count"] = len(entry["affected_machines"])
    actions = list(grouped.values())
    actions.sort(key=lambda a: (SEVERITY_ORDER.get(a["severity"], 9), -a["affected_machines_count"], a["failure_category"]))
    return actions


def collect_live(config, period, reference_utc, deadline=None):
    identity = Identity(config)
    try:
        reader = ArgReader(identity, config, deadline=deadline)
        queries = arg_queries()
        raw_tables = {}
        sources = []
        for sid in SOURCE_IDS:
            rows, receipt = reader.query_table(sid, queries[sid], reference_utc)
            raw_tables[sid] = rows
            sources.append(receipt)
        if all(s["status"] in ("denied", "error") for s in sources):
            first_err = sources[0]["errors"][0] if sources[0]["errors"] else {"code": "collection_failed", "http_status": None}
            raise EvidenceError(
                first_err["code"],
                "All Azure Resource Graph queries failed; no synthetic or empty patching report was produced.",
                "arg_compute_machines",
                first_err.get("http_status"),
            )
        return normalize_collected(raw_tables, sources, config, period, reference_utc)
    finally:
        identity.close()


def normalize_collected(raw_tables, sources, config, period, reference_utc):
    sub_id = config["subscription_id"]
    machines = [normalize_machine(r, sub_id, reference_utc) for r in raw_tables.get("arg_compute_machines", [])]
    assessments = [normalize_assessment(r, sub_id, reference_utc) for r in raw_tables.get("arg_patch_assessments", [])]
    pending_patches = [normalize_pending_patch(r, sub_id, reference_utc) for r in raw_tables.get("arg_software_patches_pending", [])]
    installations = [normalize_installation(r, sub_id, reference_utc) for r in raw_tables.get("arg_patch_installations", [])]
    installed_patches = [normalize_installed_patch(r, sub_id, reference_utc) for r in raw_tables.get("arg_software_patches_installed", [])]
    maintenance_cycles = [normalize_maintenance_row(r, sub_id, reference_utc) for r in raw_tables.get("arg_maintenance_cycles", [])]
    extensions = [normalize_extension(r, sub_id, reference_utc) for r in raw_tables.get("arg_patch_extensions", [])]
    return {
        "subscription_id": sub_id,
        "period": period,
        "machines": machines,
        "assessments": assessments,
        "software_patches_pending": pending_patches,
        "installations": installations,
        "software_patches_installed": installed_patches,
        "maintenance_cycles": maintenance_cycles,
        "extensions": extensions,
        "sources": sources,
    }


def finish_snapshot(raw, reference_utc, provenance="LIVE", environment="PRODUCTION"):
    if provenance not in ("LIVE", "SIMULATED"):
        raise EvidenceError("invalid_provenance", "provenance must be LIVE or SIMULATED.")
    period = raw.get("period", "last_30d")
    window = window_for(period, reference_utc)
    inv = investigate_machines(raw, window, reference_utc)
    machines = inv["machines"]
    failures = inv["failures"]
    win_installs = inv["window_installations"]
    win_installed_patches = inv["window_installed_patches"]
    win_cycles = inv["window_cycles"]
    actions = build_actions(failures)

    apply_cycles = [c for c in win_cycles if c["type"] == "microsoft.maintenance/applyupdates"]
    config_runs = [c for c in win_cycles if c["type"] == "microsoft.maintenance/maintenanceconfigurations/applyupdates"]
    assign_rows = [c for c in win_cycles if c["type"] == "microsoft.maintenance/configurationassignments"]

    cat_counts = Counter(m["failure_category"] for m in machines)
    sev_counts = Counter(m["severity"] for m in machines)
    hosting_counts = Counter(m["hosting"] for m in machines)

    assessed_machines = [m for m in machines if m["assessment_status"] != "NoAssessment"]
    machines_with_issues = [m for m in machines if m["failure_category"] != "healthy"]

    total_sec_pending = sum(m["pending_counts"]["security_or_critical"] for m in machines)
    total_rollup_pending = sum(m["pending_counts"]["update_rollup"] for m in machines)
    total_pending_all = sum(m["pending_counts"]["total"] for m in machines)

    unresp_count = sum(c["status"] == "ShutdownOrUnresponsive" for c in apply_cycles)
    applied_count = sum(c["status"] == "UpdateSuccessfullyApplied" for c in apply_cycles)

    summary_kpis = {
        "subscription_id": raw["subscription_id"],
        "period": period,
        "window": window,
        "machines_total": len(machines),
        "azure_vms_total": hosting_counts.get("azure", 0),
        "arc_machines_total": hosting_counts.get("arc", 0),
        "assessed_machines_total": len(assessed_machines),
        "unassessed_machines_total": len(machines) - len(assessed_machines),
        "healthy_machines_total": cat_counts.get("healthy", 0),
        "machines_with_blockers_total": len(machines_with_issues),
        "diagnostic_findings_total": len(failures),
        "critical_machines_total": sev_counts.get("critical", 0),
        "high_machines_total": sev_counts.get("high", 0),
        "medium_machines_total": sev_counts.get("medium", 0),
        "low_machines_total": sev_counts.get("low", 0),
        "category_counts": {cat: cat_counts.get(cat, 0) for cat in FAILURE_CATEGORIES if cat != "all"},
        "maintenance_cycles_in_window": len(apply_cycles),
        "maintenance_cycles_succeeded": applied_count,
        "maintenance_cycles_unresponsive": unresp_count,
        "maintenance_config_runs_in_window": len(config_runs),
        "maintenance_assignments_total": len(assign_rows),
        "installation_runs_in_window": len(win_installs),
        "installation_runs_succeeded": sum(i["status"] == "Succeeded" for i in win_installs),
        "installation_runs_failed": sum(i["status"] in ("Failed", "Warning") or i["failed_patch_count"] > 0 for i in win_installs),
        "installed_patches_in_window": sum(p["installation_state"] == "Installed" for p in win_installed_patches),
        "not_selected_patches_in_window": sum(p["installation_state"] == "NotSelected" for p in win_installed_patches),
        "pending_security_or_critical_patches": total_sec_pending,
        "pending_rollup_patches": total_rollup_pending,
        "pending_total_patches": total_pending_all,
        "guest_extensions_total": len(raw["extensions"]),
        "guest_extensions_failed": sum(e["provisioning_state"].lower() not in ("succeeded", "creating", "updating") for e in raw["extensions"]),
    }

    executive_messages = [
        (
            plural(summary_kpis["machines_total"], "machine", "machines") + " in inventory ("
            + plural(summary_kpis["azure_vms_total"], "Azure VM", "Azure VMs") + " and "
            + plural(summary_kpis["arc_machines_total"], "hybrid Azure Arc server", "hybrid Azure Arc servers") + "): "
            + str(summary_kpis["assessed_machines_total"]) + " assessed by Update Manager and "
            + str(summary_kpis["unassessed_machines_total"]) + " with no assessment telemetry."
        ),
        (
            plural(summary_kpis["maintenance_cycles_in_window"], "per-machine maintenance cycle", "per-machine maintenance cycles") + " recorded in the window ("
            + str(applied_count) + " 'UpdateSuccessfullyApplied' versus "
            + str(unresp_count) + " 'ShutdownOrUnresponsive') and "
            + plural(summary_kpis["installation_runs_in_window"], "patchInstallationResults run", "patchInstallationResults runs") + "."
        ),
        (
            plural(cat_counts.get("arc_agent_expired_or_disconnected", 0), "Azure Arc server has", "Azure Arc servers have")
            + " the agent in state 'Expired'/'Disconnected', which blocks assessment and patch deployment."
        ),
        (
            plural(cat_counts.get("assessment_stuck_or_readiness_undetermined", 0), "machine has an assessment", "machines have assessments")
            + " stuck in 'InProgress' with vmGuestPatchReadiness='UnableToDetermine', and "
            + plural(cat_counts.get("pending_security_patches_unscheduled", 0), "server has", "servers have")
            + " pending Security/UpdateRollUp patches with no maintenance window assigned."
        ),
        (
            "Automated root-cause diagnosis generated for " + plural(len(machines), "machine", "machines")
            + " (" + plural(len(failures), "technical finding", "technical findings") + " correlated across ARG, extensions, Hotpatch and maintenance windows), "
            "without signing in to any machine."
        ),
    ]

    all_patches_combined = (
        sorted(
            raw["software_patches_pending"],
            key=lambda p: (
                0 if "Security" in p["classifications"] or "Critical" in p["classifications"] else (1 if "UpdateRollUp" in p["classifications"] else 2),
                p["machine_name"].lower(),
                p["patch_name"].lower(),
            ),
        )
        + sorted(
            win_installed_patches,
            key=lambda p: (p.get("last_modified_utc") or "", p["machine_name"].lower()),
            reverse=True,
        )
    )

    return {
        "schema_version": "1.0",
        "provenance": provenance,
        "environment": environment,
        "reference_utc": reference_utc,
        "subscription_id": raw["subscription_id"],
        "window": window,
        "client": {
            "name": CLIENT_NAME,
            "logo_data_uri": CLIENT_LOGO_DATA_URI,
            "logo_alt": CLIENT_LOGO_ALT,
        },
        "summary": summary_kpis,
        "executive_messages": executive_messages,
        "machines": machines,
        "failures": failures,
        "cycles": {
            "maintenance_cycles": win_cycles,
            "installation_runs": win_installs,
        },
        "patches": {
            "pending": raw["software_patches_pending"],
            "installed_in_window": win_installed_patches,
            "combined": all_patches_combined,
        },
        "extensions": raw["extensions"],
        "actions": actions,
        "sources": raw["sources"],
        "methodology": {
            "read_only": True,
            "scheduled_cadence_cron": "0 8 1 * *",
            "scheduled_cadence_description": "Day 1 of every month at 08:00 UTC (plus on-demand runs after a patching window).",
            "arg_tables": [
                "resources (microsoft.compute/virtualmachines, microsoft.hybridcompute/machines, extensions)",
                "patchassessmentresources (patchAssessmentResults/latest and softwarePatches)",
                "patchinstallationresources (patchInstallationResults and softwarePatches)",
                "maintenanceresources (applyupdates, configurationassignments, maintenanceconfigurations/applyupdates, updates)",
            ],
            "limitations": [
                "100% read-only collection through the Azure Resource Graph API (2022-10-01); the tool never runs guest commands (runCommand) and never starts or stops machines.",
                "Sensitive or private extension configuration blocks are never requested or exported.",
                "Local log paths shown by Azure Update Manager (for example WindowsPatchExtension) come from the error message reported to the ARM control plane.",
            ],
        },
    }


def compact_machine_row(m):
    return {
        "machine_name": m["name"],
        "hosting": m["hosting"],
        "resource_group": m["resource_group"],
        "os_type": m["os_type"],
        "power_or_arc_state": m["power_or_arc_state"],
        "assessment_status": m["assessment_status"],
        "vm_guest_patch_readiness": m["vm_guest_patch_readiness"],
        "pending_security_or_critical": m["pending_counts"]["security_or_critical"],
        "pending_update_rollup": m["pending_counts"]["update_rollup"],
        "pending_total": m["pending_counts"]["total"],
        "cycles_succeeded": m["maintenance_cycles_summary"]["succeeded"],
        "cycles_unresponsive": m["maintenance_cycles_summary"]["unresponsive"],
        "install_runs_in_window": m["installations_summary"]["runs_in_window"],
        "failure_category": m["failure_category"],
        "matched_categories": m["matched_categories"],
        "severity": m["severity"],
        "investigation_headline": m["investigation_headline"],
        "log_or_source_reference": m["log_or_source_reference"],
    }


def compact_failure_row(f):
    return {
        "failure_id": f["failure_id"],
        "machine_name": f["machine_name"],
        "hosting": f["hosting"],
        "resource_group": f["resource_group"],
        "power_or_arc_state": f["power_or_arc_state"],
        "failure_category": f["failure_category"],
        "severity": f["severity"],
        "pending_security_count": f["pending_security_count"],
        "unresponsive_cycles_count": f["unresponsive_cycles_count"],
        "investigation_headline": f["investigation_headline"],
        "log_or_source_reference": f["log_or_source_reference"][:180],
    }


def snapshot_rows(snapshot, view):
    if view == "summary":
        return [snapshot["summary"]]
    if view == "machines":
        return [compact_machine_row(m) for m in snapshot["machines"]]
    if view == "failures":
        return [compact_failure_row(f) for f in snapshot["failures"]]
    if view == "cycles":
        rows = []
        for c in snapshot["cycles"]["maintenance_cycles"]:
            rows.append({
                "record_type": c["type"],
                "machine_name": c["machine_name"],
                "status": c["status"],
                "start_utc": c["start_utc"],
                "end_utc": c["end_utc"],
                "maintenance_configuration_name": c["maintenance_configuration_name"],
                "correlation_id": c["correlation_id"],
                "resource_id": c["resource_id"],
            })
        for i in snapshot["cycles"]["installation_runs"]:
            rows.append({
                "record_type": "patch_installation_run",
                "machine_name": i["machine_name"],
                "status": i["status"],
                "start_utc": i["start_utc"],
                "end_utc": i["last_modified_utc"],
                "installed_patch_count": i["installed_patch_count"],
                "failed_patch_count": i["failed_patch_count"],
                "not_selected_patch_count": i["not_selected_patch_count"],
                "reboot_status": i["reboot_status"],
                "maintenance_run_id": i["maintenance_run_id"],
                "resource_id": i["resource_id"],
            })
        return rows
    if view == "patches":
        return [
            {
                "record_kind": p["record_kind"],
                "machine_name": p["machine_name"],
                "patch_name": p["patch_name"],
                "kb_id": p["kb_id"],
                "version": p["version"],
                "primary_classification": p["primary_classification"],
                "installation_state": p["installation_state"],
                "reboot_behavior": p["reboot_behavior"],
                "last_modified_utc": p["last_modified_utc"],
            }
            for p in snapshot["patches"]["combined"]
        ]
    if view == "extensions":
        return [
            {
                "machine_name": e["machine_name"],
                "hosting": e["hosting"],
                "name": e["name"],
                "publisher": e["publisher"],
                "extension_type": e["extension_type"],
                "type_handler_version": e["type_handler_version"],
                "provisioning_state": e["provisioning_state"],
                "auto_upgrade_minor_version": e["auto_upgrade_minor_version"],
                "enable_automatic_upgrade": e["enable_automatic_upgrade"],
            }
            for e in snapshot["extensions"]
        ]
    if view == "coverage":
        return snapshot["sources"]
    if view == "actions":
        return snapshot["actions"]
    raise EvidenceError("invalid_parameter", "Unsupported view: " + str(view), "parameters")


def collection_disclosure(snapshot):
    return {
        "reference_utc": snapshot["reference_utc"],
        "fresh_collection": True,
        "provenance": snapshot["provenance"],
        "subscription_id": snapshot["subscription_id"],
        "period": snapshot["window"]["period"],
        "window_start_utc": snapshot["window"]["start_utc"],
        "window_end_utc": snapshot["window"]["end_utc"],
        "source_status_counts": dict(Counter(s["status"] for s in snapshot["sources"])),
        "source_total": len(snapshot["sources"]),
        "source_details_view": "coverage",
        "paging_basis": "Local offset in this collection; later calls recollect, not a stable cross-call cursor.",
    }


def response_bytes(document):
    return len(json.dumps(document, ensure_ascii=False, allow_nan=False).encode("utf-8"))


def ensure_response(document):
    if response_bytes(document) > TRANSPORT_BYTES:
        raise EvidenceError("transport_budget_exceeded", "Response exceeds the 3500-byte JSON transport budget.", "transport")
    return document


def query_snapshot(snapshot, params):
    view = params["view"]
    rows = snapshot_rows(snapshot, view)
    machine_by_name = {m["name"].lower(): m for m in snapshot["machines"]}

    def matches(row):
        m_name = (row.get("machine_name") or row.get("name") or "").lower()
        m_obj = machine_by_name.get(m_name)
        if params["machine_name"]:
            target = params["machine_name"].lower()
            if view == "actions":
                if not any(name.lower() == target for name in row.get("affected_machines", [])):
                    return False
            elif m_name != target:
                return False
        if params["hosting"] != "all":
            row_hosting = row.get("hosting") or (m_obj.get("hosting") if m_obj else None)
            if row_hosting != params["hosting"]:
                return False
        if params["failure_category"] != "all":
            cat = params["failure_category"]
            row_cat = row.get("failure_category")
            matched_cats = row.get("matched_categories") or (m_obj.get("matched_categories") if m_obj else [])
            if row_cat != cat and cat not in (matched_cats or []):
                return False
        return True

    matched = [r for r in rows if matches(r)] if view != "summary" or (
        params["hosting"] == "all" and params["failure_category"] == "all" and not params["machine_name"]
    ) else [r for r in rows if matches(r)]
    selected = matched[params["offset"]:params["offset"] + params["limit"]]
    partial = any(s["status"] != "complete" for s in snapshot["sources"])
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
                "message": "One complete row cannot fit 3500 default-serialized bytes. Use the full report JSON.",
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
        raise EvidenceError("round_trip_failed", "Embedded normalized JSON did not round-trip.", "renderer")
    return escaped


def render_html(snapshot):
    if HTML_TEMPLATE.count("__REPORT_DATA_JSON__") != 1:
        raise EvidenceError("template_missing", "Build the approved template into the standalone tool with build_tool.py.", "renderer")
    validate_logo(snapshot["client"]["logo_data_uri"], snapshot["client"].get("logo_alt", CLIENT_LOGO_ALT))
    return HTML_TEMPLATE.replace("__REPORT_DATA_JSON__", safe_json(snapshot))


def csv_cell(value):
    if value is None:
        return ""
    value = json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":")) if isinstance(value, (dict, list)) else str(value)
    return "'" + value if value.lstrip().startswith(("=", "+", "-", "@", "\t", "\r", "\n")) else value


def csv_document(rows, fields):
    stream = io.StringIO(newline="")
    writer = csv.writer(stream)
    writer.writerow(fields)
    for row in rows:
        writer.writerow([csv_cell(row.get(field)) for field in fields])
    return stream.getvalue()


def machines_csv_rows(snapshot):
    rows = []
    for m in snapshot["machines"]:
        rows.append({
            "machine_name": m["name"],
            "hosting": m["hosting"],
            "resource_group": m["resource_group"],
            "location": m["location"],
            "os_type": m["os_type"],
            "os_name": m["os_name"],
            "power_or_arc_state": m["power_or_arc_state"],
            "agent_version": m.get("agent_version") or "",
            "last_status_change_utc": m.get("last_status_change_utc") or "",
            "patch_mode": m.get("patch_mode") or "",
            "assessment_mode": m.get("assessment_mode") or "",
            "assessment_status": m["assessment_status"],
            "vm_guest_patch_readiness": m["vm_guest_patch_readiness"],
            "reboot_pending": m["reboot_pending"],
            "pending_security_or_critical": m["pending_counts"]["security_or_critical"],
            "pending_update_rollup": m["pending_counts"]["update_rollup"],
            "pending_total": m["pending_counts"]["total"],
            "maintenance_cycles_succeeded": m["maintenance_cycles_summary"]["succeeded"],
            "maintenance_cycles_unresponsive": m["maintenance_cycles_summary"]["unresponsive"],
            "installations_in_window": m["installations_summary"]["runs_in_window"],
            "failed_extensions_count": m["failed_extensions_count"],
            "failure_category": m["failure_category"],
            "matched_categories": m["matched_categories"],
            "severity": m["severity"],
            "investigation_headline": m["investigation_headline"],
            "root_cause_evidence": m["root_cause_evidence"],
            "log_or_source_reference": m["log_or_source_reference"],
            "recommended_human_action": m["recommended_human_action"],
            "resource_id": m["resource_id"],
        })
    return rows


def patches_csv_rows(snapshot):
    rows = []
    for c in snapshot["cycles"]["maintenance_cycles"]:
        rows.append({
            "record_kind": c["type"],
            "machine_name": c["machine_name"],
            "status_or_state": c["status"],
            "classification": c.get("maintenance_scope") or "MaintenanceCycle",
            "kb_id": "",
            "patch_or_cycle_name": c.get("maintenance_configuration_name") or c.get("name") or c["type"],
            "version": "",
            "reboot_info": "",
            "start_utc": c.get("start_utc") or "",
            "end_or_modified_utc": c.get("end_utc") or "",
            "reference_id": c.get("correlation_id") or c["resource_id"],
        })
    for i in snapshot["cycles"]["installation_runs"]:
        rows.append({
            "record_kind": "patch_installation_run",
            "machine_name": i["machine_name"],
            "status_or_state": i["status"],
            "classification": "InstallationRun",
            "kb_id": "",
            "patch_or_cycle_name": "installed=" + str(i["installed_patch_count"]) + ",failed=" + str(i["failed_patch_count"]) + ",notSelected=" + str(i["not_selected_patch_count"]),
            "version": "",
            "reboot_info": i["reboot_status"],
            "start_utc": i.get("start_utc") or "",
            "end_or_modified_utc": i.get("last_modified_utc") or "",
            "reference_id": i.get("maintenance_run_id") or i["resource_id"],
        })
    for p in snapshot["patches"]["combined"]:
        rows.append({
            "record_kind": p["record_kind"],
            "machine_name": p["machine_name"],
            "status_or_state": p["installation_state"],
            "classification": p["primary_classification"],
            "kb_id": p["kb_id"],
            "patch_or_cycle_name": p["patch_name"],
            "version": p["version"],
            "reboot_info": p["reboot_behavior"],
            "start_utc": p.get("published_utc") or "",
            "end_or_modified_utc": p.get("last_modified_utc") or "",
            "reference_id": p["resource_id"],
        })
    return rows


def artifact_directory():
    try:
        cwd = Path.cwd()
        root = cwd.resolve(strict=True)
        linked = any(part.is_symlink() or getattr(part, "is_junction", lambda: False)() for part in (cwd, *cwd.parents))
    except (OSError, RuntimeError) as exc:
        raise EvidenceError("unsafe_artifact_root", "Runtime cwd must resolve to an existing directory.", "artifact_storage") from exc
    if root == Path(root.anchor) or not root.is_dir() or linked:
        raise EvidenceError("unsafe_artifact_root", "Filesystem roots, symlink/junction cwd ancestors and non-directories are forbidden.", "artifact_storage")
    if OUTPUT_DIRECTORY != "patching-investigation-reports":
        raise EvidenceError("unsafe_artifact_directory", "Only the fixed patching-investigation-reports child directory is allowed.", "artifact_storage")
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
        "machines_csv_path": "-machines.csv",
        "patches_csv_path": "-patches.csv",
    }
    if set(paths) != set(suffixes):
        raise EvidenceError("unsafe_sharing_path", "Native delivery requires exactly the four guarded report artifacts.", "artifact_storage")
    stem = paths["report_path"].name.removesuffix(".html")
    if not re.fullmatch(r"patch-[0-9]{8}T[0-9]{6}Z-[0-9a-f]{12}", stem):
        raise EvidenceError("unsafe_sharing_path", "Native aliases require this tool's generated patch-<timestamp>-<hash> filenames.", "artifact_storage")
    expected = root / "patching-investigation-reports"
    aliases = {}
    for key, path in paths.items():
        if path.parent != expected or path.name != stem + suffixes[key]:
            raise EvidenceError("unsafe_sharing_path", "Native aliases must reference the same run in the fixed report directory.", "artifact_storage")
        aliases[key.removesuffix("_path") + "_url"] = (
            "/api/files/tmp/ThreadFiles/" + match[1] + "/patching-investigation-reports/" + quote(path.name, safe="")
        )
    return {**result, "sharing_mode": "native_ui", **aliases}


def report_envelope(snapshot, paths, root):
    partial = any(s["status"] != "complete" for s in snapshot["sources"])
    s = snapshot["summary"]
    result = {
        "status": "partial" if partial else "ok",
        "operation": "report",
        "artifact_status": "written",
        **sharing_fields(root, paths),
        "collection": collection_disclosure(snapshot),
        "summary": {
            "machines_total": s["machines_total"],
            "azure_vms_total": s["azure_vms_total"],
            "arc_machines_total": s["arc_machines_total"],
            "assessed_machines_total": s["assessed_machines_total"],
            "machines_with_blockers_total": s["machines_with_blockers_total"],
            "diagnostic_findings_total": s["diagnostic_findings_total"],
            "maintenance_cycles_succeeded": s["maintenance_cycles_succeeded"],
            "maintenance_cycles_unresponsive": s["maintenance_cycles_unresponsive"],
            "installation_runs_in_window": s["installation_runs_in_window"],
            "pending_security_or_critical_patches": s["pending_security_or_critical_patches"],
            "pending_rollup_patches": s["pending_rollup_patches"],
            "category_counts": s["category_counts"],
        },
        **{key: str(path) for key, path in paths.items()},
    }
    return ensure_response(result)


def write_report(snapshot):
    root, directory = artifact_directory()
    reference = snapshot["reference_utc"].replace(":", "").replace("-", "")
    prefix = "patch-" + reference + "-" + uuid4().hex[:12]
    paths = {
        key: directory / (prefix + suffix)
        for key, suffix in (
            ("report_path", ".html"),
            ("snapshot_path", "-snapshot.json"),
            ("machines_csv_path", "-machines.csv"),
            ("patches_csv_path", "-patches.csv"),
        )
    }
    response = report_envelope(snapshot, paths, root)
    snapshot_document = json.dumps(snapshot, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    if json.loads(snapshot_document) != snapshot:
        raise EvidenceError("round_trip_failed", "Full normalized export does not round-trip.", "artifact_storage")
    documents = {
        "report_path": render_html(snapshot),
        "snapshot_path": snapshot_document,
        "machines_csv_path": csv_document(
            machines_csv_rows(snapshot),
            (
                "machine_name", "hosting", "resource_group", "location", "os_type", "os_name",
                "power_or_arc_state", "agent_version", "last_status_change_utc", "patch_mode",
                "assessment_mode", "assessment_status", "vm_guest_patch_readiness", "reboot_pending",
                "pending_security_or_critical", "pending_update_rollup", "pending_total",
                "maintenance_cycles_succeeded", "maintenance_cycles_unresponsive",
                "installations_in_window", "failed_extensions_count", "failure_category",
                "matched_categories", "severity", "investigation_headline", "root_cause_evidence",
                "log_or_source_reference", "recommended_human_action", "resource_id",
            ),
        ),
        "patches_csv_path": csv_document(
            patches_csv_rows(snapshot),
            (
                "record_kind", "machine_name", "status_or_state", "classification", "kb_id",
                "patch_or_cycle_name", "version", "reboot_info", "start_utc",
                "end_or_modified_utc", "reference_id",
            ),
        ),
    }
    encoded = {key: value.encode("utf-8-sig" if key.endswith("csv_path") else "utf-8") for key, value in documents.items()}
    if any(len(value) > ARTIFACT_BYTES for value in encoded.values()):
        raise EvidenceError("artifact_size_exceeded", "Complete artifacts exceed 4800000 bytes; no records were dropped and no files were written.", "artifact_storage")
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
            raise EvidenceError("artifact_readback_failed", "Written full normalized JSON differs from source-normalized data.", "artifact_storage")
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
                "Artifact failure and cleanup failure; inspect these generated files in the fixed output directory: " + ", ".join(failures),
                "artifact_storage",
            ) from exc
        if isinstance(exc, EvidenceError):
            raise
        raise EvidenceError("artifact_write_failed", "Could not atomically write/read back all four files; partial files were removed.", "artifact_storage") from exc
    return response


def main(
    operation: str = "report",
    period: str = "last_30d",
    view: str = "summary",
    hosting: str = "all",
    failure_category: str = "all",
    machine_name: str = "",
    limit: int = 25,
    offset: int = 0,
) -> dict:
    """Collect Azure Update Manager post-patching evidence and automated per-machine root-cause investigation."""
    try:
        params = validate_parameters(
            operation, period, view, hosting, failure_category, machine_name, limit, offset
        )
        config = validate_config()
        if HTML_TEMPLATE.count("__REPORT_DATA_JSON__") != 1:
            raise EvidenceError("template_missing", "Use the build-generated standalone tool with embedded HTML_TEMPLATE.", "renderer")
        reference = utc_now()
        deadline = time.monotonic() + MAX_COLLECTION_SECONDS
        raw = collect_live(config, params["period"], reference, deadline=deadline)
        snapshot = finish_snapshot(raw, reference, provenance="LIVE", environment="PRODUCTION")
        return query_snapshot(snapshot, params) if operation == "query" else write_report(snapshot)
    except EvidenceError as exc:
        return ensure_response({
            "status": "error",
            "error": exc.public(),
            "artifact_status": "cleanup_failed" if exc.code == "artifact_cleanup_failed" else "not_written",
            "provenance": "LIVE",
        })
