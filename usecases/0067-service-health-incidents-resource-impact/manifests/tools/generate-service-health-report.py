"""Bounded read-only Service Health adapter; build_tool.py embeds the report UI."""

import base64
import binascii
import copy
import csv
import hashlib
import html
import io
import json
import os
import re
import tempfile
import time
from datetime import datetime, timedelta, timezone
from http.client import HTTPException
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, quote, unquote, urlencode, urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from uuid import UUID, uuid4


SUBSCRIPTION_ID = "<APPROVED_SUBSCRIPTION_ID>"
TENANT_ID = "<APPROVED_TENANT_ID>"
MANAGED_IDENTITY_CLIENT_ID = "<APPROVED_UAMI_CLIENT_ID>"
CLIENT_NAME = "Customer"
# Here goes the customer's logo, privately configured as a validated PNG/JPEG
# data URI. Keep generic Git source empty. Use adjacent strings <10K per line.
COMPANY_LOGO_DATA_URI = ""
COMPANY_LOGO_ALT_TEXT = "Customer logo"

API_VERSION = "2025-05-01"
ORIGIN = "https://management.azure.com"
OUTPUT_DIRECTORY = "service-health-reports"
ARTIFACT_BYTES = 4_800_000
TRANSPORT_BYTES = 3_500
MAX_LOGO_BYTES = 100_000
MAX_LOGO_DIMENSION = 2048
RETAINED_LOOKBACK_DAYS = 365
MAX_REQUESTED_DAYS = 93
MAX_PAGES = 25
MAX_SOURCE_RECORDS = 5_000
MAX_EVENT_RECORDS = 500
MAX_RESPONSE_BYTES = 20_000_000
MAX_HTTP_ATTEMPTS = 250
MAX_COLLECTION_SECONDS = 180
MAX_JSON_DEPTH = 50
EVENT_TYPES = ("ServiceIssue", "PlannedMaintenance")
TEMPORAL_SCOPES = ("all", "requested_updates", "active_now", "future_maintenance")
COMPLETE_SOURCE_STATUSES = ("complete", "successful_empty", "successful_empty_in_scope")

