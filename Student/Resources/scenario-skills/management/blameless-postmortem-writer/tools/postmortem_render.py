"""
postmortem_render: Render a blameless postmortem as a self contained HTML doc.

Azure SRE Agent Python tool. Reads a postmortem object as JSON on standard input
and writes one self contained HTML document (inline CSS, no external assets) to
OUTPUT_DIR, then returns the path. Standard library only.

    echo '<postmortem json>' | python postmortem_render.py

See references/postmortem-template.md for the input shape. The pure section
builders are unit tested without any file or network access.
"""

import html
import argparse
import json
import os
import sys
from datetime import datetime, timezone


def _bootstrap_shared_tools():
    """Make the shared report_render importable both in the repo and when the
    deploy step bundles the shared tools next to this file."""
    here = os.path.dirname(os.path.abspath(__file__))
    if here not in sys.path:
        sys.path.insert(0, here)
    probe = here
    for _ in range(6):
        candidate = os.path.join(probe, "shared", "tools")
        if os.path.isdir(candidate) and candidate not in sys.path:
            sys.path.insert(0, candidate)
            break
        probe = os.path.dirname(probe)


_bootstrap_shared_tools()
from report_render import document_shell  # noqa: E402
from sharing import sanitized_copy  # noqa: E402

OUTPUT_DIR = "/mnt/data"
# Action item type to its pill class; the colours live in POSTMORTEM_CSS as
# theme variables so they adapt to the light and dark palette.
ACTION_CLASS = {"Prevent": "a-prevent", "Detect": "a-detect", "Mitigate": "a-mitigate"}


def _esc(value):
    return html.escape("" if value is None else str(value), quote=True)


def _paragraph(title, text):
    if not text:
        return ""
    return f"<h2>{_esc(title)}</h2><p>{_esc(text)}</p>"


def _list_block(title, items):
    items = [item for item in (items or []) if item]
    if not items:
        return ""
    rows = "".join(f"<li>{_esc(item)}</li>" for item in items)
    return f"<h2>{_esc(title)}</h2><ul>{rows}</ul>"


def _impact_block(impact):
    if not impact:
        return ""
    rows = ""
    for label, key in (("Duration", "duration"), ("Scope", "scope"), ("Customer effect", "customer")):
        if impact.get(key):
            rows += f"<tr><th>{label}</th><td>{_esc(impact[key])}</td></tr>"
    return f"<h2>Impact</h2><table class='kv'>{rows}</table>" if rows else ""


def _timeline_block(timeline):
    rows = [row for row in (timeline or []) if row]
    if not rows:
        return ""
    body = "".join(
        f"<tr><td class='t'>{_esc(row.get('time', ''))}</td><td>{_esc(row.get('event', ''))}</td></tr>"
        for row in rows
    )
    controls = (
        "<div class='controls'>"
        "<input class='filter' id='tlText' onkeyup=\"filterRows('timeline')\" placeholder='Filter timeline...'>"
        "<span class='count' id='tl-count'></span></div>"
    ) if len(rows) > 4 else ""
    return (
        "<h2>Timeline</h2>"
        f"{controls}"
        "<table class='timeline' id='timeline' data-text='tlText' data-count='tl-count'>"
        f"<tbody>{body}</tbody></table>"
    )


def _lessons_block(lessons):
    if not lessons:
        return ""
    parts = [
        _list_block("What went well", lessons.get("went_well")),
        _list_block("What went wrong", lessons.get("went_wrong")),
        _list_block("Where we got lucky", lessons.get("got_lucky")),
    ]
    joined = "".join(parts)
    return f"<h2>Lessons</h2><div class='lessons'>{joined}</div>" if joined else ""


