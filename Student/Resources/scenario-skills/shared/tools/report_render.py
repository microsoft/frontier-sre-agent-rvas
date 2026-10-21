"""
report_render: Build one self contained HTML posture report for any SRE skill.

Azure SRE Agent Python tool, shared across skills. Renders a single self
contained HTML file with no external assets, no CDN, and no image dependencies.
All styling is inline CSS and every chart is drawn with plain HTML and CSS bars,
so the report opens fully styled offline. Writes the report to OUTPUT_DIR and
returns the file path.

It reads one report_data object as JSON on standard input and renders, in order:
summary cards, horizontal bar charts, a sortable and filterable findings table,
an optional action candidates table with copyable commands, and a method and
limits panel. See any skill's references/report-layout.md for the input shape.

Standard library only (html, json, os, sys, datetime). No third party packages.
"""

import argparse
import html
import json
import os
import sys
from datetime import datetime, timezone

OUTPUT_DIR = os.environ.get("SRE_REPORT_OUTPUT_DIR", "/mnt/data")

# Severity and confidence render as CSS classes so the palette adapts to the
# light and dark themes. The colours live in THEME_CSS as CSS variables.
SEVERITY_ORDER = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3, "Info": 4}
SEVERITY_CLASS = {
    "Critical": "s-critical",
    "High": "s-high",
    "Medium": "s-medium",
    "Low": "s-low",
    "Info": "s-info",
}
SEVERITY_VAR = {
    "Critical": "var(--sev-critical)",
    "High": "var(--sev-high)",
    "Medium": "var(--sev-medium)",
    "Low": "var(--sev-low)",
    "Info": "var(--sev-info)",
}
CONFIDENCE_CLASS = {"Very high": "c-vhigh", "High": "c-high", "Medium": "c-medium", "Low": "c-low"}
CONFIDENCE_VAR = {
    "Very high": "var(--conf-very-high)",
    "High": "var(--conf-high)",
    "Medium": "var(--conf-medium)",
    "Low": "var(--conf-low)",
}


def _sev_var(band):
    return SEVERITY_VAR.get(band, "var(--accent)")


def _esc(value):
    return html.escape("" if value is None else str(value), quote=True)