# BEGIN BUILD-TIME ASSETS
HTML_TEMPLATE = (
    '<!doctype html>\n<!--\nTHESIS: A temporal review register keeps published communications separate from'
    ' observed workload health; it refuses the health-score dashboard.\nOWN-WORLD: Charcoal #1E1C18 hero w'
    'ith yellow #FBC807 accents frames white evidence cards; shared report-family pills name event types '
    'and source states.\nSTORY: Read the review status and counts, follow a review step or temporal lane, '
    'read a communication beside its resource receipts, then check the source ledger.\nFIRST VIEWPORT: Pro'
    'duct mark (or the configured customer logo), review status, numbers sentence, UTC chips, type/state '
    'distribution and KPI cards.\nFORM: Temporal register with adjacent evidence dossier. Narrow screens s'
    'tack without removing evidence. Print is an A4 layout of the same HTML.\n-->\n<html lang="en">\n<head>\n'
    '<meta charset="utf-8">\n<meta name="viewport" content="width=device-width, initial-scale=1">\n<meta ht'
    'tp-equiv="Content-Security-Policy" content="default-src \'none\'; script-src \'unsafe-inline\'; style-sr'
    'c \'unsafe-inline\'; img-src data:; connect-src \'none\'; base-uri \'none\'; form-action \'none\'">\n<title>S'
    'ervice Health review</title>\n<style>\n:root{color-scheme:light;--yellow:#fbc807;--charcoal:#1e1c18;--'
    'paper:#f3f4f5;--soft:#f4f5f7;--hover:#f8f9fa;--ink:#1f2328;--title:#16181b;--muted:#555b61;--line:#e'
    '1e4e8;--line2:#c4c9cf;\n--link:#155da4;--focus:#155da4;--crit:#b42318;--crit-bg:#fee4e2;--crit-bar:#d'
    '92d20;--med:#93370d;--med-bg:#fef0c7;--med-bar:#f79009;--low:#175cd3;--low-bg:#d1e9ff;\n--info:#34405'
    '4;--info-bg:#eaecf0;--info-bar:#98a2b3;--hero-muted:#d4d0c8;--hero-line:rgba(255,255,255,.22);--shad'
    'ow:0 1px 2px rgba(16,24,40,.05),0 8px 24px rgba(16,24,40,.06);\n--font:"Segoe UI",system-ui,-apple-sy'
    'stem,sans-serif;--mono:ui-monospace,"Cascadia Mono",Consolas,monospace}\n*{box-sizing:border-box}\nhtm'
    'l{scroll-behavior:smooth;scroll-padding-top:76px;scrollbar-color:var(--line2) var(--paper);-webkit-t'
    'ext-size-adjust:100%}\nbody{margin:0;background:var(--paper);color:var(--ink);font:15px/1.55 var(--fo'
    'nt);font-variant-numeric:tabular-nums;-webkit-font-smoothing:antialiased}\n::selection{background:rgb'
    'a(251,200,7,.5);color:var(--charcoal)}\nbutton,input,select{font:inherit;color:inherit}\na{color:var(-'
    '-link);text-underline-offset:3px}\n:focus-visible{outline:3px solid var(--focus);outline-offset:2px}\n'
    'h1,h2,h3,h4,p{margin:0}\nh1,h2,h3,h4{line-height:1.3;text-wrap:balance;color:var(--title)}\np{max-widt'
    'h:75ch}\n.mono{font:13px/1.6 var(--mono);overflow-wrap:break-word}\n.muted{color:var(--muted)}.nowrap{'
    'white-space:nowrap}.small{font-size:13.5px}\n.sr-only{position:absolute;width:1px;height:1px;margin:-'
    '1px;padding:0;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0}\n.skip{position:absolut'
    'e;top:-80px;left:12px;z-index:30;padding:10px 14px;border-radius:10px;background:var(--yellow);color'
    ':var(--charcoal);font-weight:600}\n.skip:focus{top:12px}\n[hidden]{display:none!important}\n.bar{positi'
    'on:sticky;top:0;z-index:20;display:flex;align-items:center;gap:20px;min-height:60px;padding:8px clam'
    'p(16px,4vw,40px);background:#fff;border-bottom:1px solid var(--line)}\n.brand{display:flex;align-item'
    's:center;min-width:0;color:var(--charcoal);text-decoration:none}\n.brand-logo img{display:block;heigh'
    't:36px;width:auto;max-width:200px;object-fit:contain;margin-right:12px}\n.logo-placeholder,.brand:has'
    '(img) .wordmark,.chip-brand{display:none}\n.bar:has(img) .chip-brand{display:inline}\n.wordmark{font-s'
    'ize:17px;font-weight:700;letter-spacing:-.01em;white-space:nowrap}\n.sections{display:flex;gap:2px}\n.'
    'sections a{padding:8px 12px;border-radius:10px;color:var(--muted);font-size:14px;font-weight:600;tex'
    't-decoration:none}\n.sections a:hover{background:var(--soft);color:var(--ink)}\n.acts{margin-left:auto'
    ';display:flex;align-items:center;gap:10px}\n.chip{padding:5px 11px;border:1px solid var(--line2);bord'
    'er-radius:999px;color:var(--muted);font-size:12.5px;font-weight:600;white-space:nowrap}\n.btn{display'
    ':inline-flex;align-items:center;gap:8px;min-height:40px;padding:0 16px;border:1px solid var(--charco'
    'al);border-radius:10px;background:var(--charcoal);color:#fff;font-size:14px;font-weight:700;cursor:p'
    'ointer;white-space:nowrap}\n.btn:hover{background:#3a362f}\nsvg{width:16px;height:16px;flex:none}\n.her'
    'o{position:relative;padding:clamp(28px,4.5vw,52px) clamp(16px,4vw,40px) 104px;background:linear-grad'
    'ient(160deg,#28251f 0%,var(--charcoal) 55%,#151410 100%);color:#fff}\n.hero::before{content:"";positi'
    'on:absolute;inset:0 0 auto;height:4px;background:var(--yellow)}\n.hero-in{max-width:1320px;margin:0 a'
    'uto;display:grid;grid-template-columns:minmax(0,1fr) 340px;gap:24px 48px;align-items:start}\n.kicker{'
    'margin-bottom:10px;color:var(--yellow);font-size:13px;font-weight:700;letter-spacing:.08em;text-tran'
    'sform:uppercase}\n.hero h1{margin-bottom:12px;color:#fff;font-size:clamp(32px,4vw,44px);line-height:1'
    '.1;font-weight:700;letter-spacing:-.02em}\n.lead{max-width:62ch;font-size:17px}\n.sum{margin-top:10px;'
    'color:var(--hero-muted)}.sum b{color:#fff}\n.meta{display:flex;flex-wrap:wrap;gap:8px;margin-top:20px'
    '}\n.meta span{padding:4px 11px;border:1px solid var(--hero-line);border-radius:999px;color:var(--hero'
    '-muted);font-size:12.5px;white-space:nowrap}\n.meta .prov{border-color:var(--yellow);background:var(-'
    '-yellow);color:var(--charcoal);font-weight:700;letter-spacing:.02em}\n.signal{padding:20px 22px;borde'
    'r:1px solid var(--hero-line);border-radius:16px;background:rgba(255,255,255,.06)}\n.signal .k{color:v'
    'ar(--hero-muted);font-size:13px;font-weight:600}\n.signal .v{margin-top:6px;color:var(--yellow);font-'
    'size:26px;line-height:1.15;font-weight:700}\n.signal.neutral .v{color:#fff}\n.signal .d{margin-top:8px'
    ';color:var(--hero-muted);font-size:14px}\n.dist{grid-column:1/-1}\n.dist-head{display:flex;flex-wrap:w'
    'rap;justify-content:space-between;gap:4px 16px;margin-bottom:8px;color:var(--hero-muted);font-size:1'
    '3.5px}\n.dist-head b,.legend b{color:#fff}\n.track{display:flex;height:12px;border-radius:999px;overfl'
    'ow:hidden;background:rgba(255,255,255,.14)}\n.track i{display:block;height:100%}.track i+i{box-shadow'
    ':-2px 0 0 var(--charcoal)}\n.unk{background:repeating-linear-gradient(135deg,#98a2b3 0 4px,#5d6673 4p'
    'x 8px)}\n.legend{display:flex;flex-wrap:wrap;gap:6px 20px;margin-top:10px;color:var(--hero-muted);fon'
    't-size:13.5px}\n.legend span{display:inline-flex;align-items:center;gap:7px}\n.legend i{display:inline'
    '-block;width:10px;height:10px;border-radius:3px}\n.wrap{max-width:1400px;margin:0 auto;padding:0 clam'
    'p(16px,4vw,40px) 40px}\n.kpis{position:relative;z-index:2;display:grid;grid-template-columns:repeat(6'
    ',minmax(0,1fr));gap:14px;margin-top:-64px}\n.kpis:empty{display:none}\n.kpi{min-width:0;padding:16px 1'
    '8px;border:1px solid var(--line);border-radius:16px;background:#fff;box-shadow:var(--shadow)}\n.kpi .'
    'v{color:var(--title);font-size:36px;line-height:1;font-weight:700;letter-spacing:-.02em}\n.kpi .l{mar'
    'gin-top:8px;font-size:14px;font-weight:600}\n.kpi .s{margin-top:4px;color:var(--muted);font-size:12.5'
    'px;line-height:1.4}\n.kpi.warn{border-color:#f5c46b}.kpi.warn .v{color:var(--med)}\n.sim{display:flex;'
    'align-items:center;gap:10px;max-width:none;margin-top:16px;padding:10px 16px;border:1px solid #fedf8'
    '9;border-radius:12px;background:repeating-linear-gradient(135deg,#fffaeb 0 12px,#fef0c7 12px 24px);c'
    'olor:#7a2e0e;font-size:14px;font-weight:600}\n.error{margin-top:16px;padding:16px 20px;border-radius:'
    '12px;background:var(--crit-bg);color:var(--crit)}\n.card{min-width:0;padding:20px 24px;border:1px sol'
    'id var(--line);border-radius:16px;background:#fff;box-shadow:var(--shadow)}\n.card>h2{font-size:19px;'
    'font-weight:700}\n.sub{margin:4px 0 16px;color:var(--muted);font-size:13.5px}\n.overview{display:grid;'
    'grid-template-columns:repeat(2,minmax(0,1fr));gap:16px;align-items:start;margin-top:24px}\n.stack{dis'
    'play:grid;gap:16px;min-width:0}\n.sh{display:flex;flex-wrap:wrap;justify-content:space-between;align-'
    'items:flex-end;gap:8px 24px;margin-bottom:14px}\n.sh h2{font-size:22px;font-weight:700;letter-spacing'
    ':-.01em}\n.sh p{margin-top:4px;color:var(--muted);font-size:14px}\n.counts{color:var(--muted);font-siz'
    'e:13.5px}\n.steps{display:grid;gap:14px;margin:0;padding:0;list-style:none;counter-reset:step}\n.steps'
    ' li{display:grid;grid-template-columns:28px minmax(0,1fr);gap:2px 12px;counter-increment:step}\n.step'
    's li::before{content:counter(step);grid-row:1/span 3;display:grid;place-items:center;width:28px;heig'
    'ht:28px;border-radius:50%;background:var(--charcoal);color:var(--yellow);font-size:13px;font-weight:'
    '700}\n.steps b{color:var(--title);font-weight:650}\n.steps p{color:var(--muted);font-size:13.5px}\n.go{'
    'justify-self:start;margin-top:4px;padding:2px 0;border:0;background:none;color:var(--link);font-size'
    ':13.5px;font-weight:600;text-decoration:underline;text-underline-offset:3px;cursor:pointer}\n.named{d'
    'isplay:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:20px 28px}\n.named h3{margin-bottom:10p'
    'x;color:var(--muted);font-size:12px;font-weight:700;letter-spacing:.05em;text-transform:uppercase}\n.'
    'bars{display:grid;gap:10px}\n.brow{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:3px 10px'
    ';align-items:baseline;font-size:13.5px}\n.brow span{overflow:hidden;text-overflow:ellipsis;white-spac'
    'e:nowrap}\n.brow i{grid-column:1/-1;display:block;height:6px;border-radius:999px;background:var(--sof'
    't);overflow:hidden}\n.brow i i{height:100%;min-width:3px;background:var(--charcoal)}\n.more{margin-top'
    ':10px;color:var(--muted);font-size:12.5px}\n.context-grid{display:grid;grid-template-columns:repeat(a'
    'uto-fit,minmax(170px,1fr));gap:16px 24px}\ndl{margin:0}dt{color:var(--muted);font-size:13px;font-weig'
    'ht:600}dd{margin:4px 0 0}\n.window-label{display:block;margin-top:6px;color:var(--muted);font-size:13'
    'px}\n.coverage-line{display:flex;flex-wrap:wrap;align-items:center;gap:8px 12px;margin-top:18px;paddi'
    'ng-top:14px;border-top:1px solid var(--line);font-size:14px}\n.limits{margin-top:8px;color:var(--mute'
    'd);font-size:13px}\n.pill{display:inline-flex;align-items:center;gap:6px;padding:2px 10px;border-radi'
    'us:999px;font-size:12px;font-weight:650;line-height:1.5;white-space:nowrap}\n.pill::before{content:""'
    ';width:6px;height:6px;border-radius:50%;background:currentColor}\n.pill.incident{background:var(--cri'
    't-bg);color:var(--crit)}\n.pill.maintenance,.pill.partial{background:var(--med-bg);color:var(--med)}\n'
    '.pill.info{background:var(--low-bg);color:var(--low)}\n.pill.unknown{background:var(--info-bg);color:'
    'var(--info)}\n.review{margin-top:44px}\n.lanes{display:flex;flex-wrap:wrap;gap:8px}\n.lane{display:inli'
    'ne-flex;align-items:center;gap:8px;min-height:40px;padding:5px 6px 5px 14px;border:1px solid var(--l'
    'ine2);border-radius:999px;background:#fff;font-size:14px;font-weight:600;cursor:pointer}\n.lane span{'
    'min-width:30px;padding:1px 8px;border-radius:999px;background:var(--soft);font-size:13px;text-align:'
    'center}\n.lane:hover{background:var(--hover);border-color:var(--muted)}\n.lane[aria-pressed="true"]{bo'
    'rder-color:var(--charcoal);background:var(--yellow);color:var(--charcoal)}\n.lane[aria-pressed="true"'
    '] span{background:var(--charcoal);color:#fff}\n.lane-note{margin-top:10px;color:var(--muted);font-siz'
    'e:13px}\n.filters{display:grid;grid-template-columns:minmax(200px,1.6fr) repeat(3,minmax(130px,1fr)) '
    'auto;gap:12px;align-items:end;margin-top:16px;padding-top:16px;border-top:1px solid var(--line)}\nlab'
    'el{display:flex;flex-direction:column;gap:6px;min-width:0;font-size:13px;font-weight:600}\ninput,sele'
    'ct{width:100%;min-width:0;min-height:40px;padding:7px 12px;border:1px solid var(--line2);border-radi'
    'us:10px;background:#fff;font-size:14px;font-weight:400}\ninput::placeholder{color:var(--muted);opacit'
    'y:1}\n.ghost{min-height:40px;padding:0 14px;border:1px solid var(--line2);border-radius:10px;backgrou'
    'nd:#fff;font-size:14px;font-weight:600;cursor:pointer}\n.ghost:hover,a.download:hover{background:var('
    '--soft)}\n.ghost:disabled{background:var(--paper);color:var(--muted);cursor:default}\n.toolbar{display'
    ':flex;flex-wrap:wrap;align-items:center;gap:10px 16px;margin-top:16px;padding-top:14px;border-top:1p'
    'x solid var(--line)}\n.toolbar>div:first-child{flex:1 1 300px}\n#results{font-size:14px;font-weight:60'
    '0}\n.hint{color:var(--muted);font-size:13px}\n.dl{display:flex;flex-wrap:wrap;align-items:center;gap:8'
    'px}\na.download{display:inline-flex;align-items:center;gap:7px;min-height:36px;padding:0 12px;border:'
    '1px solid var(--line2);border-radius:10px;background:#fff;color:var(--ink);font-size:13.5px;font-wei'
    'ght:600;text-decoration:none;white-space:nowrap}\n.workbench{display:grid;grid-template-columns:minma'
    'x(0,1.45fr) minmax(360px,1fr);gap:16px;align-items:start;margin-top:16px}\n.register{padding:0;overfl'
    'ow:hidden}\n.table-scroll{overflow-x:auto;background:linear-gradient(90deg,#fff 30%,rgba(255,255,255,'
    '0)) left/36px 100% no-repeat local,linear-gradient(270deg,#fff 30%,rgba(255,255,255,0)) right/36px 1'
    '00% no-repeat local,radial-gradient(farthest-side at 0 50%,rgba(16,24,40,.16),rgba(16,24,40,0)) left'
    '/14px 100% no-repeat scroll,radial-gradient(farthest-side at 100% 50%,rgba(16,24,40,.16),rgba(16,24,'
    '40,0)) right/14px 100% no-repeat scroll}\ntable{width:100%;border-collapse:collapse;text-align:left;f'
    'ont-size:14px}\n.events-table{min-width:600px}\n.events-table th:not(:first-child){width:1%}\nth{paddin'
    'g:0;border-bottom:1px solid var(--line);background:var(--soft);color:var(--info);font-size:12px;font'
    '-weight:700;letter-spacing:.04em;text-transform:uppercase;white-space:nowrap}\n.sort{display:flex;ali'
    'gn-items:center;gap:6px;width:100%;padding:11px 12px;border:0;background:none;font:inherit;letter-sp'
    'acing:inherit;text-transform:inherit;text-align:left;cursor:pointer}\n.sort::after{content:"";border:'
    '4px solid transparent;border-top-color:currentColor;transform:translateY(2px);opacity:.3}\nth[aria-so'
    'rt] .sort::after{opacity:1}\nth[aria-sort="ascending"] .sort::after{border-top-color:transparent;bord'
    'er-bottom-color:currentColor;transform:translateY(-2px)}\nth.n .sort{justify-content:flex-end}\ntd{pad'
    'ding:12px;border-bottom:1px solid var(--line);vertical-align:top}\nth:first-child .sort,td:first-chil'
    'd{padding-left:20px}\nth:last-child .sort,td:last-child{padding-right:20px}\ntbody tr:last-child td{bo'
    'rder-bottom:0}\ntbody tr:hover td{background:var(--hover)}\ntr.selected td,tr.selected:hover td{backgr'
    'ound:#fff6d1}\n.event-open{padding:0;border:0;background:none;color:var(--title);font-weight:650;line'
    '-height:1.4;text-align:left;overflow-wrap:break-word;cursor:pointer}\n.event-open:hover{text-decorati'
    'on:underline;text-underline-offset:3px}\n.row-meta{display:flex;flex-wrap:wrap;align-items:center;gap'
    ':6px 10px;margin-top:6px}\n.row-meta .mono{color:var(--muted)}\n.ts span{display:block;white-space:now'
    'rap}\n.ts .t,td small{display:block;color:var(--muted);font-size:13px}\ntd.n{text-align:right;white-sp'
    'ace:nowrap}\n.empty{padding:28px 20px;color:var(--muted)}\n.pager{display:flex;flex-wrap:wrap;justify-'
    'content:space-between;align-items:center;gap:10px;padding:12px 20px;border-top:1px solid var(--line)'
    ';color:var(--muted);font-size:13.5px}\n.detail h3{margin:12px 0 6px;font-size:19px;overflow-wrap:brea'
    'k-word}\n.detail h4{margin:22px 0 8px;font-size:15px}\n.detail p{overflow-wrap:break-word}\n.detail-gri'
    'd{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px 20px;margin-top:16px}\n.detail '
    'dd{overflow-wrap:break-word}\n.event-labels{display:flex;flex-wrap:wrap;gap:6px}\n.source-copy{max-hei'
    'ght:240px;overflow:auto;white-space:pre-wrap;font-size:14px}\n.detail-note{margin-top:12px;padding:10'
    'px 14px;border-radius:10px;background:#eef4fb;color:#1c4f86;font-size:13px}\n.uncertainties{margin:8p'
    'x 0 0;padding-left:20px;color:var(--info);font-size:13.5px}\n.uncertainties li{margin:4px 0}\ndetails{'
    'margin-top:12px;padding-top:10px;border-top:1px solid var(--line)}\nsummary{font-size:13.5px;font-wei'
    'ght:600;cursor:pointer;overflow-wrap:break-word}\npre{max-height:420px;overflow:auto;margin:10px 0 0;'
    'padding:12px 14px;border-radius:10px;background:var(--soft);color:#30363b;font:12px/1.6 var(--mono);'
    'white-space:pre-wrap;overflow-wrap:break-word}\n.resource-records details{margin-top:10px}\n.res-meta{'
    'display:block;margin-left:16px;color:var(--muted);font-size:12.5px;font-weight:400}\n.ext{display:inl'
    'ine-flex;align-items:center;gap:5px;margin-top:10px;font-size:13.5px;font-weight:600}\n.ledger{margin'
    '-top:44px}\n.ledger-stats{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:12px}\n.ledger-list{paddin'
    'g:0;overflow:hidden}\n.source-entry{margin:0;padding:12px 20px;border-top:1px solid var(--line)}\n.sou'
    'rce-entry:first-child{border-top:0}\n.source-entry.bad{background:#fffbf0}\n.source-entry summary{disp'
    'lay:list-item;font-size:14px}\n.source-entry summary .pill{margin-left:8px}\n.src-id{font:600 13px var'
    '(--mono);overflow-wrap:break-word}\n.source-stats{display:block;margin-top:3px;color:var(--muted);fon'
    't-size:13px;font-weight:400}\n.source-entry p{margin-top:8px;font-size:13px}\n.ledger-context{max-widt'
    'h:none;padding:14px 20px;border-top:1px solid var(--line);background:var(--soft);color:var(--muted);'
    'font-size:13px}\n.method{margin-top:24px}\n.method ul{margin:10px 0 0;padding-left:20px;font-size:14px'
    '}\n.method li{max-width:85ch;margin:6px 0}\n.foot{display:flex;flex-wrap:wrap;justify-content:space-be'
    'tween;gap:6px 16px;max-width:1400px;margin:0 auto;padding:4px clamp(16px,4vw,40px) 36px;color:var(--'
    'muted);font-size:13px}\n@media (min-width:1101px){.detail{position:sticky;top:76px;max-height:calc(10'
    '0vh - 92px);overflow:auto;overscroll-behavior:contain}}\n@media (max-width:1180px){.kpis{grid-templat'
    'e-columns:repeat(3,minmax(0,1fr))}}\n@media (max-width:1100px){.workbench{grid-template-columns:minma'
    'x(0,1fr)}.filters{grid-template-columns:minmax(200px,1.5fr) 1fr 1fr}.filters label:last-of-type{grid'
    '-column:1/3}}\n@media (max-width:1040px){.hero-in,.overview{grid-template-columns:minmax(0,1fr)}.sect'
    'ions{display:none}}\n@media (max-width:640px){.chip{display:none}.bar{gap:12px}.hero{padding-bottom:8'
    '4px}.lead{font-size:16px}.kpis{grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}\n.kpi{padding:'
    '14px}.kpi .v{font-size:30px}.card{padding:16px}.named,.detail-grid{grid-template-columns:1fr}.lanes,'
    '.dl{display:grid;grid-template-columns:1fr 1fr}\n.lane{justify-content:space-between;border-radius:12'
    'px;font-size:13.5px}.dl a.download{justify-content:center;min-height:44px;padding:4px 10px;white-spa'
    'ce:normal;text-align:center}.filters{grid-template-columns:1fr 1fr}\n.filters label:first-child{grid-'
    'column:1/-1}.filters label:last-of-type{grid-column:auto}.events-table{min-width:560px}.source-entry'
    '{padding:12px 16px}}\n@media (prefers-reduced-motion:reduce){html{scroll-behavior:auto}}\n@page{size:A'
    '4;margin:14mm 12mm 16mm;@bottom-left{content:var(--print-foot,"Service Health review · Azure SRE Age'
    'nt");font:8pt "Segoe UI",system-ui,sans-serif;color:#555b61}\n@bottom-right{content:"Page " counter(p'
    'age) " of " counter(pages);font:8pt "Segoe UI",system-ui,sans-serif;color:#555b61}}\n@media print{*{-'
    'webkit-print-color-adjust:exact;print-color-adjust:exact}\nhtml{scroll-padding-top:0}body{background:'
    '#fff;font-size:12px}\n.bar{position:static;min-height:0;padding:0 0 8px;border:0}.sections,.btn,.tool'
    'bar,.filters,.pager,.skip,.go,.sort::after,.foot{display:none!important}.chip{display:inline-block}\n'
    '.hero{padding:18px 22px 64px;border-radius:12px;overflow:hidden}.hero-in{grid-template-columns:minma'
    'x(0,1fr) 200px;gap:12px 24px}.kicker{font-size:11px;margin-bottom:6px}\n.hero h1{font-size:26px;margi'
    'n-bottom:8px}.lead{font-size:12.5px}.sum,.signal .d,.dist-head,.legend{font-size:11px}.meta{margin-t'
    'op:12px;gap:6px}.meta span{padding:2px 8px;font-size:11px}\n.signal{padding:12px 14px}.signal .k{font'
    '-size:11px}.signal .v{font-size:17px}.wrap{padding:0}\n.kpis{grid-template-columns:repeat(6,minmax(0,'
    '1fr));gap:8px;margin-top:-48px}.kpi{padding:10px}.kpi .v{font-size:22px}.kpi .l,.kpi .s{font-size:11'
    'px}\n.card,.kpi{box-shadow:none}.card{padding:14px 16px}.card>h2{font-size:15px}.sub,.sim,.lane-note,'
    '.limits,.window-label,dt{font-size:11px}.sim{padding:6px 12px}\n.steps{gap:8px}.steps b{font-size:12p'
    'x}.steps p,.more{font-size:11px}.named{grid-template-columns:1fr}.brow,.coverage-line,.counts{font-s'
    'ize:11px}\n.kpi,.steps li,.stack>.card,.method,.source-entry,tr{break-inside:avoid}.sh,.card>h2,.sub{'
    'break-after:avoid}.sh h2{font-size:17px}.sh p{font-size:11px}\n.review{margin-top:24px}.lane{min-heig'
    'ht:0;padding:2px 4px 2px 10px;font-size:11px}.workbench{grid-template-columns:1fr}\n.detail{position:'
    'static;max-height:none;overflow:visible}.detail h3{font-size:15px}.detail h4{font-size:12.5px;margin'
    '-top:14px}.table-scroll{overflow:visible;background:none}.events-table{min-width:0}\ntable{font-size:'
    '11px}th{font-size:11px}.sort,td{padding:6px 8px}.pill,.ts .t,td small{font-size:11px}thead{display:t'
    'able-header-group}\n.source-copy,pre{max-height:none;overflow:visible}pre,.mono{font-size:11px}.ledge'
    'r{break-before:page;margin-top:0}.source-entry{padding:6px 12px}.source-entry summary,.method ul{fon'
    't-size:11.5px}.source-stats,.ledger-context{font-size:11px}}\n</style>\n</head>\n<body>\n<a class="skip"'
    ' href="#review">Skip to event review</a>\n<header class="bar">\n  <a class="brand" href="#top"><span c'
    'lass="brand-logo">__COMPANY_LOGO__</span><span class="wordmark">Azure SRE Agent</span></a>\n  <nav cl'
    'ass="sections" aria-label="Report sections"><a href="#summary">Summary</a><a href="#review">Communic'
    'ations</a><a href="#source-ledger">Sources</a><a href="#method">Method</a></nav>\n  <div class="acts"'
    '><span class="chip"><span class="chip-brand">Azure SRE Agent · </span>Read-only</span><button class='
    '"btn" type="button" id="print-report" title="Print or save as PDF with every row that matches the cu'
    'rrent filters"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-li'
    'necap="round" stroke-linejoin="round" aria-hidden="true"><path d="M6 9V3h12v6M6 18H4a2 2 0 0 1-2-2v-'
    '5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2M6 14h12v7H6z"/></svg>Print / PDF</button></div>\n'
    '</header>\n<main>\n<section class="hero" id="top" aria-labelledby="report-title">\n  <div class="hero-i'
    'n">\n    <div>\n      <p class="kicker">Azure Service Health · <span>__CLIENT_NAME__</span></p>\n      '
    '<h1 id="report-title">Service Health review</h1>\n      <p class="lead">Published incidents and plann'
    'ed maintenance. Evidence for review, not a workload-health verdict.</p>\n      <p class="sum" id="her'
    'o-sum"></p>\n      <div class="meta" id="hero-meta"><span class="prov" id="provenance">Opening snapsh'
    'ot</span><span id="reference-line">Reading the recorded UTC context</span></div>\n    </div>\n    <asi'
    'de class="signal" id="signal" aria-label="Review status"><p class="k">Review status</p><p class="v" '
    'id="verdict">Reading snapshot</p><p class="d" id="verdict-line"></p></aside>\n    <div class="dist" i'
    'd="dist"></div>\n  </div>\n</section>\n<div class="wrap">\n  <div class="kpis" id="summary"></div>\n  <p '
    'class="sim" id="sim-banner" hidden><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke'
    '-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 9v4m0 4h.0'
    '1M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z"/></svg><span id="sim'
    '-text"></span></p>\n  <div id="render-error" class="error" role="alert" hidden></div>\n  <noscript><di'
    'v class="error">JavaScript is required for offline filters and exports. Use the separately delivered'
    ' complete JSON and CSV files; this is not an empty-success report.</div></noscript>\n  <div class="ov'
    'erview">\n    <section class="card" id="next" aria-labelledby="next-heading">\n      <h2 id="next-head'
    'ing">Review next</h2>\n      <p class="sub">Prioritised from this snapshot\'s counts. Each step opens '
    'the matching records.</p>\n      <ol class="steps" id="next-steps"></ol>\n    </section>\n    <div clas'
    's="stack">\n      <section class="card" aria-labelledby="named-heading">\n        <h2 id="named-headin'
    'g">Named in communications</h2>\n        <p class="sub">Services and regions in the published impact '
    'of in-scope records; not measured impact.</p>\n        <div class="named"><div><h3>Services</h3><div '
    'class="bars" id="bars-services"></div></div><div><h3>Regions</h3><div class="bars" id="bars-regions"'
    '></div></div></div>\n      </section>\n      <section class="card window" id="window" aria-labelledby='
    '"window-heading">\n        <h2 id="window-heading">The window matters</h2>\n        <p class="sub">Thr'
    'ee different times shape what this review contains.</p>\n        <div class="context-grid">\n         '
    ' <dl><dt>Requested update window · UTC, end exclusive</dt><dd id="requested-window"></dd><dd class="'
    'window-label">Selection uses lastUpdateTime, not impact start or first publication.</dd></dl>\n      '
    '    <dl><dt>Observed source reads · UTC</dt><dd id="observed-window"></dd><dd class="window-label">N'
    'ative status is observed at collection, not a historical as-of state.</dd></dl>\n          <dl><dt>Re'
    'tained-source queryStartTime · UTC</dt><dd id="query-start"></dd><dd class="window-label">Older Acti'
    've events are not removed because their impact began before the requested month.</dd></dl>\n        <'
    '/div>\n        <div class="coverage-line"><span id="coverage-tag" class="pill unknown"></span><span i'
    'd="coverage-summary"></span></div>\n        <p class="limits">New/changed since last run is not estab'
    'lished. A Tracking ID is not a support-case number.</p>\n      </section>\n    </div>\n  </div>\n  <sect'
    'ion class="review" id="review" aria-labelledby="review-heading">\n    <div class="sh"><div><h2 id="re'
    'view-heading">Communications to review</h2><p>Choose a lane, filter, then select a communication to '
    'read its source record and resource evidence.</p></div><span id="record-counts" class="counts"></spa'
    'n></div>\n    <div class="card">\n      <div class="lanes" role="group" aria-label="Temporal scope">\n '
    '       <button class="lane" type="button" data-scope="all" aria-pressed="true">All returned<span id='
    '"count-all"></span></button>\n        <button class="lane" type="button" data-scope="requested_update'
    's" aria-pressed="false">Requested updates<span id="count-requested"></span></button>\n        <button'
    ' class="lane" type="button" data-scope="active_now" aria-pressed="false">Active observed<span id="co'
    'unt-active"></span></button>\n        <button class="lane" type="button" data-scope="future_maintenan'
    'ce" aria-pressed="false">Future maintenance<span id="count-future"></span></button>\n      </div>\n   '
    '   <p class="lane-note" id="lane-note">All accepted event records in the retained response, includin'
    'g records outside the requested update window. Temporal lanes can overlap.</p>\n      <div class="fil'
    'ters" role="search" aria-label="Filter recorded event evidence">\n        <label>Search communication'
    's<input id="search" type="search" maxlength="160" placeholder="Tracking ID, service, region or text"'
    '></label>\n        <label>Event type<select id="event-type"><option value="all">Both event types</opt'
    'ion><option value="ServiceIssue">Service incidents</option><option value="PlannedMaintenance">Planne'
    'd maintenance</option></select></label>\n        <label>Native current state<select id="state"><optio'
    'n value="all">All states</option><option>Active</option><option>Resolved</option><option>Unknown</op'
    'tion></select></label>\n        <label>Published region<select id="region"><option value="all">All re'
    'gions</option><option value="__unknown__">Unknown region</option></select></label>\n        <button c'
    'lass="ghost" type="button" id="reset">Reset filters</button>\n      </div>\n      <div class="toolbar"'
    '>\n        <div><p id="results" aria-live="polite"></p><p class="hint">Filtered downloads include eve'
    'ry match and its resource rows, not only the visible page.</p></div>\n        <div class="dl" role="g'
    'roup" aria-label="Downloads">\n          <a class="download" id="filtered-json" download="service-hea'
    'lth-filtered.json">Filtered JSON</a>\n          <a class="download" id="events-csv" download="service'
    '-health-events-filtered.csv">Filtered events CSV</a>\n          <a class="download" id="resources-csv'
    '" download="service-health-resources-filtered.csv">Filtered resources CSV</a>\n          <a class="do'
    'wnload" id="full-json" download="service-health-complete.json">Full source JSON</a>\n        </div>\n '
    '     </div>\n    </div>\n    <div class="workbench">\n      <div class="card register">\n        <div cl'
    'ass="table-scroll" tabindex="0" role="region" aria-label="Event register, scroll horizontally if nee'
    'ded">\n          <table class="events-table"><caption class="sr-only">Recorded event communications</'
    'caption>\n            <thead><tr><th scope="col"><button class="sort" type="button" data-sort="title"'
    '>Communication</button></th><th scope="col"><button class="sort" type="button" data-sort="state">Sta'
    'te</button></th><th scope="col"><button class="sort" type="button" data-sort="start">Impact start</b'
    'utton></th><th scope="col" aria-sort="descending"><button class="sort" type="button" data-sort="upda'
    'ted">Last update</button></th><th scope="col" class="n"><button class="sort" type="button" data-sort'
    '="resources">Resources</button></th></tr></thead>\n            <tbody id="event-rows"></tbody>\n      '
    '    </table>\n        </div>\n        <div class="pager"><span id="visible-count"></span><button class'
    '="ghost" type="button" id="show-more">Show 25 more</button></div>\n      </div>\n      <section class='
    '"card detail" id="event-detail" tabindex="-1" aria-label="Selected communication and resource eviden'
    'ce">\n        <p class="muted">Select a communication to inspect its source record and potential reso'
    'urce associations.</p>\n      </section>\n    </div>\n  </section>\n  <section class="ledger" id="source'
    '-ledger" aria-labelledby="ledger-heading">\n    <div class="sh"><div><h2 id="ledger-heading">Source &'
    'amp; coverage ledger</h2><p>Every list and attempted page has its own receipt. A first page or HTTP '
    '200 alone is not completeness. Empty, denied and partial are different outcomes.</p></div></div>\n   '
    ' <div class="ledger-stats" id="ledger-stats"></div>\n    <div class="card ledger-list"><div id="sourc'
    'e-entries"></div><p class="ledger-context" id="retention-note"></p></div>\n  </section>\n  <section cl'
    'ass="card method" id="method" aria-labelledby="method-heading">\n    <h2 id="method-heading">Method a'
    'nd limits</h2>\n    <ul>\n      <li>Read-only snapshot. Published potential impact is not a measured w'
    'orkload outage.</li>\n      <li>Support cases, owners, root-cause verification and prior-run baseline'
    's are not collected. Historical completeness is not proven.</li>\n      <li>Full JSON retains complet'
    'e accepted response fields and pagination evidence; filtered exports contain every selected event/re'
    'source record, not only the visible page.</li>\n    </ul>\n  </section>\n</div>\n</main>\n<footer class="'
    'foot"><span>Report generated by Azure SRE Agent · Read-only</span><span id="foot-ref"></span></foote'
    'r>\n<template id="icon-ext"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="'
    '2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M14 4h6v6m0-6-9 9m7 1v'
    '5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5"/></svg></template>\n<template id="icon-dl"><svg vi'
    'ewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-l'
    'inejoin="round" aria-hidden="true"><path d="M12 3v12m0 0 5-5m-5 5-5-5M4 21h16"/></svg></template>\n<s'
    'cript id="complete-json-bytes" type="application/octet-stream">__FULL_JSON_BASE64__</script>\n<script'
    ' id="report-model" type="application/json">__UI_MODEL_JSON__</script>\n<script>\n(() => {\n  "use stric'
    't";\n  const errorBox = document.getElementById("render-error");\n  try {\n    const data = JSON.parse('
    'document.getElementById("report-model").textContent);\n    const fullJSONBase64 = document.getElement'
    'ById("complete-json-bytes").textContent.trim();\n    if (!Number.isSafeInteger(data.source_json_bytes'
    ') || data.source_json_bytes < 1 || data.source_json_bytes > 4800000 ||\n        fullJSONBase64.length'
    ' !== 4 * Math.ceil(data.source_json_bytes / 3)) throw new Error("Invalid complete JSON byte bound.")'
    ';\n    const binaryJSON = atob(fullJSONBase64);\n    const sourceJSONBytes = Uint8Array.from(binaryJSO'
    'N, character => character.charCodeAt(0));\n    if (sourceJSONBytes.length !== data.source_json_bytes)'
    ' throw new Error("Complete JSON byte length differs from its references.");\n    const decoder = new '
    'TextDecoder("utf-8", {fatal: true});\n    const rangeText = range => {\n      if (!Array.isArray(range'
    ') || range.length !== 2 || !range.every(Number.isSafeInteger) ||\n          range[0] < 0 || range[1] '
    '<= range[0] || range[1] > sourceJSONBytes.length) throw new Error("Invalid source JSON byte referenc'
    'e.");\n      return decoder.decode(sourceJSONBytes.subarray(range[0], range[1]));\n    };\n    const co'
    'mpleteJSON = record => {\n      const normalized = rangeText(record.record_range);\n      const origin'
    'al = rangeText(record.source_record_range);\n      if (normalized[0] !== "{" || !normalized.endsWith('
    '"}") || original[0] !== "{" || !original.endsWith("}")) throw new Error("Referenced records must be '
    'JSON objects.");\n      return normalized.slice(0, -1) + \',"source_record":\' + original + "}";\n    };'
    '\n    const prettyJSON = value => {\n      const pieces = [];\n      let quoted = false, escaped = fals'
    'e, depth = 0;\n      const line = () => "\\n" + "  ".repeat(depth);\n      for (const character of valu'
    'e) {\n        if (quoted) {\n          pieces.push(character);\n          if (escaped) escaped = false;'
    '\n          else if (character === "\\\\") escaped = true;\n          else if (character === \'"\') quoted'
    ' = false;\n        } else if (character === \'"\') {\n          quoted = true;\n          pieces.push(cha'
    'racter);\n        } else if (character === "{" || character === "[") {\n          if (++depth > 100) t'
    'hrow new Error("Source JSON display exceeds the nesting bound.");\n          pieces.push(character, l'
    'ine());\n        } else if (character === "}" || character === "]") {\n          if (--depth < 0) thro'
    'w new Error("Unbalanced source JSON display.");\n          pieces.push(line(), character);\n        } '
    'else if (character === ",") pieces.push(character, line());\n        else if (character === ":") piec'
    'es.push(": ");\n        else pieces.push(character);\n      }\n      if (quoted || escaped || depth) th'
    'row new Error("Incomplete source JSON display.");\n      return pieces.join("");\n    };\n    data.even'
    'ts.concat(data.resources).forEach(record => {\n      rangeText(record.record_range);\n      rangeText('
    'record.source_record_range);\n    });\n    const context = data.context;\n    const totals = data.summa'
    'ry;\n    const byId = id => document.getElementById(id);\n    const el = (tag, text, className) => {\n '
    '     const node = document.createElement(tag);\n      if (text !== undefined && text !== null) node.t'
    'extContent = String(text);\n      if (className) node.className = className;\n      return node;\n    }'
    ';\n    const text = value => value === null || value === undefined || value === "" ? "Unknown / not s'
    'upplied" : String(value);\n    const pill = (label, kind) => el("span", label, "pill " + kind);\n    c'
    'onst typeName = event => event.event_type === "ServiceIssue" ? "Service incident" : "Planned mainten'
    'ance";\n    const typeClass = event => event.event_type === "ServiceIssue" ? "incident" : "maintenanc'
    'e";\n    const statusClass = status => status === "Active" ? "info" : "unknown";\n    const goodSource'
    ' = source => ["complete", "successful_empty", "successful_empty_in_scope"].includes(source.status);\n'
    '    const sourceById = id => data.sources.find(source => source.source_id === id);\n    const noun = '
    '(count, one, many) => count === 1 ? one : many;\n    const plural = (count, one, many) => count + " "'
    ' + noun(count, one, many);\n    const day = value => value ? String(value).slice(0, 10) : "Unknown";\n'
    '    const minute = value => value ? String(value).slice(0, 16).replace("T", " ") + " UTC" : "Unknown'
    '";\n    const nowrap = value => el("span", text(value), "nowrap");\n    const icon = id => byId(id).co'
    'ntent.firstElementChild.cloneNode(true);\n    // Long identifiers may wrap only after a "/" separator'
    ', never mid-token.\n    const segments = value => String(value).split("/").flatMap((part, index) => i'
    'ndex ? ["/", document.createElement("wbr"), part] : [part]);\n    const stamp = value => {\n      cons'
    't node = el("span", null, "ts");\n      const [date, time] = value ? String(value).split("T") : ["Unk'
    'nown", "original retained"];\n      node.append(el("span", date), el("span", time || "", "t"));\n     '
    ' return node;\n    };\n    const fields = (items, parent) => {\n      const grid = el("div", null, "det'
    'ail-grid");\n      items.forEach(([label, value, mono]) => {\n        const group = el("dl");\n        '
    'const content = el("dd", null, mono ? "mono" : "");\n        if (mono && value) content.append(...seg'
    'ments(value));\n        else content.textContent = text(value);\n        group.append(el("dt", label),'
    ' content);\n        grid.append(group);\n      });\n      parent.append(grid);\n    };\n    const rawDeta'
    'ils = (label, value) => {\n      const details = el("details");\n      details.append(el("summary", la'
    'bel), el("pre", value));\n      return details;\n    };\n    const encoded = string => {\n      const by'
    'tes = new TextEncoder().encode(string);\n      let binary = "";\n      for (let index = 0; index < byt'
    'es.length; index += 8192) binary += String.fromCharCode(...bytes.subarray(index, index + 8192));\n   '
    '   return btoa(binary);\n    };\n    const download = (id, content, mime, base64 = false) => {\n      b'
    'yId(id).href = "data:" + mime + ";base64," + (base64 ? content : encoded(content));\n    };\n    const'
    ' csv = (columns, rows) => {\n      const cell = value => \'"\' + String(value).replace(/"/g, \'""\') + \'"'
    '\';\n      return "\\ufeff" + [columns, ...rows].map(row => row.map(cell).join(",")).join("\\r\\n") + "\\r'
    '\\n";\n    };\n    let scope = "all";\n    let selectedKey = null;\n    let shown = 25;\n    let filtered '
    '= [];\n    let printing = false;\n    let sortKey = "updated";\n    let sortDirection = -1;\n    const l'
    'aneNotes = {\n      all: "All accepted event records in the retained response, including records outs'
    'ide the requested update window. Temporal lanes can overlap.",\n      requested_updates: "lastUpdateT'
    'ime falls inside the requested UTC interval. This is not impact-start history, first publication or '
    'newness since last run.",\n      active_now: "The native source reported Active when read. Old impact'
    '-start dates remain visible. This is not reconstructed historical status or workload-outage proof.",'
    '\n      future_maintenance: "PlannedMaintenance with a future impactStartTime and not reported Resolv'
    'ed. Future communication is not guaranteed execution, first publication or measured impact."\n    };\n'
    '    const partial = context.coverage.status === "partial";\n    const count = test => data.events.fil'
    'ter(test).length;\n    const unknownCount = count(event => event.native_status === "Unknown");\n    co'
    'nst windowStart = context.requested_window.start_utc;\n    const windowEnd = context.requested_window'
    '.end_utc_exclusive;\n\n    byId("provenance").textContent = context.provenance;\n    byId("reference-li'
    'ne").textContent = "Reference " + minute(context.reference_utc);\n    byId("hero-meta").append(el("sp'
    'an", "Window " + day(windowStart) + " to " + day(windowEnd) + " UTC"),\n      el("span", Math.round(c'
    'ontext.source_query.lookback_days) + "-day lookback"), el("span", partial ? "Partial coverage" : "Re'
    'turned pages complete"));\n    const sum = byId("hero-sum");\n    if (totals.event_records) {\n      su'
    'm.append("Of ", el("b", totals.native_event_records_received), " records received, ", el("b", totals'
    '.event_records), " are in scope: ",\n        el("b", totals.service_issue_records), noun(totals.servi'
    'ce_issue_records, " service incident", " service incidents") + " and ",\n        el("b", totals.plann'
    'ed_maintenance_records), " planned maintenance. ", el("b", totals.active_observed_records), " were A'
    'ctive when read; ",\n        el("b", totals.future_maintenance_records), noun(totals.future_maintenan'
    'ce_records, " future maintenance communication.", " future maintenance communications."));\n    } els'
    'e {\n      sum.append("No in-scope communications in ", el("b", totals.native_event_records_received)'
    ', " records received. ",\n        partial ? "Collection is partial; inspect the source ledger." : "A '
    'successful-empty read validates the source, not workload health.");\n    }\n    const signalParts = []'
    ';\n    if (partial) signalParts.push(plural(totals.incomplete_sources, "incomplete source", "incomple'
    'te sources"));\n    if (totals.active_observed_records) signalParts.push(totals.active_observed_recor'
    'ds + " Active when read");\n    if (totals.future_maintenance_records) signalParts.push(totals.future'
    '_maintenance_records + " future maintenance");\n    if (unknownCount) signalParts.push(unknownCount +'
    ' " Unknown state");\n    const signal = byId("signal");\n    if (partial) byId("verdict").textContent '
    '= "Partial coverage";\n    else if (!totals.event_records) byId("verdict").textContent = "No communic'
    'ations returned";\n    else if (signalParts.length) byId("verdict").textContent = "Review needed";\n  '
    '  else byId("verdict").textContent = "Nothing Active when read";\n    if (!partial && !signalParts.le'
    'ngth) signal.classList.add("neutral");\n    byId("verdict-line").textContent = signalParts.length ? s'
    'ignalParts.join(" · ")\n      : totals.event_records ? "All in-scope records Resolved when read; not '
    'a workload-health result."\n      : "Successful-empty read: source validation only, not a health resu'
    'lt.";\n    const dist = byId("dist");\n    const head = el("div", null, "dist-head");\n    const headLe'
    'ft = el("span");\n    headLeft.append("By type and source state · ", el("b", totals.event_records), "'
    ' in scope");\n    head.append(headLeft, el("span", totals.native_event_records_received + " received '
    '· " + totals.excluded_category_records + " other-category excluded"));\n    const parts = [\n      ["A'
    'ctive incidents", count(event => event.native_status === "Active" && event.event_type === "ServiceIs'
    'sue"), "var(--crit-bar)"],\n      ["Active maintenance", count(event => event.native_status === "Acti'
    've" && event.event_type === "PlannedMaintenance"), "var(--med-bar)"],\n      ["Resolved", count(event'
    ' => event.native_status === "Resolved"), "var(--info-bar)"],\n      ["Unknown state", unknownCount, "'
    '"]\n    ].filter(part => part[1]);\n    const track = el("div", null, "track");\n    track.setAttribute'
    '("role", "img");\n    track.setAttribute("aria-label", parts.length ? parts.map(part => part[0] + " "'
    ' + part[1]).join(", ") : "No in-scope communications");\n    const legend = el("div", null, "legend")'
    ';\n    parts.forEach(([label, value, color]) => {\n      const segment = el("i", null, color ? "" : "u'
    'nk");\n      const swatch = el("i", null, color ? "" : "unk");\n      segment.style.width = (100 * val'
    'ue / totals.event_records) + "%";\n      if (color) segment.style.background = swatch.style.backgroun'
    'd = color;\n      const item = el("span");\n      item.append(swatch, label + " ", el("b", value));\n  '
    '    track.append(segment);\n      legend.append(item);\n    });\n    if (!parts.length) legend.append(e'
    'l("span", "No in-scope communications"));\n    dist.append(head, track, legend);\n\n    [\n      [totals'
    '.event_records, "In scope", totals.native_event_records_received + " received · " + totals.excluded_'
    'category_records + " other-category excluded"],\n      [totals.active_observed_records, "Active when '
    'read", "Native status at collection"],\n      [totals.requested_update_records, "Updated in window", '
    '"lastUpdateTime in the requested window"],\n      [totals.future_maintenance_records, "Future mainten'
    'ance", "Communicated, not guaranteed"],\n      [totals.impacted_resource_records, "Resource associati'
    'ons", "Potential, not a measured outage"],\n      [totals.incomplete_sources, "Incomplete sources", "'
    'of " + data.sources.length + " source receipts"]\n    ].forEach(([value, label, note], index) => {\n  '
    '    const card = el("div", null, "kpi" + (index === 5 && value ? " warn" : ""));\n      card.append(e'
    'l("p", value, "v"), el("p", label, "l"), el("p", note, "s"));\n      byId("summary").append(card);\n  '
    '  });\n    if (context.provenance !== "LIVE") {\n      byId("sim-banner").hidden = false;\n      byId("'
    'sim-text").textContent = context.provenance === "SIMULATED" ? "Simulated data: offline test fixtures'
    ', not a live Azure read."\n        : context.provenance === "PRIVATE_REPLAY" ? "Replayed source evide'
    'nce: recorded receipts, not a fresh live collection."\n        : "Provenance " + context.provenance +'
    ' ": not a fresh live collection.";\n    }\n\n    const steps = [];\n    if (totals.incomplete_sources) s'
    'teps.push(["Check " + plural(totals.incomplete_sources, "incomplete source receipt", "incomplete sou'
    'rce receipts"),\n      "Denied, unavailable or partial reads are blind spots, so every count here is '
    'a lower bound.", {href: "#source-ledger"}, "Open the source ledger"]);\n    if (totals.active_observe'
    'd_records) steps.push(["Confirm workload impact for " + plural(totals.active_observed_records, "comm'
    'unication", "communications") + " Active when read",\n      "Active is the provider\'s state at collec'
    'tion, not measured downtime. Check the named services with workload owners.", {scope: "active_now"},'
    ' "Show Active observed"]);\n    if (totals.future_maintenance_records) {\n      const earliest = data.'
    'events.filter(event => event.temporal.future_maintenance).map(event => event.impact_start_utc).filte'
    'r(Boolean).sort()[0];\n      steps.push(["Prepare for " + plural(totals.future_maintenance_records, "'
    'future maintenance communication", "future maintenance communications"),\n        (earliest ? "Earlie'
    'st communicated start " + minute(earliest) + ". " : "") + "Communicated, not guaranteed execution.",'
    ' {scope: "future_maintenance"}, "Show future maintenance"]);\n    }\n    if (totals.requested_update_r'
    'ecords) steps.push(["Read " + plural(totals.requested_update_records, "update", "updates") + " in th'
    'e requested window",\n      "lastUpdateTime from " + day(windowStart) + " up to " + day(windowEnd) + '
    '" UTC. An update is not a new incident.", {scope: "requested_updates"}, "Show requested updates"]);\n'
    '    if (unknownCount) steps.push(["Treat " + plural(unknownCount, "record", "records") + " with Unkn'
    'own state as a blind spot",\n      "The source reported neither Active nor Resolved. Read the origina'
    'l record before deciding.", {state: "Unknown"}, "Show Unknown state"]);\n    if (totals.impacted_reso'
    'urce_records) steps.push(["Validate " + plural(totals.impacted_resource_records, "potential resource'
    ' association", "potential resource associations"),\n      "Published associations, not measured outag'
    'es. Select a communication to read its resource records."]);\n    if (!steps.length) steps.push([tota'
    'ls.event_records ? "Nothing Active, upcoming or updated in the window" : "No in-scope communications'
    ' returned",\n      "Keep the source receipts as validation of this read; this is not a workload-healt'
    'h result."]);\n    steps.slice(0, 5).forEach(([title, note, action, label]) => {\n      const item = e'
    'l("li");\n      item.append(el("b", title), el("p", note));\n      if (action && action.href) {\n      '
    '  const link = el("a", label, "go");\n        link.href = action.href;\n        item.append(link);\n   '
    '   } else if (action) {\n        const button = el("button", label, "go");\n        button.type = "but'
    'ton";\n        button.addEventListener("click", () => showView(action.scope, action.state));\n        '
    'item.append(button);\n      }\n      byId("next-steps").append(item);\n    });\n\n    const tally = key ='
    '> {\n      const counts = new Map();\n      data.events.forEach(event => (event[key].length ? event[ke'
    'y] : ["Not supplied"]).forEach(name => counts.set(name, (counts.get(name) || 0) + 1)));\n      return'
    ' [...counts].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));\n    };\n    [["services", "bars'
    '-services"], ["regions", "bars-regions"]].forEach(([key, id]) => {\n      const rows = tally(key);\n  '
    '    const box = byId(id);\n      if (!rows.length) box.append(el("p", "No in-scope communications.", '
    '"more"));\n      rows.slice(0, 6).forEach(([name, value]) => {\n        const row = el("div", null, "b'
    'row");\n        const label = el("span", name);\n        label.title = name;\n        const bar = el("i'
    '");\n        const fill = el("i");\n        fill.style.width = (100 * value / rows[0][1]) + "%";\n     '
    '   bar.append(fill);\n        row.append(label, el("b", value), bar);\n        box.append(row);\n      '
    '});\n      if (rows.length > 6) box.append(el("p", "+" + (rows.length - 6) + " more in the register."'
    ', "more"));\n    });\n\n    byId("requested-window").append(nowrap(windowStart), " to ", nowrap(windowE'
    'nd));\n    byId("observed-window").append(nowrap(context.collection_observed_utc.first), " to ", nowr'
    'ap(context.collection_observed_utc.last));\n    byId("query-start").append(nowrap(context.source_quer'
    'y.query_start_utc));\n    byId("coverage-tag").className = "pill " + (partial ? "partial" : "unknown"'
    ');\n    byId("coverage-tag").textContent = partial ? "Partial source coverage" : "Returned pages comp'
    'lete";\n    byId("coverage-summary").textContent = totals.incomplete_sources + " incomplete source(s)'
    '; historical completeness is not proven."\n      + (context.coverage.event_source_successful_empty ? '
    '" No in-scope event records returned: source validation only, not resilience." : "");\n    byId("reco'
    'rd-counts").textContent = totals.native_event_records_received + " received · " + totals.event_recor'
    'ds + " in scope · " + totals.excluded_category_records + " other-category records excluded";\n    con'
    'st regions = [...new Set(data.events.flatMap(event => event.regions))].sort((a, b) => a.localeCompar'
    'e(b));\n    regions.forEach(region => { const option = el("option", region); option.value = region; b'
    'yId("region").append(option); });\n    byId("count-all").textContent = totals.event_records;\n    byId'
    '("count-requested").textContent = totals.requested_update_records;\n    byId("count-active").textCont'
    'ent = totals.active_observed_records;\n    byId("count-future").textContent = totals.future_maintenan'
    'ce_records;\n    download("full-json", fullJSONBase64, "application/json;charset=utf-8", true);\n    d'
    'ocument.querySelectorAll("a.download").forEach(link => link.prepend(icon("icon-dl")));\n    byId("ret'
    'ention-note").textContent = context.source_query.retention + " The explicit " + context.source_query'
    '.lookback_days + "-day lookback is a request, not a guarantee. Accepted record lastUpdateTime extent'
    ': " + text(context.observed_last_update_extent.first_original) + " to " + text(context.observed_last'
    '_update_extent.last_original) + "; " + context.observed_last_update_extent.missing_or_invalid + " mi'
    'ssing/invalid. This extent is not complete history. No historical daily as-of status, workload outag'
    'e measurement or previous-run baseline is available.";\n    const statuses = new Map();\n    data.sour'
    'ces.forEach(source => statuses.set(source.status, (statuses.get(source.status) || 0) + 1));\n    byId'
    '("ledger-stats").append(pill(plural(data.sources.length, "source receipt", "source receipts"), "unkn'
    'own"),\n      ...[...statuses].map(([status, value]) => pill(value + " " + status.replace(/_/g, " "),'
    ' goodSource({status}) ? "unknown" : "partial")));\n    data.sources.forEach((source, index) => {\n    '
    '  const entry = el("details", null, "source-entry" + (goodSource(source) ? "" : " bad"));\n      entr'
    'y.id = "source-" + index;\n      const heading = el("summary");\n      heading.append(el("span", sourc'
    'e.source_id, "src-id"), pill(source.status.replace(/_/g, " "), goodSource(source) ? "unknown" : "par'
    'tial"));\n      heading.append(el("span", source.records_accepted + " in scope / " + source.records_r'
    'eceived + " received · " + source.records_excluded_by_scope + " other-category records excluded · " '
    '+ source.pages.length + " page attempts · pagination " + (source.pagination_complete ? "finished" : '
    '"not complete"), "source-stats"));\n      entry.append(heading);\n      if (source.errors.length) entr'
    'y.append(el("p", "Coverage errors: " + source.errors.map(error => error.code + (error.http_status ? '
    '" (HTTP " + error.http_status + ")" : "")).join("; ")));\n      if (source.redactions.length) entry.a'
    'ppend(el("p", source.redactions.length + " unexpected sensitive/out-of-scope record(s) redacted. Thi'
    's source is not complete."));\n      entry.append(el("pre", prettyJSON(rangeText(source.detail_range)'
    ')));\n      byId("source-entries").append(entry);\n    });\n    const footer = "Reference " + minute(co'
    'ntext.reference_utc) + " · " + context.provenance;\n    byId("foot-ref").textContent = footer;\n    do'
    'cument.documentElement.style.setProperty("--print-foot", JSON.stringify("Service Health review · " +'
    ' context.client_name + " · " + footer));\n    document.title = "Service Health review · " + context.c'
    'lient_name + " · " + day(context.reference_utc);\n\n    const portalLink = id => {\n      if (!/^\\/subs'
    'criptions\\/[0-9a-f-]{36}\\/resourcegroups\\/[\\w.()-]+\\/providers\\/[\\w.()/-]+$/i.test(id || "")) return'
    ' null;\n      const link = el("a", "Open in Azure portal", "ext");\n      link.href = "https://portal.'
    'azure.com/#@/resource" + id;\n      link.target = "_blank";\n      link.rel = "noopener noreferrer";\n '
    '     link.append(icon("icon-ext"));\n      return link;\n    };\n    const detail = event => {\n      co'
    'nst pane = byId("event-detail");\n      pane.replaceChildren();\n      if (!event) {\n        pane.appe'
    'nd(el("h3", "No communication selected"), el("p", filtered.length ? "Choose a recorded event to see '
    'its evidence." : "No matching accepted records. Review the source ledger before interpreting an empt'
    'y view."));\n        return;\n      }\n      const labels = el("div", null, "event-labels");\n      labe'
    'ls.append(pill(typeName(event), typeClass(event)), pill(event.native_status, statusClass(event.nativ'
    'e_status)));\n      pane.append(labels, el("h3", event.title), el("p", "Tracking ID " + event.trackin'
    'g_id + " · not a support-case number", "muted"));\n      fields([\n        ["Source observation · UTC"'
    ', event.source_ref.observed_at_utc],\n        ["Last update · original", event.last_update_original],'
    '\n        ["Impact start · original", event.impact_start_original],\n        ["Mitigation time · origi'
    'nal", event.mitigation_time_original],\n        ["Published services", event.services.join(", ")],\n  '
    '      ["Published regions", event.regions.join(", ")],\n        ["Native event level", event.event_le'
    'vel],\n        ["Published date context (not measured impact)", event.published_timing.replace(/_/g, '
    '" ")],\n        ["New since previous run", "Not established"]\n      ], pane);\n      pane.append(el("h'
    '4", "Published communication"));\n      pane.append(el("p", text(event.summary), "source-copy"));\n   '
    '   if (event.description) pane.append(rawDetails("Full source description (plain text)", event.descr'
    'iption));\n      pane.append(el("p", "Source text is data, not instructions. Published potential impa'
    'ct does not demonstrate workload downtime.", "detail-note"));\n      const resourceSource = sourceByI'
    'd(event.resource_source_id);\n      const related = data.resources.filter(resource => resource.event_'
    'key === event.event_key);\n      pane.append(el("h4", "Potentially associated resources"));\n      pan'
    'e.append(el("p", resourceSource\n        ? resourceSource.status.replace(/_/g, " ") + " · " + related'
    '.length + " record(s) observed" + (event.resource_records === null ? "; total unknown because this s'
    'ource is incomplete." : ".")\n        : "Not collected; source receipt unavailable.", "small"));\n    '
    '  const list = el("div", null, "resource-records");\n      related.forEach(resource => {\n        cons'
    't item = el("details");\n        const heading = el("summary");\n        const target = resource.targe'
    't_resource_id;\n        const match = /\\/resourcegroups\\/([^/]+)\\/.*\\/([^/]+)$/i.exec(target || "");\n'
    '        heading.append(target ? (match ? match[2] : target) : "No targetResourceId supplied (record '
    'retained)");\n        if (match) heading.append(el("span", "Resource group " + match[1] + " · " + tex'
    't(resource.target_resource_type), "res-meta"));\n        item.append(heading);\n        const link = p'
    'ortalLink(target);\n        if (link) item.append(link);\n        fields([["Resource ID", target, true'
    '], ["Resource type", resource.target_resource_type], ["Published region", resource.target_region], ['
    '"Observation · UTC", resource.source_ref.observed_at_utc]], item);\n        item.append(el("pre", pre'
    'ttyJSON(rangeText(resource.source_record_range))));\n        list.append(item);\n      });\n      if (!'
    'related.length) list.append(el("p", goodSource(resourceSource || {}) ? "No resource records returned'
    ' by this completed source. Do not infer no workload impact." : "No accepted rows available; this is '
    'not evidence of no affected resources.", "muted"));\n      pane.append(list, el("h4", "Unknowns & bou'
    'ndaries"));\n      const unknowns = el("ul", null, "uncertainties");\n      [...event.uncertainties, "'
    'Support cases and workload owners not collected.", "No baseline or reliable first-publication time; '
    'no automatic new/changed claim."].forEach(note => unknowns.append(el("li", note)));\n      pane.appen'
    'd(unknowns, rawDetails("Original event record · every returned field", prettyJSON(rangeText(event.so'
    'urce_record_range))));\n      fields([["Native event ID", event.id, true], ["Event source receipt", e'
    'vent.source_ref.source_id, true], ["Resource source receipt", event.resource_source_id, true]], pane'
    ');\n    };\n    const exports = () => {\n      const keys = new Set(filtered.map(event => event.event_k'
    'ey));\n      const resources = data.resources.filter(resource => keys.has(resource.event_key));\n     '
    ' const sourceIds = new Set(filtered.flatMap(event => [event.source_ref.source_id, event.resource_sou'
    'rce_id]));\n      const receipts = data.sources.filter(source => sourceIds.has(source.source_id));\n  '
    '    const content = \'{"context":\' + JSON.stringify(context)\n        + \',"export_scope":"All selected'
    ' complete records; unfiltered original page envelopes remain in Full source JSON."\'\n        + \',"eve'
    'nts":[\' + filtered.map(completeJSON).join(",") + \']\'\n        + \',"impacted_resources":[\' + resources'
    '.map(completeJSON).join(",") + \']\'\n        + \',"source_receipts":[\' + receipts.map(source => source.'
    'receipt_json).join(",") + "]}\\n";\n      download("filtered-json", content, "application/json;charset'
    '=utf-8");\n      download("events-csv", csv(data.event_csv_fields, filtered.map(event => [...event.cs'
    'v_cells, completeJSON(event)])), "text/csv;charset=utf-8");\n      download("resources-csv", csv(data'
    '.resource_csv_fields, resources.map(resource => [...resource.csv_cells, completeJSON(resource)])), "'
    'text/csv;charset=utf-8");\n    };\n    const time = value => {\n      const parsed = typeof value === "'
    'string" && value ? new Date(value).getTime() : NaN;\n      return Number.isFinite(parsed) ? parsed : '
    'null;\n    };\n    const sortValue = {\n      title: event => event.title.toLocaleLowerCase(),\n      st'
    'ate: event => event.native_status,\n      start: event => time(event.impact_start_original),\n      up'
    'dated: event => time(event.last_update_original),\n      resources: event => event.resource_records ='
    '== null ? event.resource_records_observed : event.resource_records\n    };\n    const compare = (a, b)'
    ' => {\n      const left = sortValue[sortKey](a), right = sortValue[sortKey](b);\n      if (left === ri'
    'ght) return 0;\n      if (left === null) return 1;\n      if (right === null) return -1;\n      return '
    'sortDirection * (typeof left === "string" ? left.localeCompare(right) : left - right);\n    };\n    co'
    'nst render = () => {\n      const search = byId("search").value.toLocaleLowerCase();\n      const kind'
    ' = byId("event-type").value;\n      const state = byId("state").value;\n      const region = byId("reg'
    'ion").value;\n      filtered = data.events.filter(event =>\n        (scope === "all" || event.temporal'
    '[scope]) &&\n        (kind === "all" || event.event_type === kind) &&\n        (state === "all" || eve'
    'nt.native_status === state) &&\n        (region === "all" || (region === "__unknown__" ? !event.regio'
    'ns.length : event.regions.includes(region))) &&\n        [event.title, event.summary || "", event.des'
    'cription || "", event.tracking_id, event.id, ...event.services, ...event.regions].join(" ").toLocale'
    'LowerCase().includes(search)\n      );\n      filtered.sort(compare);\n      const body = byId("event-r'
    'ows");\n      body.replaceChildren();\n      if (!filtered.some(event => event.event_key === selectedK'
    'ey)) selectedKey = filtered[0]?.event_key || null;\n      const visible = printing ? filtered : filte'
    'red.slice(0, shown);\n      visible.forEach(event => {\n        const row = el("tr", null, event.event'
    '_key === selectedKey ? "selected" : "");\n        const communication = el("td");\n        const open '
    '= el("button", event.title, "event-open");\n        open.type = "button";\n        open.setAttribute("'
    'aria-controls", "event-detail");\n        open.setAttribute("aria-pressed", String(event.event_key =='
    '= selectedKey));\n        open.addEventListener("click", () => {\n          selectedKey = event.event_'
    'key;\n          render();\n          const dossier = byId("event-detail");\n          dossier.scrollTop'
    ' = 0;\n          dossier.focus({preventScroll: true});\n          const top = dossier.getBoundingClien'
    'tRect().top;\n          if (top < 0 || top > innerHeight / 2) dossier.scrollIntoView({block: "start"}'
    ');\n        });\n        const labels = el("div", null, "row-meta");\n        labels.append(pill(typeNa'
    'me(event), typeClass(event)), el("span", event.tracking_id, "mono"));\n        communication.append(o'
    'pen, labels);\n        const stateCell = el("td");\n        stateCell.append(pill(event.native_status,'
    ' statusClass(event.native_status)));\n        const start = el("td");\n        start.append(stamp(even'
    't.impact_start_utc));\n        const updated = el("td");\n        updated.append(stamp(event.last_upda'
    'te_utc));\n        const resourceCell = el("td", event.resource_records === null ? event.resource_rec'
    'ords_observed + " observed" : String(event.resource_records), "n");\n        if (event.resource_recor'
    'ds === null) resourceCell.append(el("small", "total unknown"));\n        row.append(communication, st'
    'ateCell, start, updated, resourceCell);\n        body.append(row);\n      });\n      if (!filtered.leng'
    'th) {\n        const row = el("tr");\n        const cell = el("td", data.events.length\n          ? "No'
    ' records match these filters. Reset filters to review all returned evidence."\n          : partial ? '
    '"No event records accepted. Collection is partial; inspect the source ledger."\n          : "Successf'
    'ul-empty event reads. This validates the source, not workload health or resilience.", "empty");\n    '
    '    cell.colSpan = 5;\n        row.append(cell);\n        body.append(row);\n      }\n      byId("result'
    's").textContent = filtered.length + " matching / " + data.events.length + " accepted event records";'
    '\n      byId("visible-count").textContent = "Showing " + visible.length + " of " + filtered.length + '
    '" matches";\n      byId("show-more").disabled = visible.length >= filtered.length;\n      byId("show-m'
    'ore").hidden = filtered.length <= 25;\n      byId("lane-note").textContent = laneNotes[scope];\n      '
    'document.querySelectorAll(".lane").forEach(button => button.setAttribute("aria-pressed", String(butt'
    'on.dataset.scope === scope)));\n      document.querySelectorAll(".sort").forEach(button => {\n        '
    'const header = button.closest("th");\n        if (button.dataset.sort === sortKey) header.setAttribut'
    'e("aria-sort", sortDirection > 0 ? "ascending" : "descending");\n        else header.removeAttribute('
    '"aria-sort");\n      });\n      detail(filtered.find(event => event.event_key === selectedKey));\n     '
    ' exports();\n    };\n    const showView = (nextScope, nextState) => {\n      byId("search").value = "";'
    '\n      ["event-type", "region"].forEach(id => byId(id).value = "all");\n      byId("state").value = n'
    'extState || "all";\n      scope = nextScope || "all"; shown = 25; render();\n      byId("review").scro'
    'llIntoView({block: "start"});\n      (nextState ? byId("state") : document.querySelector(\'.lane[data-'
    'scope="\' + scope + \'"]\')).focus({preventScroll: true});\n    };\n    document.querySelectorAll(".lane"'
    ').forEach(button => button.addEventListener("click", () => { scope = button.dataset.scope; shown = 2'
    '5; render(); }));\n    document.querySelectorAll(".sort").forEach(button => button.addEventListener("'
    'click", () => {\n      const key = button.dataset.sort;\n      sortDirection = key === sortKey ? -sort'
    'Direction : key === "title" || key === "state" ? 1 : -1;\n      sortKey = key;\n      render();\n    })'
    ');\n    ["event-type", "state", "region"].forEach(id => byId(id).addEventListener("change", () => { s'
    'hown = 25; render(); }));\n    byId("search").addEventListener("input", () => { shown = 25; render();'
    ' });\n    byId("reset").addEventListener("click", () => {\n      byId("search").value = "";\n      ["ev'
    'ent-type", "state", "region"].forEach(id => byId(id).value = "all");\n      scope = "all"; shown = 25'
    '; render();\n    });\n    byId("show-more").addEventListener("click", () => { shown += 25; render(); }'
    ');\n    byId("print-report").addEventListener("click", () => window.print());\n    window.addEventList'
    'ener("beforeprint", () => { printing = true; render(); });\n    window.addEventListener("afterprint",'
    ' () => { printing = false; render(); });\n    render();\n  } catch (error) {\n    document.getElementBy'
    'Id("verdict").textContent = "Report did not initialize";\n    errorBox.hidden = false;\n    errorBox.t'
    'extContent = "The offline report could not initialize. Do not interpret this as an empty source. Ope'
    'n the separately delivered complete JSON/CSV files and report the render error to the operator.";\n  '
    '  console.error("Offline report initialization failed", error);\n  }\n})();\n</script>\n</body>\n</html>\n'
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
    def __init__(self, code, message, source="validation", http_status=None, receipt=None):
        super().__init__(message)
        self.code = code
        self.source = source
        self.http_status = http_status
        self.receipt = receipt

    def document(self):
        result = {"code": self.code, "source": self.source, "message": str(self)}
        if self.http_status is not None:
            result["http_status"] = self.http_status
        return result


def utc_now():
    return datetime.now(timezone.utc)


def iso(value):
    value = value.astimezone(timezone.utc)
    return value.isoformat(timespec="microseconds" if value.microsecond else "seconds").replace("+00:00", "Z")


def json_text(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def decode_json(data):
    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate JSON object key.")
            result[key] = value
        return result

    def reject_constant(value):
        raise ValueError("Nonfinite JSON constant.")

    result = json.loads(data, object_pairs_hook=unique_object, parse_constant=reject_constant)
    pending = [(result, 0)]
    while pending:
        item, depth = pending.pop()
        if depth > MAX_JSON_DEPTH:
            raise ValueError("JSON nesting exceeds its explicit bound.")
        if isinstance(item, dict):
            for key in item:
                key.encode("utf-8")
            pending.extend((value, depth + 1) for value in item.values())
        elif isinstance(item, list):
            pending.extend((value, depth + 1) for value in item)
        elif isinstance(item, str):
            item.encode("utf-8")
        elif isinstance(item, float) and not (-float("inf") < item < float("inf")):
            raise ValueError("Nonfinite JSON number.")
    return result


def response_bytes(value):
    return len(json.dumps(value).encode("utf-8"))


def budget_response(value):
    if response_bytes(value) > TRANSPORT_BYTES:
        raise EvidenceError("response_size_exceeded", "Default-serialized tool result exceeds 3500 bytes; no truncated result is returned.", "transport")
    return value


def configured_guid(value, name):
    try:
        valid = isinstance(value, str) and str(UUID(value)) == value.lower() and UUID(value).int != 0
    except (ValueError, AttributeError):
        valid = False
    if not valid:
        raise EvidenceError("configuration_required", "Set a real fixed " + name + " in the administrator-owned code before authentication.", "configuration")
    return value.lower()


def plain_text(value, field, maximum, empty=False):
    if not isinstance(value, str) or len(value) > maximum or (not empty and not value.strip()) or re.search(r"[\x00-\x1f\x7f\ud800-\udfff]", value):
        raise EvidenceError("invalid_parameter", field + " must be bounded plain text.", "parameters")
    return value.strip()


def configuration():
    config = {
        "subscription_id": configured_guid(SUBSCRIPTION_ID, "SUBSCRIPTION_ID"),
        "tenant_id": configured_guid(TENANT_ID, "TENANT_ID"),
        "client_id": configured_guid(MANAGED_IDENTITY_CLIENT_ID, "MANAGED_IDENTITY_CLIENT_ID"),
    }
    try:
        config["client_name"] = plain_text(CLIENT_NAME, "CLIENT_NAME", 120)
    except EvidenceError as exc:
        raise EvidenceError("invalid_branding", "CLIENT_NAME must contain 1 to 120 plain characters.", "branding") from exc
    return config


def logo_markup():
    try:
        alt = plain_text(COMPANY_LOGO_ALT_TEXT, "COMPANY_LOGO_ALT_TEXT", 120)
    except EvidenceError as exc:
        raise EvidenceError("invalid_company_logo", "Provide descriptive customer-logo alt text of 1 to 120 plain characters.", "branding") from exc
    if COMPANY_LOGO_DATA_URI == "":
        return '<span class="logo-placeholder">Customer logo</span>'
    if not isinstance(COMPANY_LOGO_DATA_URI, str):
        raise EvidenceError("invalid_company_logo", "The optional logo must be a PNG/JPEG base64 data URI.", "branding")
    if len(COMPANY_LOGO_DATA_URI) > ((MAX_LOGO_BYTES + 2) // 3) * 4 + 32:
        raise EvidenceError("invalid_company_logo", "Logo exceeds the 100000-byte raster bound.", "branding")
    match = re.fullmatch(r"data:image/(png|jpeg);base64,([A-Za-z0-9+/]+={0,2})", COMPANY_LOGO_DATA_URI)
    if match is None:
        raise EvidenceError("invalid_company_logo", "Only an embedded PNG/JPEG is allowed; no remote URL or SVG.", "branding")
    try:
        data = base64.b64decode(match[2], validate=True)
    except (ValueError, binascii.Error) as exc:
        raise EvidenceError("invalid_company_logo", "Logo base64 is invalid.", "branding") from exc
    if not 1 <= len(data) <= MAX_LOGO_BYTES:
        raise EvidenceError("invalid_company_logo", "Logo must contain 1 to 100000 raster bytes.", "branding")
    try:
        from PIL import Image, UnidentifiedImageError
    except ImportError as exc:
        raise EvidenceError("dependency_missing", "Configured branding requires Pillow raster validation.", "branding") from exc
    try:
        with Image.open(io.BytesIO(data), formats=["PNG", "JPEG"]) as image:
            width, height = image.size
            if (
                image.format != ("PNG" if match[1] == "png" else "JPEG")
                or not 1 <= width <= MAX_LOGO_DIMENSION
                or not 1 <= height <= MAX_LOGO_DIMENSION
                or getattr(image, "n_frames", 1) != 1
            ):
                raise EvidenceError("invalid_company_logo", "Use one frame, matching PNG/JPEG MIME, at most 2048 by 2048 pixels.", "branding")
            image.verify()
        with Image.open(io.BytesIO(data), formats=["PNG", "JPEG"]) as image:
            image.load()
    except (OSError, ValueError, SyntaxError, UnidentifiedImageError, Image.DecompressionBombError) as exc:
        raise EvidenceError("invalid_company_logo", "The logo is not a complete valid raster.", "branding") from exc
    return (
        '<img src="' + html.escape(COMPANY_LOGO_DATA_URI, quote=True) + '" alt="'
        + html.escape(alt, quote=True) + '" width="' + str(width) + '" height="' + str(height) + '">'
    )


def parse_utc(value, field):
    if not isinstance(value, str) or len(value) > 40:
        raise EvidenceError("invalid_time", field + " must be an ISO 8601 UTC timestamp.", "parameters")
    fraction = re.search(r"\.(\d+)", value)
    if fraction is not None and any(char != "0" for char in fraction[1][6:]):
        raise EvidenceError("invalid_time", field + " supports at most microsecond precision; no sub-microsecond input is rounded silently.", "parameters")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise EvidenceError("invalid_time", field + " must be an ISO 8601 UTC timestamp.", "parameters") from exc
    if result.tzinfo is None or result.utcoffset() != timedelta(0):
        raise EvidenceError("invalid_time", field + " requires Z or an explicit zero UTC offset.", "parameters")
    return result.astimezone(timezone.utc)


def parameters(operation, period, start_utc, end_utc, view, event_type, state, time_scope, search, limit, offset, reference):
    enums = {
        "operation": (operation, ("report", "query")),
        "period": (period, ("auto", "previous_month", "last_24h", "last_7d", "custom")),
        "view": (view, ("summary", "events", "resources", "coverage")),
        "event_type": (event_type, ("all", *EVENT_TYPES)),
        "state": (state, ("all", "Active", "Resolved", "Unknown")),
        "time_scope": (time_scope, TEMPORAL_SCOPES),
    }
    for field, (value, allowed) in enums.items():
        if not isinstance(value, str) or value not in allowed:
            raise EvidenceError("invalid_parameter", field + " must be one of its documented values.", "parameters")
    if type(limit) is not int or not 1 <= limit <= 50 or type(offset) is not int or not 0 <= offset <= 10_000:
        raise EvidenceError("invalid_parameter", "limit requires int 1-50 and offset int 0-10000; booleans/floats are rejected.", "parameters")
    search = plain_text(search, "search", 160, empty=True)
    if operation == "report" and (view != "summary" or event_type != "all" or state != "all" or time_scope != "all" or search or limit != 10 or offset != 0):
        raise EvidenceError("invalid_combination", "Report mode retains all collected evidence; use default query-only filters and paging.", "parameters")
    if view in ("summary", "coverage") and (event_type != "all" or state != "all" or time_scope != "all" or search):
        raise EvidenceError("invalid_combination", "Event filters apply only to events/resources, not summary/coverage.", "parameters")
    selected = ("previous_month" if operation == "report" else "last_24h") if period == "auto" else period
    if selected == "custom":
        start, end = parse_utc(start_utc, "start_utc"), parse_utc(end_utc, "end_utc")
    else:
        if start_utc != "" or end_utc != "":
            raise EvidenceError("invalid_combination", "start_utc/end_utc are accepted only with period=custom.", "parameters")
        if selected == "previous_month":
            end = reference.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            start = (end - timedelta(days=1)).replace(day=1)
        else:
            end = reference
            start = end - timedelta(days=1 if selected == "last_24h" else 7)
    if not start < end <= reference or end - start > timedelta(days=MAX_REQUESTED_DAYS) or start < reference - timedelta(days=RETAINED_LOOKBACK_DAYS):
        raise EvidenceError("invalid_window", "Request a past UTC window of at most 93 days within the 365-day retained-source lookback.", "parameters")
    return {
        "operation": operation, "view": view, "event_type": event_type, "state": state,
        "time_scope": time_scope, "search": search, "limit": limit, "offset": offset,
        "window": {"period": selected, "start_utc": iso(start), "end_utc_exclusive": iso(end), "basis": "lastUpdateTime"},
        "source_query_start_utc": iso(reference - timedelta(days=RETAINED_LOOKBACK_DAYS)),
    }


def events_url(config, query_start):
    query = urlencode({"api-version": API_VERSION, "queryStartTime": query_start})
    return ORIGIN + "/subscriptions/" + config["subscription_id"] + "/providers/Microsoft.ResourceHealth/events?" + query


def resources_url(config, tracking_id):
    if not isinstance(tracking_id, str) or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}", tracking_id) is None:
        raise EvidenceError("invalid_event_identity", "Event name cannot be used as a bounded native event path.", "source_scope")
    return (
        ORIGIN + "/subscriptions/" + config["subscription_id"]
        + "/providers/Microsoft.ResourceHealth/events/" + quote(tracking_id, safe="")
        + "/impactedResources?api-version=" + API_VERSION
    )


def query_pairs(url, source):
    try:
        pairs = parse_qsl(urlsplit(url).query, keep_blank_values=True, strict_parsing=True)
    except ValueError as exc:
        raise EvidenceError("unsafe_source_url", "Source URL has malformed query parameters.", source) from exc
    result = {}
    for key, value in pairs:
        key = key.casefold()
        if key in result:
            raise EvidenceError("unsafe_source_url", "Source URL repeats a query parameter.", source)
        result[key] = value
    return result


def validate_request(url, config):
    if not isinstance(url, str) or len(url) > 16_000 or re.search(r"[\x00-\x20\x7f\\]|%(?![0-9A-Fa-f]{2})", url):
        raise EvidenceError("unsafe_source_url", "Source URL is not a bounded HTTPS native request.", "source_scope")
    try:
        parsed = urlsplit(url)
    except ValueError as exc:
        raise EvidenceError("unsafe_source_url", "Source URL has an invalid authority.", "source_scope") from exc
    prefix = "/subscriptions/" + config["subscription_id"] + "/providers/Microsoft.ResourceHealth/events"
    if parsed.scheme != "https" or parsed.netloc.casefold() != "management.azure.com" or parsed.fragment:
        raise EvidenceError("unsafe_source_url", "Only the fixed ARM origin is allowed; no redirects or credentials in URLs.", "source_scope")
    decoded = unquote(parsed.path)
    if decoded != parsed.path or "\\" in decoded or any(part in (".", "..") for part in decoded.split("/")):
        raise EvidenceError("unsafe_source_url", "Encoded paths, traversal and alternate separators are forbidden.", "source_scope")
    query = query_pairs(url, "source_scope")
    continuation = {"$skiptoken", "skiptoken"}
    if query.get("api-version") != API_VERSION or any(not query[key] for key in continuation & query.keys()):
        raise EvidenceError("unsafe_source_url", "Native API version and nonempty continuation are required.", "source_scope")
    if parsed.path == prefix:
        if set(query) - continuation != {"api-version", "querystarttime"}:
            raise EvidenceError("unsafe_source_url", "Only the native subscription feed with explicit queryStartTime is allowed; categories are selected locally.", "source_scope")
        parse_utc(query["querystarttime"], "queryStartTime")
    elif re.fullmatch(re.escape(prefix) + r"/[A-Za-z0-9][A-Za-z0-9_-]{0,127}/impactedResources", parsed.path):
        if set(query) - continuation != {"api-version"}:
            raise EvidenceError("unsafe_source_url", "Impacted-resource requests accept only the fixed API version and continuation.", "source_scope")
    else:
        raise EvidenceError("unsafe_source_url", "Only configured subscription events and their impactedResources may be read.", "source_scope")


def next_link(link, initial, config):
    if not isinstance(link, str) or len(link) > 16_000:
        raise EvidenceError("invalid_pagination", "Continuation must be a bounded native URL.", "pagination")
    query, required = query_pairs(link, "pagination"), query_pairs(initial, "pagination")
    if query.get("api-version") != required["api-version"]:
        raise EvidenceError("invalid_pagination", "Continuation changed/omitted the fixed API version.", "pagination")
    if "querystarttime" in required and "querystarttime" not in query:
        try:
            parts = urlsplit(link)
        except ValueError as exc:
            raise EvidenceError("invalid_pagination", "Continuation has an invalid authority.", "pagination") from exc
        pairs = parse_qsl(parts.query, keep_blank_values=True, strict_parsing=True)
        pairs.append(("queryStartTime", required["querystarttime"]))
        link = urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(pairs), parts.fragment))
        query["querystarttime"] = required["querystarttime"]
    validate_request(link, config)
    current, original = urlsplit(link), urlsplit(initial)
    if current.path != original.path:
        raise EvidenceError("invalid_pagination", "Continuation changed the source resource path.", "pagination")
    if any(query.get(key) != value for key, value in required.items()) or set(query) - set(required) - {"$skiptoken", "skiptoken"}:
        raise EvidenceError("invalid_pagination", "Continuation changed/omitted query scope or added an unsupported parameter.", "pagination")
    if "$skiptoken" in query and "skiptoken" in query:
        raise EvidenceError("invalid_pagination", "Continuation supplied ambiguous skip tokens.", "pagination")
    return link


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class NativeReader:
    def __init__(self, config):
        try:
            from azure.identity import ManagedIdentityCredential, CredentialUnavailableError
            from azure.core.exceptions import ClientAuthenticationError, ServiceRequestError
        except ImportError as exc:
            raise EvidenceError("dependency_missing", "Install azure-identity; no human/CLI credential fallback is available.", "identity") from exc
        self.config = config
        self.credential = ManagedIdentityCredential(
            client_id=config["client_id"], connection_timeout=5, read_timeout=10, retry_total=0,
        )
        self.auth_errors = (CredentialUnavailableError, ClientAuthenticationError, ServiceRequestError)
        self.opener = build_opener(NoRedirect())
        self.deadline = time.monotonic() + MAX_COLLECTION_SECONDS
        self.attempt_count = 0
        self.cached_token = None

    def close(self):
        self.credential.close()

    def token(self):
        if self.cached_token is not None and self.cached_token.expires_on > time.time() + 60:
            return self.cached_token.token
        try:
            token = self.credential.get_token(ORIGIN + "/.default")
        except self.auth_errors as exc:
            raise EvidenceError("authentication_failed", "The fixed managed identity could not acquire an ARM token.", "identity") from exc
        try:
            body = token.token.split(".")[1]
            claims = decode_json(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
            claims = normalize_sidecar_claims(claims)
        except (AttributeError, IndexError, ValueError, RecursionError, binascii.Error) as exc:
            raise EvidenceError("identity_mismatch", "Managed-identity token claims could not be verified; token data is excluded.", "identity") from exc
        if not isinstance(claims, dict) or (
            str(claims.get("tid", "")).lower() != self.config["tenant_id"]
            or str(claims.get("appid", claims.get("azp", ""))).lower() != self.config["client_id"]
            or str(claims.get("aud", "")).rstrip("/") != ORIGIN
        ):
            raise EvidenceError("identity_mismatch", "Token tenant/client/audience differs from fixed configuration.", "identity")
        self.cached_token = token
        return token.token

    def get(self, url, source):
        validate_request(url, self.config)
        attempts = []
        for attempt in range(2):
            if self.attempt_count >= MAX_HTTP_ATTEMPTS or time.monotonic() >= self.deadline:
                raise EvidenceError("collection_bound", "The shared request/deadline bound was reached; remaining evidence is unavailable.", source, receipt={"attempts": attempts})
            self.attempt_count += 1
            token = self.token()
            remaining = self.deadline - time.monotonic()
            if remaining <= 0:
                raise EvidenceError("collection_bound", "The collection deadline expired during managed-identity acquisition; no ARM request was sent.", source, receipt={"attempts": attempts})
            request = Request(url, headers={"Authorization": "Bearer " + token, "Accept": "application/json"}, method="GET")
            started = iso(utc_now())
            try:
                try:
                    response = self.opener.open(request, timeout=max(0.1, min(20, remaining)))
                except HTTPError as exc:
                    response = exc
                with response:
                    status = response.code
                    request_id = response.headers.get("x-ms-request-id", "")
                    retry_after = response.headers.get("Retry-After", "")
                    chunks, length, complete = [], 0, False
                    while length <= MAX_RESPONSE_BYTES:
                        if time.monotonic() >= self.deadline:
                            attempts.append({
                                "started_at_utc": started, "finished_at_utc": iso(utc_now()),
                                "http_status": status, "body_incomplete": True, "response_bytes_observed": length,
                            })
                            raise EvidenceError("collection_bound", "The collection deadline expired while reading the native response; an incomplete body was not accepted.", source, status, {"attempts": attempts})
                        # read1 permits a deadline check between buffered network reads.
                        chunk = response.read1(min(65_536, MAX_RESPONSE_BYTES + 1 - length))
                        if not chunk:
                            complete = True
                            break
                        chunks.append(chunk)
                        length += len(chunk)
                    data = b"".join(chunks)
            except (URLError, TimeoutError, OSError, HTTPException) as exc:
                attempts.append({"started_at_utc": started, "finished_at_utc": iso(utc_now()), "http_status": None, "code": "transport_failed"})
                raise EvidenceError("transport_failed", "Native HTTPS read failed; no empty response was substituted.", source, receipt={"attempts": attempts}) from exc
            receipt = {
                "started_at_utc": started, "finished_at_utc": iso(utc_now()),
                "http_status": status, "response_bytes": len(data),
                "response_complete": complete,
                "request_id": request_id, "response_sha256": hashlib.sha256(data).hexdigest(),
            }
            attempts.append(receipt)
            if len(data) > MAX_RESPONSE_BYTES:
                raise EvidenceError("source_response_too_large", "Native response exceeds 20000000 bytes; an incomplete body was not accepted.", source, status, {"attempts": attempts})
            try:
                payload = decode_json(data)
            except (ValueError, UnicodeDecodeError, RecursionError) as exc:
                raise EvidenceError("invalid_response_json", "Native response is not valid bounded JSON; raw non-JSON bodies are excluded.", source, status, {"attempts": attempts}) from exc
            if status in (429, 500, 502, 503, 504) and attempt == 0:
                receipt["error_response"] = payload
                delay = min(int(retry_after), 2) if re.fullmatch(r"[0-9]{1,4}", retry_after) else 1
                time.sleep(min(delay, max(0, self.deadline - time.monotonic())))
                continue
            return {"http_status": status, "payload": payload, "attempts": attempts, "observed_at_utc": receipt["finished_at_utc"]}
        raise EvidenceError("source_retry_exhausted", "Native retry bound was exhausted.", source)


def source_error(code, message, source, http_status=None):
    return EvidenceError(code, message, source, http_status).document()


def record_in_scope(raw, kind, config, tracking_id=None):
    if not isinstance(raw, dict):
        return "Record is not an object."
    identity = raw.get("id")
    prefix = "/subscriptions/" + config["subscription_id"] + "/providers/Microsoft.ResourceHealth/events/"
    if not isinstance(identity, str) or "\\" in identity or "%" in identity or "?" in identity or "#" in identity or any(part in (".", "..") for part in identity.split("/")):
        return "Record has no safe native subscription identity."
    if kind == "events":
        name = raw.get("name")
        if not isinstance(name, str) or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}", name) is None:
            return "Event identity is outside the fixed subscription or cannot be verified."
        accepted_ids = (
            prefix + name, "/providers/Microsoft.ResourceHealth/events/" + name,
            "Microsoft.ResourceHealth/events/" + name,
        )
        if identity.casefold() not in [candidate.casefold() for candidate in accepted_ids]:
            return "Event identity is outside the fixed subscription or cannot be verified."
        props = raw.get("properties")
        if not isinstance(props, dict) or props.get("eventType") not in EVENT_TYPES or (props.get("isEventSensitive") is not None and props.get("isEventSensitive") is not False):
            return "Event category/sensitivity is outside the fixed nonsensitive category read."
    else:
        prefixes = (
            prefix + tracking_id + "/impactedResources/",
            "/providers/Microsoft.ResourceHealth/events/" + tracking_id + "/impactedResources/",
            "Microsoft.ResourceHealth/events/" + tracking_id + "/impactedResources/",
        )
        expected = next((item for item in prefixes if identity.casefold().startswith(item.casefold())), None)
        if expected is None or not identity[len(expected):] or "/" in identity[len(expected):]:
            return "Impacted-resource record identity is outside its subscription event."
        props = raw.get("properties")
        target = props.get("targetResourceId") if isinstance(props, dict) else None
        if isinstance(target, str) and target.casefold().startswith("/subscriptions/") and not target.casefold().startswith(("/subscriptions/" + config["subscription_id"] + "/").casefold()):
            return "Published target resource belongs to a different subscription."
    return None