def _action_items_block(items):
    items = [item for item in (items or []) if item]
    if not items:
        return ""
    types_present = [t for t in ("Prevent", "Detect", "Mitigate") if any(item.get("type") == t for item in items)]
    rows = ""
    for item in items:
        kind = item.get("type", "")
        cls = ACTION_CLASS.get(kind, "")
        pill = f"<span class='pill {cls}'>{_esc(kind)}</span>" if kind else ""
        rows += (
            f"<tr data-type='{_esc(kind)}'>"
            f"<td>{_esc(item.get('action', ''))}</td>"
            f"<td>{_esc(item.get('owner', ''))}</td>"
            f"<td>{_esc(item.get('due', ''))}</td>"
            f"<td>{pill}</td></tr>"
        )
    type_select = ""
    if types_present:
        options = "".join(f"<option value='{_esc(t)}'>{_esc(t)}</option>" for t in types_present)
        type_select = (
            "<select id='aiType' onchange=\"filterRows('actionItems')\">"
            f"<option value=''>All types</option>{options}</select>"
        )
    return (
        "<h2>Action items</h2>"
        "<div class='controls'>"
        f"{type_select}"
        "<input class='filter' id='aiText' onkeyup=\"filterRows('actionItems')\" placeholder='Filter action items...'>"
        "<span class='count' id='ai-count'></span>"
        "</div>"
        "<table class='data' id='actionItems' data-text='aiText' data-type='aiType' data-count='ai-count'>"
        "<thead><tr><th onclick='sortTable(this)'>Action</th><th onclick='sortTable(this)'>Owner</th>"
        "<th onclick='sortTable(this)'>Due</th><th onclick='sortTable(this)'>Type</th></tr></thead>"
        f"<tbody>{rows}</tbody></table>"
    )


# Postmortem specific styling on top of the shared Azure Portal theme. Uses the
# same CSS variables so it adapts to the light and dark palette.
POSTMORTEM_CSS = """
h2{font-size:19px;font-weight:600;margin:28px 0 8px;padding-top:14px;border-top:1px solid var(--border);color:var(--text)}
.lessons h2{border-top:none;padding-top:0;font-size:16px}
p{margin:8px 0;color:var(--text)}
ul{margin:8px 0;padding-left:22px}
li{margin:4px 0}
.badges{display:flex;gap:8px;margin:6px 0 20px;flex-wrap:wrap}
.badge{padding:3px 10px;border-radius:10px;border:1px solid var(--border-2);font-size:12.5px;font-weight:600;background:var(--surface-2);color:var(--text-2)}
table.kv{width:100%;border-collapse:collapse;margin:10px 0}
table.kv th{width:170px;text-align:left;color:var(--text-2);font-weight:600;vertical-align:top;padding:6px 8px}
table.kv td{padding:6px 8px;color:var(--text)}
table.timeline{width:100%;border-collapse:collapse;margin:10px 0}
table.timeline td{padding:8px 10px;border-bottom:1px solid var(--border);vertical-align:top;color:var(--text)}
table.timeline .t{white-space:nowrap;color:var(--text-2);font-variant-numeric:tabular-nums;width:130px}
.pill.a-prevent{color:var(--conf-very-high);border-color:color-mix(in srgb,var(--conf-very-high) 45%,transparent);background:color-mix(in srgb,var(--conf-very-high) 12%,transparent)}
.pill.a-detect{color:var(--sev-medium);border-color:color-mix(in srgb,var(--sev-medium) 45%,transparent);background:color-mix(in srgb,var(--sev-medium) 12%,transparent)}
.pill.a-mitigate{color:var(--accent);border-color:color-mix(in srgb,var(--accent) 45%,transparent);background:color-mix(in srgb,var(--accent) 12%,transparent)}
.callout{background:var(--accent-soft);border:1px solid color-mix(in srgb,var(--accent) 35%,transparent);border-radius:var(--radius);padding:12px 16px;color:var(--text);font-size:13.5px;margin:18px 0}
footer{margin-top:36px}
"""

# Generic row filter for the action items and timeline tables. Each table
# declares its input, optional type select, and count element through data-*.
POSTMORTEM_JS = """
function filterRows(tableId){var el=document.getElementById(tableId);if(!el)return;var cfg=el.dataset;
var q=((document.getElementById(cfg.text)||{}).value||'').toLowerCase();
var ty=cfg.type?((document.getElementById(cfg.type)||{}).value||''):'';
var tb=el.tBodies[0],shown=0;
Array.prototype.forEach.call(tb.rows,function(r){var okT=!ty||r.getAttribute('data-type')===ty;var okQ=r.innerText.toLowerCase().indexOf(q)>-1;var s=okT&&okQ;r.style.display=s?'':'none';if(s)shown++;});
if(cfg.count){var c=document.getElementById(cfg.count);if(c)c.textContent=shown+' of '+tb.rows.length+' shown';}}
(function(){filterRows('actionItems');filterRows('timeline');})();
"""