def _num(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return _esc(value)
    if number == int(number):
        return f"{int(number):,}"
    return f"{number:,.2f}"


def _severity_pill(band):
    band = band if band in SEVERITY_CLASS else "Info"
    return f"<span class='pill {SEVERITY_CLASS[band]}'>{_esc(band)}</span>"


def _confidence_pill(band):
    band = band if band in CONFIDENCE_CLASS else "Medium"
    return f"<span class='pill {CONFIDENCE_CLASS[band]}'>{_esc(band)}</span>"


def _summary_cards(cards):
    if not cards:
        return ""
    out = []
    for card in cards:
        sub = card.get("sub")
        sub_html = f"<div class='card-sub'>{_esc(sub)}</div>" if sub else ""
        out.append(
            "<div class='card'>"
            f"<div class='card-label'>{_esc(card.get('label', ''))}</div>"
            f"<div class='card-value'>{_esc(card.get('value', ''))}</div>"
            f"{sub_html}</div>"
        )
    return f"<div class='cards'>{''.join(out)}</div>"


def _bar_chart(chart):
    items = [item for item in chart.get("items", []) if item]
    title = chart.get("title", "")
    unit = chart.get("unit", "")
    if not items:
        return f"<div class='panel'><div class='group-title'>{_esc(title)}</div><p class='small'>No data.</p></div>"
    top = max(float(item.get("value", 0) or 0) for item in items) or 1.0
    rows = []
    for item in items:
        value = float(item.get("value", 0) or 0)
        width = max(2.0, value / top * 100.0)
        band = item.get("band")
        colour = _sev_var(band)
        label = f"{_num(value)} {unit}".strip()
        rows.append(
            "<div class='chart-row'>"
            f"<div class='chart-name'>{_esc(item.get('name', ''))}</div>"
            f"<div class='chart-bar'><div style='width:{width:.1f}%;background:{colour}'></div></div>"
            f"<div class='chart-score'>{_esc(label)}</div></div>"
        )
    return f"<div class='panel'><div class='group-title'>{_esc(title)}</div>{''.join(rows)}</div>"


def _normalise_columns(columns):
    normalised = []
    for column in columns or []:
        if isinstance(column, dict):
            normalised.append((column.get("key"), column.get("label", column.get("key", ""))))
        else:
            key = str(column)
            normalised.append((key, key.replace("_", " ").title()))
    return normalised


def _sortable_header(label):
    return (
        "<th scope='col'><button type='button' class='sort-header' "
        "onclick='sortTable(this.closest(\"th\"))' "
        f"aria-label='Sort by {_esc(label)}'>{_esc(label)}</button></th>"
    )


def _findings_table(findings):
    rows = findings.get("rows", []) if findings else []
    if not rows:
        return ""
    title = findings.get("title", "Findings")
    columns = _normalise_columns(findings.get("columns"))
    if not columns:
        keys = []
        for row in rows:
            for key in row.keys():
                if not key.startswith("_") and key not in keys:
                    keys.append(key)
        columns = _normalise_columns(keys)

    has_command = any(row.get("_command") for row in rows)
    header_cells = "".join(
        _sortable_header(label) for _, label in columns
    )
    if has_command:
        header_cells += "<th>Command</th>"

    body = []
    for row in rows:
        band = row.get("_band") or row.get("severity") or row.get("priority")
        cells = []
        for key, _ in columns:
            value = row.get(key, "")
            if key in ("severity", "priority", "band") and value:
                cells.append(f"<td data-sort='{SEVERITY_ORDER.get(str(value), 9)}'>{_severity_pill(str(value))}</td>")
            else:
                cells.append(f"<td>{_esc(value)}</td>")
        if has_command:
            command = row.get("_command")
            if command:
                cells.append(
                    "<td class='cmd'><code>" + _esc(command) + "</code>"
                    f"<button class='copy' onclick=\"copyCmd(this)\" data-cmd='{_esc(command)}'>copy</button></td>"
                )
            else:
                cells.append("<td></td>")
        band_str = str(band) if band else ""
        border = _sev_var(band_str) if band_str else "var(--border-2)"
        body.append(
            f"<tr data-band='{_esc(band_str)}' style='border-left:3px solid {border}'>{''.join(cells)}</tr>"
        )

    sev_present = [
        s for s in ("Critical", "High", "Medium", "Low", "Info")
        if any((row.get("_band") or row.get("severity") or row.get("priority")) == s for row in rows)
    ]
    sev_select = ""
    if sev_present:
        options = "".join(f"<option value='{_esc(s)}'>{_esc(s)}</option>" for s in sev_present)
        sev_select = (
            "<select id='findingsSev' aria-label='Filter by severity' onchange='filterFindings()'>"
            f"<option value=''>All severities</option>{options}</select>"
        )
    return (
        f"<div class='group-title'>{_esc(title)}</div>"
        "<div class='controls'>"
        f"{sev_select}"
        "<input class='filter' id='findingsText' aria-label='Search findings' onkeyup='filterFindings()' placeholder='Filter findings...'>"
        "<span class='count' id='findings-count'></span>"
        "</div>"
        "<div class='table-scroll' tabindex='0' role='region' aria-label='Findings table'>"
        f"<table id='findings' class='data'><thead><tr>{header_cells}</tr></thead>"
        f"<tbody>{''.join(body)}</tbody></table></div>"
    )


def _candidates_table(candidates):
    rows = [c for c in (candidates or []) if c and not c.get("excluded")]
    if not rows:
        return ""
    show_saving = any(c.get("monthly_saving") not in (None, "") for c in rows)
    subs = sorted({str(c.get("subscription", "")) for c in rows if c.get("subscription")})
    sub_options = "".join(f"<option value='{_esc(s)}'>{_esc(s)}</option>" for s in subs)

    head = ["Resource", "Type", "Subscription", "Resource group", "Confidence"]
    if show_saving:
        head.append("Est. monthly")
    head += ["Reason", "Next step", "Command"]
    header_cells = "".join(_sortable_header(h) for h in head)

    body = []
    for candidate in rows:
        band = candidate.get("band") or "Medium"
        command = candidate.get("command") or candidate.get("delete_command") or ""
        cells = [
            f"<td>{_esc(candidate.get('resource', ''))}</td>",
            f"<td>{_esc(candidate.get('resource_type', ''))}</td>",
            f"<td>{_esc(candidate.get('subscription', ''))}</td>",
            f"<td>{_esc(candidate.get('resource_group', ''))}</td>",
            f"<td data-sort='{_esc(candidate.get('confidence', 0))}'>{_confidence_pill(band)}</td>",
        ]
        if show_saving:
            note = candidate.get("saving_note", "")
            note_html = f"<div class='card-sub'>{_esc(note)}</div>" if note else ""
            cells.append(f"<td>{_num(candidate.get('monthly_saving', 0))}{note_html}</td>")
        cells.append(f"<td>{_esc(candidate.get('reason', ''))}</td>")
        cells.append(f"<td>{_esc(candidate.get('next_step', ''))}</td>")
        if command:
            cells.append(
                "<td class='cmd'><code>" + _esc(command) + "</code>"
                f"<button class='copy' onclick=\"copyCmd(this)\" data-cmd='{_esc(command)}'>copy</button></td>"
            )
        else:
            cells.append("<td></td>")
        body.append(
            f"<tr data-sub='{_esc(candidate.get('subscription', ''))}' data-band='{_esc(band)}'>"
            f"{''.join(cells)}</tr>"
        )

    return (
        "<div class='group-title'>Action candidates</div>"
        "<div class='controls'>"
        f"<select onchange=\"filterCandidates()\" id='candSub' aria-label='Candidate subscription'><option value=''>All subscriptions</option>{sub_options}</select>"
        "<select onchange=\"filterCandidates()\" id='candBand' aria-label='Candidate confidence'>"
        "<option value=''>All confidence</option><option>Very high</option><option>High</option>"
        "<option>Medium</option><option>Low</option></select>"
        "<input class='filter' onkeyup=\"filterCandidates()\" id='candText' aria-label='Search candidates' placeholder='Search candidates...'>"
        "<span class='count' id='cand-count'></span>"
        "</div>"
        "<div class='table-scroll' tabindex='0' role='region' aria-label='Action candidates table'>"
        f"<table id='candidates' class='data'><thead><tr>{header_cells}</tr></thead>"
        f"<tbody>{''.join(body)}</tbody></table></div>"
    )


def _method_notes(notes):
    if not notes:
        return ""
    items = "".join(f"<li>{_esc(note)}</li>" for note in notes)
    return f"<div class='group-title'>Method and limits</div><ul class='notes'>{items}</ul>"


# Azure Portal look and feel: Segoe UI, the Azure blue accent, a Fluent neutral
# canvas, and a full light and dark palette driven by CSS variables. Every skill
# shares this one theme through document_shell, so all reports match.
THEME_CSS = """
.table-scroll{overflow-x:auto}
.sort-header{background:none;border:0;color:inherit;font:inherit;font-weight:inherit;cursor:pointer;text-align:left}
:focus-visible{outline:3px solid var(--accent);outline-offset:3px}
:root{
--bg:#faf9f8;--surface:#ffffff;--surface-2:#f3f2f1;--surface-3:#faf9f8;
--text:#201f1e;--text-2:#605e5c;--text-3:#8a8886;
--border:#edebe9;--border-2:#e1dfdd;
--accent:#0078d4;--accent-hover:#106ebe;--accent-soft:#deecf9;
--shadow:0 1.6px 3.6px rgba(0,0,0,.10),0 .3px .9px rgba(0,0,0,.07);
--radius:6px;--radius-sm:4px;
--sev-critical:#a4262c;--sev-high:#d13438;--sev-medium:#c77700;--sev-low:#605e5c;--sev-info:#0078d4;
--conf-very-high:#107c10;--conf-high:#107c10;--conf-medium:#c77700;--conf-low:#a4262c;
--code-bg:#f3f2f1;--code-text:#201f1e;--track:#c8c6c4;--track-on:#0078d4;
color-scheme:light}
html[data-theme='dark']{
--bg:#0d1117;--surface:#161b22;--surface-2:#21262d;--surface-3:#161b22;
--text:#f3f2f1;--text-2:#c8c6c4;--text-3:#a19f9d;
--border:#3b3a39;--border-2:#484644;
--accent:#4db2ff;--accent-hover:#6cbcff;--accent-soft:#123047;
--shadow:0 1.6px 3.6px rgba(0,0,0,.4),0 .3px .9px rgba(0,0,0,.3);
--sev-critical:#f1707b;--sev-high:#f1707b;--sev-medium:#f0a35e;--sev-low:#c8c6c4;--sev-info:#4db2ff;
--conf-very-high:#5bbf5b;--conf-high:#5bbf5b;--conf-medium:#f0a35e;--conf-low:#f1707b;
--code-bg:#1e1e1e;--code-text:#f3f2f1;--track:#605e5c;--track-on:#4db2ff;
color-scheme:dark}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);font:14px/1.5 "Segoe UI","Segoe UI Web (West European)",-apple-system,BlinkMacSystemFont,Roboto,"Helvetica Neue",Arial,sans-serif}
a{color:var(--accent)}
.appbar{position:sticky;top:0;z-index:20;display:flex;align-items:center;justify-content:space-between;gap:16px;padding:9px 20px;background:var(--surface);border-bottom:1px solid var(--border);box-shadow:var(--shadow)}
.appbar-brand{display:flex;align-items:center;gap:10px;font-weight:600;font-size:14px;color:var(--text)}
.appbar-logo{width:16px;height:16px;border-radius:3px;background:linear-gradient(135deg,var(--accent),#5c2d91)}
.theme-switch{display:inline-flex;align-items:center;gap:8px;border:1px solid var(--border-2);background:var(--surface-2);color:var(--text-2);border-radius:999px;padding:5px 12px 5px 8px;cursor:pointer;font:inherit;font-size:12px}
.theme-switch:hover{border-color:var(--accent)}
.theme-switch__track{position:relative;width:34px;height:18px;border-radius:999px;background:var(--track);transition:background .15s;flex:none}
.theme-switch__thumb{position:absolute;top:2px;left:2px;width:14px;height:14px;border-radius:50%;background:#fff;transition:left .15s;box-shadow:0 1px 2px rgba(0,0,0,.4)}
.theme-switch[aria-checked='true'] .theme-switch__track{background:var(--track-on)}
.theme-switch[aria-checked='true'] .theme-switch__thumb{left:18px}
.theme-switch__label{min-width:62px;text-align:left}
.wrap{max-width:1120px;margin:0 auto;padding:24px 24px 64px}
.wrap.wide{max-width:1360px}
.wrap.doc{max-width:880px;margin-top:24px;background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);padding:40px 40px 64px;box-shadow:var(--shadow)}
h1{font-size:24px;font-weight:600;margin:0 0 4px;color:var(--text)}
.subtitle{color:var(--text-2);margin:0 0 16px}
.meta{display:flex;flex-wrap:wrap;gap:6px 20px;color:var(--text-2);font-size:12.5px;margin-bottom:24px}
.meta b{color:var(--text);font-weight:600}
.group-title{font-size:18px;font-weight:600;margin:26px 0 12px;color:var(--text)}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:14px;margin:0 0 24px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:14px;margin:16px 0}
.card{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);padding:16px;box-shadow:var(--shadow)}
.card-label{color:var(--text-2);font-size:11px;text-transform:uppercase;letter-spacing:.05em;font-weight:600}
.card-value{font-size:26px;font-weight:600;margin-top:6px;color:var(--text)}
.card-sub{color:var(--text-2);font-size:12px;margin-top:2px}
.card h3{margin:0 0 6px;font-size:11px;text-transform:uppercase;letter-spacing:.05em;color:var(--text-2);font-weight:600}
.card .num{font-size:26px;font-weight:600;color:var(--text)}
.panel{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);padding:16px 18px;margin-bottom:18px;box-shadow:var(--shadow)}
.section{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);padding:20px;margin-top:16px;box-shadow:var(--shadow)}
.section h2{margin:0 0 12px;font-size:17px;font-weight:600;color:var(--text)}
.chart-row{display:grid;grid-template-columns:200px 1fr 130px;align-items:center;gap:12px;margin:7px 0}
.chart-name{color:var(--text-2);font-size:13px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.chart-bar{background:var(--surface-2);border-radius:3px;height:14px;overflow:hidden}
.chart-bar>div{height:100%;border-radius:3px}
.chart-score{text-align:right;font-variant-numeric:tabular-nums;font-size:13px;color:var(--text)}
.pill{display:inline-block;padding:2px 9px;border-radius:10px;border:1px solid;font-size:12px;font-weight:600;line-height:18px;white-space:nowrap}
.pill.s-critical{color:var(--sev-critical);border-color:color-mix(in srgb,var(--sev-critical) 45%,transparent);background:color-mix(in srgb,var(--sev-critical) 12%,transparent)}
.pill.s-high{color:var(--sev-high);border-color:color-mix(in srgb,var(--sev-high) 45%,transparent);background:color-mix(in srgb,var(--sev-high) 12%,transparent)}
.pill.s-medium{color:var(--sev-medium);border-color:color-mix(in srgb,var(--sev-medium) 45%,transparent);background:color-mix(in srgb,var(--sev-medium) 12%,transparent)}
.pill.s-low{color:var(--sev-low);border-color:color-mix(in srgb,var(--sev-low) 45%,transparent);background:color-mix(in srgb,var(--sev-low) 14%,transparent)}
.pill.s-info{color:var(--sev-info);border-color:color-mix(in srgb,var(--sev-info) 45%,transparent);background:color-mix(in srgb,var(--sev-info) 12%,transparent)}
.pill.c-vhigh{color:var(--conf-very-high);border-color:color-mix(in srgb,var(--conf-very-high) 45%,transparent);background:color-mix(in srgb,var(--conf-very-high) 12%,transparent)}
.pill.c-high{color:var(--conf-high);border-color:color-mix(in srgb,var(--conf-high) 45%,transparent);background:color-mix(in srgb,var(--conf-high) 12%,transparent)}
.pill.c-medium{color:var(--conf-medium);border-color:color-mix(in srgb,var(--conf-medium) 45%,transparent);background:color-mix(in srgb,var(--conf-medium) 12%,transparent)}
.pill.c-low{color:var(--conf-low);border-color:color-mix(in srgb,var(--conf-low) 45%,transparent);background:color-mix(in srgb,var(--conf-low) 12%,transparent)}
.controls{display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin:0 0 12px}
.filter,select,input[type=search],input[type=text],.filter-input{padding:7px 10px;border:1px solid var(--border-2);border-radius:var(--radius-sm);font:inherit;font-size:13px;background:var(--surface);color:var(--text)}
.filter{flex:1;min-width:200px}
select:focus,input:focus,.filter:focus{outline:2px solid var(--accent);outline-offset:-1px}
label{font-size:13px;color:var(--text-2);font-weight:600}
.count,.summary-line{color:var(--text-2);font-size:12.5px}
table.data{width:100%;border-collapse:collapse;background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);overflow:hidden;font-size:13px;box-shadow:var(--shadow)}
table.data th{background:var(--surface-2);text-align:left;padding:10px 12px;border-bottom:1px solid var(--border);cursor:pointer;user-select:none;white-space:nowrap;color:var(--text);font-weight:600}
table.data td{padding:9px 12px;border-bottom:1px solid var(--border);vertical-align:top;color:var(--text)}
table.data tr:last-child td{border-bottom:none}
table.data tbody tr:hover{background:var(--surface-2)}
.cmd code,.code-box{display:block;font:12px/1.45 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;color:var(--code-text);background:var(--code-bg);border:1px solid var(--border);padding:6px 8px;border-radius:var(--radius-sm);word-break:break-all;white-space:pre-wrap}
.copy,.copy-btn{margin-top:6px;font-size:11px;padding:4px 10px;border:1px solid var(--border-2);border-radius:var(--radius-sm);background:var(--surface);color:var(--text);cursor:pointer}
.copy:hover,.copy-btn:hover{border-color:var(--accent);color:var(--accent)}
.bar-wrap{position:relative;min-width:110px;background:var(--surface-2);height:16px;border-radius:3px;overflow:hidden}
.bar-fill{height:100%;border-radius:3px}
.bar-label{position:absolute;right:8px;top:0;line-height:16px;font-size:11px;font-weight:600;color:var(--text)}
.sort-btn{background:none;border:0;font:inherit;font-weight:600;color:var(--text);cursor:pointer;display:inline-flex;gap:4px;align-items:center}
.indicator{color:var(--accent)}
.note{color:var(--text-2);font-size:13px;line-height:1.5}
.small{font-size:12px;color:var(--text-3);line-height:1.5}
.hidden{display:none}
.notes{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);padding:12px 28px;color:var(--text-2);box-shadow:var(--shadow)}
.notes li{margin:4px 0}
footer{margin-top:32px;color:var(--text-3);font-size:12px;text-align:center}
@media print{.appbar,.controls,.copy,.copy-btn{display:none}}
"""

# Set the theme before first paint so there is no flash of the wrong palette.
THEME_INIT_JS = (
    "(function(){try{var s=localStorage.getItem('sre-theme');"
    "if(s!=='dark'&&s!=='light'){s='dark';}"
    "document.documentElement.setAttribute('data-theme',s);}"
    "catch(e){document.documentElement.setAttribute('data-theme','dark');}})();"
)

# Light and dark toggle: updates the attribute, the switch state, and the label,
# and remembers the choice in localStorage.
THEME_TOGGLE_JS = """
function setTheme(t){var d=document.documentElement;d.setAttribute('data-theme',t);try{localStorage.setItem('sre-theme',t);}catch(e){}
var b=document.getElementById('themeToggle');if(b){b.setAttribute('aria-checked',t==='dark'?'true':'false');var l=b.querySelector('.theme-switch__label');if(l){l.textContent=t==='dark'?'Dark mode':'Light mode';}}}
function toggleTheme(){var cur=document.documentElement.getAttribute('data-theme')==='dark'?'dark':'light';setTheme(cur==='dark'?'light':'dark');}
(function(){setTheme(document.documentElement.getAttribute('data-theme')==='dark'?'dark':'light');})();
"""

# Shared table behaviour: column sort, findings and candidate filters, copy.
TABLE_JS = """
function sortTable(th){var t=th.closest('table'),tb=t.tBodies[0],i=Array.prototype.indexOf.call(th.parentNode.children,th);
var asc=!(th.dataset.asc==='1');th.dataset.asc=asc?'1':'0';
var rows=Array.prototype.slice.call(tb.rows);
rows.sort(function(a,b){var x=cell(a,i),y=cell(b,i);return asc?(x>y?1:x<y?-1:0):(x<y?1:x>y?-1:0)});
rows.forEach(function(r){tb.appendChild(r)});}
function cell(r,i){var c=r.cells[i];if(!c)return'';if(c.dataset.sort!==undefined)return parseFloat(c.dataset.sort)||0;var t=c.innerText.replace(/[$,%]/g,'').trim();var n=parseFloat(t);return isNaN(n)?c.innerText.toLowerCase():n;}
function filterFindings(){var sev=(document.getElementById('findingsSev')||{}).value||'';var q=((document.getElementById('findingsText')||{}).value||'').toLowerCase();var el=document.getElementById('findings');if(!el)return;var tb=el.tBodies[0],shown=0;
Array.prototype.forEach.call(tb.rows,function(r){var okS=!sev||r.getAttribute('data-band')===sev;var okQ=r.innerText.toLowerCase().indexOf(q)>-1;var show=okS&&okQ;r.style.display=show?'':'none';if(show)shown++;});
var c=document.getElementById('findings-count');if(c)c.textContent=shown+' of '+tb.rows.length+' shown';}
function filterCandidates(){var s=(document.getElementById('candSub')||{}).value||'',b=(document.getElementById('candBand')||{}).value||'',q=((document.getElementById('candText')||{}).value||'').toLowerCase(),el=document.getElementById('candidates');if(!el)return;var tb=el.tBodies[0],shown=0;
Array.prototype.forEach.call(tb.rows,function(r){var ok=(!s||r.dataset.sub===s)&&(!b||r.dataset.band===b)&&r.innerText.toLowerCase().indexOf(q)>-1;r.style.display=ok?'':'none';if(ok)shown++;});
var c=document.getElementById('cand-count');if(c)c.textContent=shown+' of '+tb.rows.length+' shown';}
async function copyCmd(btn){var c=btn.getAttribute('data-cmd'),o=btn.innerText;
try{if(!navigator.clipboard||!navigator.clipboard.writeText)throw new Error('Clipboard access is unavailable');await navigator.clipboard.writeText(c);btn.innerText='Copied';}
catch(e){btn.innerText='Copy failed';btn.setAttribute('aria-label','Copy failed: select and copy the command manually');}
setTimeout(function(){btn.innerText=o},1600);}
(function(){filterFindings();filterCandidates();})();
"""


def _appbar(label):
    return (
        "<div class='appbar'>"
        f"<div class='appbar-brand'><span class='appbar-logo'></span>{_esc(label)}</div>"
        "<button id='themeToggle' class='theme-switch' type='button' role='switch' aria-checked='false' "
        "onclick='toggleTheme()' title='Toggle light or dark theme'>"
        "<span class='theme-switch__track'><span class='theme-switch__thumb'></span></span>"
        "<span class='theme-switch__label'>Light mode</span></button>"
        "</div>"
    )


def document_shell(
    title,
    body_html,
    extra_css="",
    extra_js="",
    include_table_js=True,
    wrap_class="wrap",
    appbar_label="Azure SRE Agent",
):
    """Wrap a report body in the shared Azure Portal shell.

    Every renderer uses this so the theme, the app bar, and the light and dark
    toggle are identical across all reports. Pass extra_css and extra_js for
    report specific styling and behaviour. Set include_table_js to False when the
    report ships its own table controls.
    """
    scripts = THEME_TOGGLE_JS + (TABLE_JS if include_table_js else "") + (extra_js or "")
    return (
        "<!doctype html><html lang='en' data-theme='dark'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>{_esc(title)}</title>"
        f"<style>{THEME_CSS}{extra_css}</style>"
        f"<script>{THEME_INIT_JS}</script></head><body>"
        f"{_appbar(appbar_label)}"
        f"<div class='{wrap_class}'>{body_html}</div>"
        f"<script>{scripts}</script></body></html>"
    )


def _sources_section(sources):
    items = []
    for source in sources or []:
        url = source.get("url", "")
        title = _esc(source.get("title") or url)
        if url.startswith("https://"):
            items.append(f"<li><a href='{_esc(url)}' rel='noopener noreferrer'>{title}</a></li>")
        else:
            items.append(f"<li>{title}</li>")
    if not items:
        items.append("<li>Consult the skill's checks catalog for collection methods and Microsoft sources. "
                     "Source verification was not supplied in this report.</li>")
    return "<div class='group-title'>Sources</div><ul>" + "".join(items) + "</ul>"


def render_html(report_data, include_identifiers=False):
    """Return the full HTML document string for a report_data dict."""
    from sharing import sanitized_copy

    report_data = sanitized_copy(report_data, include_identifiers=include_identifiers)
    meta = report_data.get("meta", {})
    meta_bits = []
    for label, key in (("Window", "window"), ("Scope", "scope"), ("Source", "source")):
        if meta.get(key):
            meta_bits.append(f"<span><b>{label}:</b> {_esc(meta[key])}</span>")
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    if report_data.get("generated_for"):
        meta_bits.insert(0, f"<span><b>For:</b> {_esc(report_data['generated_for'])}</span>")
    meta_bits.append(f"<span><b>Generated:</b> {generated}</span>")

    charts = "".join(_bar_chart(chart) for chart in report_data.get("charts", []))
    charts_block = f"<div class='group-title'>Overview</div>{charts}" if charts else ""
    review = report_data["sharing_review"]
    notice = (
        "<div class='panel' role='note'><b>Draft: customer sharing review required.</b> "
        f"Assessment completeness: {_esc(report_data.get('assessment_status', 'Not supplied'))}. "
        f"Redactions: {review['redactions']}. "
        + ("Customer identifiers were explicitly included. " if include_identifiers else
           "Identifiers use aliases; aliased commands are not executable instructions. ")
        + "Review free text, evidence, sources and the intended audience before delivery. "
        "No resource changes or external uploads were performed by this renderer.</div>"
    )

    body = (
        f"<h1>{_esc(report_data.get('title', 'SRE report'))}</h1>"
        f"<p class='subtitle'>{_esc(report_data.get('subtitle', ''))}</p>"
        f"<div class='meta'>{''.join(meta_bits)}</div>"
        f"{notice}"
        f"{_summary_cards(report_data.get('summary_cards'))}"
        f"{charts_block}"
        f"{_findings_table(report_data.get('findings'))}"
        f"{_candidates_table(report_data.get('candidates'))}"
        f"{_method_notes(report_data.get('method_notes'))}"
        f"{_sources_section(report_data.get('sources'))}"
        "<footer>Generated by an Azure SRE Agent skill. Read only. "
        "Recommendations and commands are proposals for a human to review and run.</footer>"
    )
    return document_shell(report_data.get("title", "SRE report"), body)


def main(report_data: dict = None, filename: str = None, include_identifiers: bool = False) -> dict:
    """Render report_data to a self contained HTML file and return its path.

    report_data: the report object. When omitted, read JSON from standard input.
    filename: optional output file name. Defaults to a slug of the title plus a
    timestamp.
    """
    if report_data is None:
        raw = sys.stdin.read()
        if not raw.strip():
            raise ValueError("A report JSON object is required; no assessment was supplied.")
        report_data = json.loads(raw)
    if not isinstance(report_data, dict) or not report_data.get("title"):
        raise ValueError("The report must be an object with a title.")

    document = render_html(report_data, include_identifiers=include_identifiers)
    if not filename:
        slug = "".join(c if c.isalnum() else "-" for c in report_data.get("title", "sre-report").lower())
        slug = "-".join(part for part in slug.split("-") if part) or "sre-report"
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        filename = f"{stamp}-{slug}.html"
    if any(character in filename for character in ("/", "\\", "\x00")) or filename in (".", ".."):
        raise ValueError("The report filename must be a simple local filename, not a path.")

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    path = os.path.join(OUTPUT_DIR, filename)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(document)
    return {"path": path, "bytes": len(document.encode("utf-8"))}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--include-identifiers", action="store_true",
                        help="Keep identifiers for an explicitly approved customer audience; credentials are still redacted.")
    parser.add_argument("--filename", help="Local output filename, without directory separators.")
    args = parser.parse_args()
    print(json.dumps(main(filename=args.filename, include_identifiers=args.include_identifiers)))