def charge_evidence(page, evidence_budget, source_id):
    evidence_budget["bytes"] += len(json_text(page).encode("utf-8"))
    if evidence_budget["bytes"] > ARTIFACT_BYTES:
        raise EvidenceError("collected_evidence_too_large", "Accepted source evidence alone exceeds the complete JSON artifact bound; no fields were dropped and no report files were written.", source_id)


def read_pages(reader, initial, source_id, kind, config, tracking_id=None, evidence_budget=None):
    evidence_budget = evidence_budget if evidence_budget is not None else {"bytes": 0}
    receipt = {
        "source_id": source_id, "kind": kind,
        "included_event_types": list(EVENT_TYPES) if kind == "events" else None,
        "tracking_id": tracking_id, "subscription_id": config["subscription_id"],
        "api_version": API_VERSION, "status": "not_collected",
        "initial_request_url": initial, "records_received": 0, "records_accepted": 0,
        "records_excluded_by_scope": 0, "excluded_event_types": {},
        "pages": [], "errors": [], "redactions": [],
        "pagination_complete": False, "duplicate_native_ids": 0,
    }
    rows, visited, identities = [], set(), set()
    current = initial
    limit = MAX_EVENT_RECORDS if kind == "events" else MAX_SOURCE_RECORDS
    while len(receipt["pages"]) < MAX_PAGES:
        if current in visited:
            receipt["errors"].append(source_error("pagination_loop", "A continuation repeated an already-read page.", source_id))
            break
        visited.add(current)
        page = {"page": len(receipt["pages"]) + 1, "request_method": "GET", "request_url": current}
        receipt["pages"].append(page)
        try:
            result = reader.get(current, source_id)
        except EvidenceError as exc:
            page.update(exc.receipt or {})
            page["http_status"] = exc.http_status
            receipt["errors"].append(exc.document())
            charge_evidence(page, evidence_budget, source_id)
            break
        page.update({
            "http_status": result["http_status"], "observed_at_utc": result["observed_at_utc"],
            "attempts": result["attempts"],
        })
        if result["http_status"] != 200:
            page["response"] = copy.deepcopy(result["payload"])
            receipt["errors"].append(source_error("native_http_error", "Native source returned HTTP " + str(result["http_status"]) + "; this is not an empty inventory.", source_id, result["http_status"]))
            charge_evidence(page, evidence_budget, source_id)
            break
        payload = result["payload"]
        if not isinstance(payload, dict) or not isinstance(payload.get("value"), list):
            page["response"] = copy.deepcopy(payload)
            receipt["errors"].append(source_error("invalid_list_shape", "Native list response is missing its value array.", source_id, 200))
            charge_evidence(page, evidence_budget, source_id)
            break
        page["response"] = {key: copy.deepcopy(value) for key, value in payload.items() if key != "value"}
        accepted = []
        excluded = 0
        for index, raw in enumerate(payload["value"]):
            receipt["records_received"] += 1
            props = raw.get("properties") if isinstance(raw, dict) else None
            category = props.get("eventType") if isinstance(props, dict) else None
            if kind == "events" and isinstance(category, str) and category and category not in EVENT_TYPES:
                receipt["records_excluded_by_scope"] += 1
                receipt["excluded_event_types"][category] = receipt["excluded_event_types"].get(category, 0) + 1
                excluded += 1
                continue
            reason = record_in_scope(raw, kind, config, tracking_id)
            if reason:
                receipt["redactions"].append({"page": page["page"], "record_index": index, "reason": reason})
                continue
            accepted_index = len(accepted)
            accepted.append(copy.deepcopy(raw))
            native_id = raw["id"].casefold()
            if native_id in identities:
                receipt["duplicate_native_ids"] += 1
            identities.add(native_id)
            rows.append((copy.deepcopy(raw), {
                "source_id": source_id, "page": page["page"], "record_index": accepted_index,
                "original_record_index": index, "observed_at_utc": result["observed_at_utc"],
            }))
        page["response"]["value"] = accepted
        page["records_received"] = len(payload["value"])
        page["records_accepted"] = len(accepted)
        page["records_excluded_by_scope"] = excluded
        receipt["records_accepted"] = len(rows)
        charge_evidence(page, evidence_budget, source_id)
        if len(rows) > limit:
            receipt["errors"].append(source_error("source_record_bound", "The source record bound was exceeded; accepted returned records remain in the export but coverage is partial.", source_id))
            break
        if payload.get("error") is not None:
            receipt["errors"].append(source_error("partial_response", "Native response contains an error alongside its list; returned records are retained.", source_id))
            break
        continuation = payload.get("nextLink")
        if continuation in (None, ""):
            receipt["pagination_complete"] = True
            break
        page["continuation_received"] = True
        try:
            current = next_link(continuation, initial, config)
            page["continuation_query_start_restored"] = current != continuation
        except EvidenceError as exc:
            receipt["errors"].append(exc.document())
            break
    else:
        receipt["errors"].append(source_error("source_page_bound", "The per-list 25-page bound was reached with an outstanding continuation.", source_id))
    if receipt["redactions"]:
        receipt["errors"].append(source_error("source_scope_violation", "Unexpected records were redacted from this nonsensitive subscription-only export; inspect the redaction ledger.", source_id))
    if receipt["duplicate_native_ids"]:
        receipt["errors"].append(source_error("duplicate_native_ids", "Repeated native IDs were retained as separate observations; unique-event completeness is uncertain.", source_id))
    if receipt["errors"]:
        first_status = receipt["errors"][0].get("http_status")
        not_collected = receipt["errors"][0]["code"] == "not_collected_in_replay"
        receipt["status"] = "partial" if rows else "not_collected" if not_collected else "denied" if first_status in (401, 403) else "unavailable"
    else:
        receipt["status"] = "complete" if rows else "successful_empty_in_scope" if receipt["records_excluded_by_scope"] else "successful_empty"
    return rows, receipt