def _reviewed_input(data, include_identifiers=False):
    data = sanitized_copy(data, include_identifiers=include_identifiers)
    status = data.get("assessment_status", "Not assessed")
    if status not in ("Complete", "Partial", "Not assessed"):
        status = "Not assessed"
    if data.get("collection_errors") or (status == "Complete" and not data.get("sources")):
        status = "Partial"
    data["assessment_status"] = status
    return data


def render_html(data, include_identifiers=False):
    """Return the full postmortem HTML document string. Pure and testable."""
    data = _reviewed_input(data, include_identifiers=include_identifiers)
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    badges = "".join(
        f"<span class='badge'>{_esc(label)}: {_esc(data[key])}</span>"
        for label, key in (("Severity", "severity"), ("Status", "status"), ("Incident", "incident_id"))
        if data.get(key)
    )
    body = (
        f"<h1>{_esc(data.get('title', 'Incident postmortem'))}</h1>"
        f"<div class='meta'>Blameless postmortem. Generated {generated}.</div>"
        f"<div class='badges'>{badges}</div>"
        "<div class='callout'>This is a blameless review. It describes systems and conditions, "
        "not individuals, so the team can learn and improve how the next incident is prevented, "
        "detected, and contained.</div>"
        "<div class='callout'>Draft: human review required before sharing. Automated sanitization does not replace review of evidence, identifiers, customer impact and action owners. No external send is performed.</div>"
        f"{_paragraph('Assessment status', data.get('assessment_status', 'Not assessed'))}"
        f"{_list_block('Evidence collection limits', data.get('collection_errors'))}"
        f"{_paragraph('Summary', data.get('summary'))}"
        f"{_impact_block(data.get('impact'))}"
        f"{_timeline_block(data.get('timeline'))}"
        f"{_paragraph('Root cause', data.get('root_cause'))}"
        f"{_list_block('Contributing factors', data.get('contributing_factors'))}"
        f"{_paragraph('Detection', data.get('detection'))}"
        f"{_paragraph('Resolution', data.get('resolution'))}"
        f"{_lessons_block(data.get('lessons'))}"
        f"{_action_items_block(data.get('action_items'))}"
        f"{_list_block('Sources', [str(source.get('title', 'Evidence')) + ': ' + str(source.get('url', '')) for source in data.get('sources', [])])}"
        "<footer>Generated by an Azure SRE Agent skill. Read only. Facts from incident evidence; "
        "unknowns are named as action items, not guessed.</footer>"
    )
    return document_shell(
        data.get("title", "Incident postmortem"),
        body,
        extra_css=POSTMORTEM_CSS,
        extra_js=POSTMORTEM_JS,
        wrap_class="wrap doc",
    )


def main(data: dict = None, include_identifiers=False) -> dict:
    if data is None:
        raw = sys.stdin.read()
        data = json.loads(raw) if raw.strip() else {}
    data = _reviewed_input(data, include_identifiers=include_identifiers)
    document = render_html(data, include_identifiers=include_identifiers)
    slug = "".join(c if c.isalnum() else "-" for c in data.get("title", "postmortem").lower())
    slug = "-".join(part for part in slug.split("-") if part) or "postmortem"
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    path = os.path.join(OUTPUT_DIR, f"postmortem-{slug}-{stamp}.html")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(document)
    return {"path": path, "bytes": len(document.encode("utf-8")), "sharing_review": data["sharing_review"],
            "assessment_status": data.get("assessment_status", "Not assessed"), "sources": data.get("sources", [])}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--include-identifiers", action="store_true", help="include identifiers in the internal draft; credentials remain redacted")
    args = parser.parse_args()
    print(json.dumps(main(include_identifiers=args.include_identifiers)))