def source_time(value):
    if not isinstance(value, str) or not value:
        return None
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return result.astimezone(timezone.utc) if result.tzinfo is not None else None


def clock_key(value):
    parsed = source_time(value)
    if parsed is None:
        return None
    match = re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.(\d{1,9}))?(?:Z|[+-]\d{2}:\d{2})", value)
    if match is None:
        return None
    elapsed = parsed - datetime(1970, 1, 1, tzinfo=timezone.utc)
    fraction = int(((match[1] or "") + "000000000")[:9])
    return (elapsed.days * 86_400 + elapsed.seconds) * 1_000_000_000 + fraction


def source_utc_display(value):
    if clock_key(value) is None:
        return None
    parsed = source_time(value).replace(microsecond=0)
    fraction = re.search(r"\.(\d+)", value)
    return iso(parsed).removesuffix("Z") + ("." + fraction[1] if fraction else "") + "Z"


def scalar(value):
    if isinstance(value, (str, int, float, bool)):
        return str(value)
    return None


def normalize_event(raw, ref, params, reference, key):
    props = raw["properties"]
    uncertain = []
    times = {}
    for field in ("impactStartTime", "impactMitigationTime", "lastUpdateTime"):
        original = props.get(field)
        times[field] = clock_key(original)
        if times[field] is None:
            uncertain.append(field + " missing/invalid; original value retained.")
    status = props.get("status") if props.get("status") in ("Active", "Resolved") else "Unknown"
    if status == "Unknown":
        uncertain.append("Native current status missing/unrecognized.")
    start, end = clock_key(params["window"]["start_utc"]), clock_key(params["window"]["end_utc_exclusive"])
    reference_key = clock_key(iso(reference))
    updated = times["lastUpdateTime"]
    impact_start = times["impactStartTime"]
    mitigation = times["impactMitigationTime"]
    if impact_start is None:
        timing = "unknown"
    elif mitigation is not None and mitigation < impact_start:
        timing = "inconsistent_source_dates"
        uncertain.append("Source mitigation precedes impact start; no ongoing/future interval is established.")
    elif impact_start > reference_key:
        timing = "future_published_start"
    elif mitigation is not None and mitigation <= reference_key:
        timing = "source_mitigation_at_or_before_reference"
    elif mitigation is not None:
        timing = "between_source_start_and_mitigation"
    else:
        timing = "published_start_without_mitigation"
    if status == "Active" and timing == "source_mitigation_at_or_before_reference":
        uncertain.append("Native status is Active but source mitigation is at/before the reference; ongoing impact is not established.")
    services, regions = [], []
    impact = props.get("impact")
    if isinstance(impact, list):
        for item in impact:
            if not isinstance(item, dict):
                continue
            service = scalar(item.get("impactedService"))
            if service and service not in services:
                services.append(service)
            region_items = item.get("impactedRegions")
            if isinstance(region_items, list):
                for region_item in region_items:
                    region = scalar(region_item.get("impactedRegion")) if isinstance(region_item, dict) else None
                    if region and region not in regions:
                        regions.append(region)
    if not services:
        uncertain.append("No structured impacted service supplied.")
    if not regions:
        uncertain.append("No structured impacted region supplied.")
    if updated is not None and updated > reference_key:
        uncertain.append("lastUpdateTime is later than the run reference; the read is not an atomic as-of snapshot.")
    return {
        "event_key": key, "id": raw["id"], "tracking_id": raw["name"],
        "event_type": props["eventType"], "native_status": status,
        "title": scalar(props.get("title")) or "Untitled source event",
        "summary": scalar(props.get("summary")), "description": scalar(props.get("description")),
        "event_level": scalar(props.get("eventLevel")), "event_source": scalar(props.get("eventSource")),
        "impact_start_original": props.get("impactStartTime"), "mitigation_time_original": props.get("impactMitigationTime"),
        "last_update_original": props.get("lastUpdateTime"),
        "impact_start_utc": source_utc_display(props.get("impactStartTime")),
        "mitigation_time_utc": source_utc_display(props.get("impactMitigationTime")),
        "last_update_utc": source_utc_display(props.get("lastUpdateTime")),
        "services": services, "regions": regions, "source_ref": ref,
        "published_timing": timing,
        "temporal": {
            "requested_updates": updated is not None and start <= updated < end,
            "active_now": status == "Active",
            "future_maintenance": props["eventType"] == "PlannedMaintenance" and status != "Resolved" and timing == "future_published_start",
        },
        "newness": "not_established", "support_case_reference": "not_collected",
        "uncertainties": uncertain, "resource_source_id": None, "resource_source_status": "not_collected", "resource_records": None,
    }


def normalize_resource(raw, ref, event, key):
    props = raw.get("properties") if isinstance(raw.get("properties"), dict) else {}
    target = scalar(props.get("targetResourceId"))
    return {
        "resource_key": key, "event_key": event["event_key"], "event_id": event["id"],
        "tracking_id": event["tracking_id"], "id": raw["id"],
        "target_resource_id": target, "target_resource_type": scalar(props.get("targetResourceType")),
        "target_region": scalar(props.get("targetRegion")), "source_ref": ref,
        "association": "published_potential_impact", "workload_outage": "not_measured",
        "uncertainties": [] if target else ["Source supplied no targetResourceId; record retained, not a resolved resource identity."],
    }


def collect(reader, config, params, reference, provenance="LIVE"):
    sources, events, resources = [], [], []
    evidence_budget = {"bytes": 0}
    initial = events_url(config, params["source_query_start_utc"])
    rows, receipt = read_pages(reader, initial, "events:subscription", "events", config, evidence_budget=evidence_budget)
    receipt["query_start_utc"] = params["source_query_start_utc"]
    receipt["time_basis"] = "lastUpdateTime lower bound; no source upper-bound/as-of guarantee"
    sources.append(receipt)
    for raw, ref in rows:
        events.append(normalize_event(raw, ref, params, reference, "event-" + str(len(events) + 1)))
    resource_receipts = {}
    for event in events:
        identity = event["tracking_id"].casefold()
        if identity not in resource_receipts:
            source_id = "resources:" + event["tracking_id"]
            rows, receipt = read_pages(reader, resources_url(config, event["tracking_id"]), source_id, "impactedResources", config, event["tracking_id"], evidence_budget)
            sources.append(receipt)
            resource_receipts[identity] = (rows, receipt)
        rows, receipt = resource_receipts[identity]
        event["resource_source_id"] = receipt["source_id"]
        event["resource_source_status"] = receipt["status"]
        event["resource_records"] = len(rows) if receipt["status"] in COMPLETE_SOURCE_STATUSES else None
        event["resource_records_observed"] = len(rows)
        if event["resource_records"] is None:
            event["uncertainties"].append("Impacted-resource source is incomplete; observed rows are a lower bound, not zero/full scope.")
        for raw, ref in rows:
            resources.append(normalize_resource(raw, ref, event, "resource-" + str(len(resources) + 1)))
    event_sources = [source for source in sources if source["kind"] == "events"]
    all_complete = all(source["status"] in COMPLETE_SOURCE_STATUSES for source in sources)
    observed_times = [page["observed_at_utc"] for source in sources for page in source["pages"] if "observed_at_utc" in page]
    updates = [(clock_key(event["last_update_original"]), event["last_update_original"]) for event in events if clock_key(event["last_update_original"]) is not None]
    return {
        "schema_version": "service-health-events-v1", "provenance": provenance,
        "client_name": config["client_name"], "subscription_id": config["subscription_id"],
        "reference_utc": iso(reference), "requested_window": params["window"],
        "collection_observed_utc": {"first": min(observed_times) if observed_times else None, "last": max(observed_times) if observed_times else None},
        "observed_last_update_extent": {
            "first_original": min(updates, key=lambda item: item[0])[1] if updates else None,
            "last_original": max(updates, key=lambda item: item[0])[1] if updates else None,
            "records_with_valid_time": len(updates), "missing_or_invalid": len(events) - len(updates),
            "meaning": "Extent of accepted observed records, not complete historical coverage.",
        },
        "source_query": {
            "query_start_utc": params["source_query_start_utc"], "basis": "lastUpdateTime",
            "lookback_days": (reference - source_time(params["source_query_start_utc"])).total_seconds() / 86_400,
            "upper_bound": "not_supported", "category_selection": "Fixed client-side ServiceIssue / PlannedMaintenance; no unsupported eventType OData filter.",
            "retention": "Portal history 90 days; backend up to one year, not a completeness guarantee.",
            "active_scope": "Source-observed current Active records within returned retained data, regardless of impact-start month.",
        },
        "coverage": {
            "status": "complete_returned_pages" if all_complete else "partial",
            "historical_completeness": "not_proven", "current_state_as_of_history": "not_reconstructed",
            "newness": "not_established_without_baseline_or_reliable_publication_time",
            "event_source_successful_empty": all(source["status"] in ("successful_empty", "successful_empty_in_scope") for source in event_sources),
            "empty_meaning": "Successful-empty source validation only; no resilience or workload-health claim.",
            "support_cases": "not_collected", "workload_outages": "not_measured",
            "redacted_records": sum(len(source["redactions"]) for source in sources),
            "excluded_category_records": sum(source["records_excluded_by_scope"] for source in event_sources),
        },
        "events": events, "impacted_resources": resources, "sources": sources,
    }


def summary(snapshot):
    events = snapshot["events"]
    return {
        "event_records": len(events), "distinct_event_ids": len({event["id"].casefold() for event in events}),
        "native_event_records_received": sum(source["records_received"] for source in snapshot["sources"] if source["kind"] == "events"),
        "excluded_category_records": snapshot["coverage"]["excluded_category_records"],
        "service_issue_records": sum(event["event_type"] == "ServiceIssue" for event in events),
        "planned_maintenance_records": sum(event["event_type"] == "PlannedMaintenance" for event in events),
        "requested_update_records": sum(event["temporal"]["requested_updates"] for event in events),
        "active_observed_records": sum(event["temporal"]["active_now"] for event in events),
        "future_maintenance_records": sum(event["temporal"]["future_maintenance"] for event in events),
        "impacted_resource_records": len(snapshot["impacted_resources"]),
        "incomplete_sources": sum(source["status"] not in COMPLETE_SOURCE_STATUSES for source in snapshot["sources"]),
    }


def matches(event, params):
    if params["event_type"] != "all" and event["event_type"] != params["event_type"]:
        return False
    if params["state"] != "all" and event["native_status"] != params["state"]:
        return False
    if params["time_scope"] != "all" and not event["temporal"][params["time_scope"]]:
        return False
    haystack = " ".join([event["id"], event["tracking_id"], event["title"], event["summary"] or "", *event["services"], *event["regions"]])
    return params["search"].casefold() in haystack.casefold()


def event_projection(event):
    return {key: event[key] for key in (
        "event_key", "tracking_id", "event_type", "native_status", "title", "last_update_original",
        "impact_start_original", "temporal", "resource_records", "resource_records_observed", "newness", "source_ref",
        "published_timing", "resource_source_id", "resource_source_status",
    )}


def query_snapshot(snapshot, params):
    selected = [event for event in snapshot["events"] if matches(event, params)]
    if params["view"] == "summary":
        rows = [summary(snapshot)]
    elif params["view"] == "events":
        rows = [event_projection(event) for event in selected]
    elif params["view"] == "resources":
        keys = {event["event_key"] for event in selected}
        rows = [row for row in snapshot["impacted_resources"] if row["event_key"] in keys]
    else:
        rows = [{
            "source_id": source["source_id"], "status": source["status"], "records_received": source["records_received"],
            "records_accepted": source["records_accepted"], "pages_attempted": len(source["pages"]),
            "pagination_complete": source["pagination_complete"], "errors": source["errors"],
            "redacted_records": len(source["redactions"]),
            "records_excluded_by_scope": source["records_excluded_by_scope"], "excluded_event_types": source["excluded_event_types"],
        } for source in snapshot["sources"]]
    result = {
        "status": "partial" if snapshot["coverage"]["status"] == "partial" else "ok",
        "operation": "query", "view": params["view"], "provenance": snapshot["provenance"],
        "reference_utc": snapshot["reference_utc"], "requested_window": snapshot["requested_window"],
        "source_query_start_utc": snapshot["source_query"]["query_start_utc"],
        "collection_observed_utc": snapshot["collection_observed_utc"],
        "historical_completeness": "not_proven", "fresh_collection": True,
        "total_matched": len(rows), "requested_limit": params["limit"], "offset": params["offset"],
        "returned": 0, "has_more": False, "next_offset": None, "transport_capped": False, "rows": [],
    }
    desired = rows[params["offset"]:params["offset"] + params["limit"]]
    for row in desired:
        proposed = copy.deepcopy(result)
        proposed["rows"].append(row)
        proposed["returned"] += 1
        consumed = params["offset"] + proposed["returned"]
        proposed["has_more"] = consumed < len(rows)
        proposed["next_offset"] = consumed if proposed["has_more"] else None
        proposed["transport_capped"] = proposed["returned"] < len(desired)
        if response_bytes(proposed) > TRANSPORT_BYTES:
            if not result["rows"]:
                raise EvidenceError("query_row_too_large", "One complete projected row exceeds the chat budget. Request a report and inspect its complete JSON; no zero-row cursor is returned.", "transport")
            result["transport_capped"] = True
            break
        result = proposed
    return budget_response(result)


def source_record(snapshot, ref):
    source = next(item for item in snapshot["sources"] if item["source_id"] == ref["source_id"])
    page = source["pages"][ref["page"] - 1]
    return page["response"]["value"][ref["record_index"]]


def complete_event(snapshot, event):
    return {**event, "source_record": source_record(snapshot, event["source_ref"])}


def complete_resource(snapshot, resource):
    return {**resource, "source_record": source_record(snapshot, resource["source_ref"])}


EVENT_CSV_FIELDS = (
    "provenance", "subscription_id", "api_version", "reference_utc", "event_feed_query_start_utc", "requested_start_utc", "requested_end_utc_exclusive",
    "event_key", "id", "tracking_id", "event_type", "native_status", "published_timing", "title", "event_level",
    "services", "regions", "impact_start_original", "mitigation_time_original", "last_update_original",
    "requested_updates", "active_observed", "future_maintenance", "newness", "resource_records",
    "resource_records_observed", "resource_source_id", "resource_source_status", "source_id", "observed_at_utc", "details_json",
)
RESOURCE_CSV_FIELDS = (
    "provenance", "subscription_id", "api_version", "reference_utc", "event_feed_query_start_utc", "requested_start_utc", "requested_end_utc_exclusive",
    "resource_key", "id", "event_key", "tracking_id", "target_resource_id", "target_resource_type", "target_region",
    "association", "workload_outage", "source_id", "observed_at_utc", "details_json",
)


def csv_cell(value):
    if value is None:
        return ""
    text = json_text(value) if isinstance(value, (dict, list, bool)) else str(value)
    if text.startswith(("\t", "\r", "\n")) or text.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + text
    return text


def csv_document(rows, fields):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\r\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({field: csv_cell(row.get(field)) for field in fields})
    return stream.getvalue()


def csv_rows(snapshot):
    context = {
        "provenance": snapshot["provenance"], "subscription_id": snapshot["subscription_id"], "api_version": API_VERSION,
        "reference_utc": snapshot["reference_utc"], "event_feed_query_start_utc": snapshot["source_query"]["query_start_utc"],
        "requested_start_utc": snapshot["requested_window"]["start_utc"],
        "requested_end_utc_exclusive": snapshot["requested_window"]["end_utc_exclusive"],
    }
    events = [{
        **context, **event, "services": event["services"], "regions": event["regions"],
        "requested_updates": event["temporal"]["requested_updates"], "active_observed": event["temporal"]["active_now"],
        "future_maintenance": event["temporal"]["future_maintenance"],
        "source_id": event["source_ref"]["source_id"], "observed_at_utc": event["source_ref"]["observed_at_utc"],
        "details_json": complete_event(snapshot, event),
    } for event in snapshot["events"]]
    resources = [{
        **context, **resource, "source_id": resource["source_ref"]["source_id"],
        "observed_at_utc": resource["source_ref"]["observed_at_utc"], "details_json": complete_resource(snapshot, resource),
    } for resource in snapshot["impacted_resources"]]
    return events, resources


def safe_script_json(value):
    return json_text(value).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")


def json_byte_ranges(snapshot, document, requested_paths):
    paths = set(requested_paths)
    prefixes = {path[:length] for path in paths for length in range(len(path) + 1)}
    chunks, ranges, position = [], {}, 0

    def emit(value):
        nonlocal position
        chunks.append(value)
        position += len(value)

    def walk(value, path=()):
        if len(path) > 100:
            raise EvidenceError("json_reference_depth", "Source JSON references exceed the bounded nesting depth.", "artifact_encoding")
        start = position
        if path not in prefixes:
            emit(json_text(value).encode("utf-8"))
        elif isinstance(value, dict):
            emit(b"{")
            for index, (key, child) in enumerate(value.items()):
                if index:
                    emit(b",")
                emit(json_text(key).encode("utf-8") + b":")
                walk(child, (*path, key))
            emit(b"}")
        elif isinstance(value, list):
            emit(b"[")
            for index, child in enumerate(value):
                if index:
                    emit(b",")
                walk(child, (*path, index))
            emit(b"]")
        else:
            emit(json_text(value).encode("utf-8"))
        if path in paths:
            ranges[path] = [start, position]

    walk(snapshot)
    if paths != ranges.keys() or b"".join(chunks) + b"\n" != document:
        raise EvidenceError("json_reference_mismatch", "Render references do not match the exact complete JSON bytes; no alternate snapshot was accepted.", "artifact_encoding")
    return ranges


def render_html(snapshot, document, branding):
    if EVENT_CSV_FIELDS[-1] != "details_json" or RESOURCE_CSV_FIELDS[-1] != "details_json":
        raise EvidenceError("invalid_csv_render_contract", "Complete CSV details must remain the final column in the render contract.", "artifact_encoding")
    event_rows, resource_rows = csv_rows(snapshot)
    source_indices = {source["source_id"]: index for index, source in enumerate(snapshot["sources"])}
    if len(source_indices) != len(snapshot["sources"]):
        raise EvidenceError("ambiguous_source_reference", "Source IDs must be unique for exact report references.", "artifact_encoding")

    def raw_path(row):
        ref = row["source_ref"]
        return ("sources", source_indices[ref["source_id"]], "pages", ref["page"] - 1, "response", "value", ref["record_index"])

    requested_paths = [("sources", index) for index in range(len(snapshot["sources"]))]
    for collection in ("events", "impacted_resources"):
        for index, row in enumerate(snapshot[collection]):
            requested_paths.extend(((collection, index), raw_path(row)))
    ranges = json_byte_ranges(snapshot, document, requested_paths)
    model = {
        "context": {key: snapshot[key] for key in ("schema_version", "provenance", "client_name", "subscription_id", "reference_utc", "requested_window", "collection_observed_utc", "observed_last_update_extent", "source_query", "coverage")},
        "summary": summary(snapshot), "events": [], "resources": [], "sources": [],
        "event_csv_fields": EVENT_CSV_FIELDS, "resource_csv_fields": RESOURCE_CSV_FIELDS,
        "source_json_bytes": len(document),
    }
    # Store source JSON once; UTF-8 byte references preserve every numeric lexeme.
    for index, (event, row) in enumerate(zip(snapshot["events"], event_rows)):
        model["events"].append({
            **event, "record_range": ranges[("events", index)], "source_record_range": ranges[raw_path(event)],
            "csv_cells": [csv_cell(row.get(field)) for field in EVENT_CSV_FIELDS if field != "details_json"],
        })
    for index, (resource, row) in enumerate(zip(snapshot["impacted_resources"], resource_rows)):
        model["resources"].append({
            **resource, "record_range": ranges[("impacted_resources", index)], "source_record_range": ranges[raw_path(resource)],
            "csv_cells": [csv_cell(row.get(field)) for field in RESOURCE_CSV_FIELDS if field != "details_json"],
        })
    for index, source in enumerate(snapshot["sources"]):
        receipt = {
            key: value for key, value in source.items() if key != "pages"
        } | {
            "pages": [{
                **{key: value for key, value in page.items() if key != "response"},
                "response_metadata": {key: value for key, value in page["response"].items() if key != "value"}
                if isinstance(page.get("response"), dict) else page.get("response"),
            } for page in source["pages"]],
        }
        model["sources"].append({
            **receipt, "receipt_json": json_text(receipt),
            "detail_range": ranges[("sources", index)],
        })
    return (
        HTML_TEMPLATE.replace("__CLIENT_NAME__", html.escape(snapshot["client_name"], quote=True))
        .replace("__COMPANY_LOGO__", branding)
        .replace("__FULL_JSON_BASE64__", base64.b64encode(document).decode("ascii"))
        .replace("__UI_MODEL_JSON__", safe_script_json(model))
    )


def artifact_directory():
    try:
        cwd = Path.cwd()
        root = cwd.resolve(strict=True)
        linked = any(part.is_symlink() or getattr(part, "is_junction", lambda: False)() for part in (cwd, *cwd.parents))
    except (OSError, RuntimeError) as exc:
        raise EvidenceError("unsafe_artifact_root", "Runtime cwd must resolve to an existing directory.", "artifact_storage") from exc
    if root == Path(root.anchor) or not root.is_dir() or linked:
        raise EvidenceError("unsafe_artifact_root", "Root directories and symlink/junction cwd ancestors are forbidden.", "artifact_storage")
    if OUTPUT_DIRECTORY != "service-health-reports":
        raise EvidenceError("unsafe_artifact_directory", "Only the fixed service-health-reports child is allowed.", "artifact_storage")
    directory = root / OUTPUT_DIRECTORY
    if directory.is_symlink() or getattr(directory, "is_junction", lambda: False)() or directory.resolve() != directory:
        raise EvidenceError("unsafe_artifact_directory", "Output folder is a link/junction or escapes the actual cwd.", "artifact_storage")
    return root, directory


SUFFIXES = {
    "report_path": ".html", "snapshot_path": "-snapshot.json",
    "events_csv_path": "-events.csv", "resources_csv_path": "-impacted-resources.csv",
}


def sharing_fields(root, paths):
    result = {"sharing_mode": "local_files_only", "http_verified": False}
    match = re.fullmatch(r"/(?:root/sreagent|usr)/terminalRoot/tmp/ThreadFiles/([0-9a-fA-F-]{36})", root.as_posix())
    if match is None:
        return result
    try:
        if str(UUID(match[1])) != match[1].lower():
            return result
    except ValueError:
        return result
    if set(paths) != set(SUFFIXES):
        raise EvidenceError("unsafe_sharing_path", "Exactly the four generated artifacts are required.", "artifact_storage")
    stem = paths["report_path"].name.removesuffix(".html")
    if re.fullmatch(r"(?:service-health|simulated-service-health)-[0-9]{8}T[0-9]{6}Z-[0-9a-f]{12}", stem) is None:
        raise EvidenceError("unsafe_sharing_path", "Native aliases require this tool's generated filenames.", "artifact_storage")
    for key, suffix in SUFFIXES.items():
        path = paths[key]
        if path.parent != root / OUTPUT_DIRECTORY or path.name != stem + suffix:
            raise EvidenceError("unsafe_sharing_path", "Native aliases must point to one guarded run under the actual runtime cwd.", "artifact_storage")
        result[key.removesuffix("_path") + "_url"] = "/api/files/tmp/ThreadFiles/" + match[1] + "/" + OUTPUT_DIRECTORY + "/" + quote(path.name, safe="")
    result["sharing_mode"] = "native_ui"
    return result


def report_envelope(snapshot, root, paths):
    return budget_response({
        "status": "partial" if snapshot["coverage"]["status"] == "partial" else "ok",
        "operation": "report", "artifact_status": "written", "provenance": snapshot["provenance"],
        "reference_utc": snapshot["reference_utc"], "requested_window": snapshot["requested_window"],
        "source_query_start_utc": snapshot["source_query"]["query_start_utc"],
        "historical_completeness": "not_proven", "newness": "not_established",
        "empty_source_validation_only": snapshot["coverage"]["event_source_successful_empty"],
        "summary": summary(snapshot), **{key: str(path) for key, path in paths.items()},
        **sharing_fields(root, paths),
    })


def prepare_artifacts(snapshot, branding):
    text = json_text(snapshot) + "\n"
    if json.loads(text) != snapshot:
        raise EvidenceError("json_round_trip_failed", "Complete source-qualified JSON failed its round-trip check.", "artifact_encoding")
    document = text.encode("utf-8")
    event_rows, resource_rows = csv_rows(snapshot)
    files = {
        "snapshot_path": document,
        "report_path": render_html(snapshot, document, branding).encode("utf-8"),
        "events_csv_path": csv_document(event_rows, EVENT_CSV_FIELDS).encode("utf-8-sig"),
        "resources_csv_path": csv_document(resource_rows, RESOURCE_CSV_FIELDS).encode("utf-8-sig"),
    }
    if any(len(data) > ARTIFACT_BYTES for data in files.values()):
        raise EvidenceError("artifact_size_exceeded", "A complete plain artifact exceeds 4800000 bytes. No file was written, no records/window were dropped and no ZIP/Blob substitute was created.", "artifact_storage")
    return files


def write_report(snapshot, branding):
    root, directory = artifact_directory()
    prefix = "simulated-service-health" if snapshot["provenance"] == "SIMULATED" else "service-health"
    stem = prefix + "-" + snapshot["reference_utc"].replace("-", "").replace(":", "") + "-" + uuid4().hex[:12]
    paths = {key: directory / (stem + suffix) for key, suffix in SUFFIXES.items()}
    result = report_envelope(snapshot, root, paths)
    files = prepare_artifacts(snapshot, branding)
    temporary, written = [], []
    try:
        directory.mkdir(exist_ok=True)
        if artifact_directory()[1] != directory or not directory.is_dir() or directory.resolve(strict=True) != directory:
            raise EvidenceError("unsafe_artifact_directory", "Output folder changed during creation.", "artifact_storage")
        for key, data in files.items():
            if paths[key].exists() or paths[key].is_symlink():
                raise EvidenceError("artifact_collision", "A generated path already exists; no overwrite is allowed.", "artifact_storage")
            fd, filename = tempfile.mkstemp(prefix=stem + "-", suffix=".tmp", dir=directory)
            pending = Path(filename)
            temporary.append(pending)
            with os.fdopen(fd, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(pending, paths[key])
            temporary.remove(pending)
            written.append(paths[key])
        if any(path.read_bytes() != files[key] for key, path in paths.items()):
            raise EvidenceError("artifact_readback_failed", "Written artifact bytes differ from the complete prepared documents.", "artifact_storage")
    except (OSError, EvidenceError) as exc:
        failed = []
        for path in temporary + written:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                failed.append(path.name)
        if failed:
            raise EvidenceError("artifact_cleanup_failed", "Artifact write failed and generated-file cleanup also failed; inspect: " + ", ".join(failed), "artifact_storage") from exc
        if isinstance(exc, EvidenceError):
            raise
        raise EvidenceError("artifact_write_failed", "Atomic artifact write/readback failed; this run's partial files were removed.", "artifact_storage") from exc
    return result


def main(operation: str = "report", period: str = "auto", start_utc: str = "", end_utc: str = "",
         view: str = "summary", event_type: str = "all", state: str = "all", time_scope: str = "all",
         search: str = "", limit: int = 10, offset: int = 0):
    """Runtime entry point. No live fixture, environment override or arbitrary path input."""
    try:
        reference = utc_now().replace(microsecond=0)
        params = parameters(operation, period, start_utc, end_utc, view, event_type, state, time_scope, search, limit, offset, reference)
        config = configuration()
        branding = logo_markup()
        if operation == "report":
            artifact_directory()
        reader = NativeReader(config)
        try:
            snapshot = collect(reader, config, params, reference)
        finally:
            reader.close()
        if operation == "report":
            return write_report(snapshot, branding)
        return query_snapshot(snapshot, params)
    except EvidenceError as exc:
        return budget_response({"status": "error", "operation": operation if operation in ("report", "query") else "invalid", "error": exc.document()})
