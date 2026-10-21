"""
generate_report: Build a self contained HTML FinOps cost optimization report.

Azure SRE Agent Python tool. Renders one self contained HTML file with no
external assets, no CDN, and no image dependencies. All styling is inline CSS
and every chart is drawn with plain HTML and CSS bars, so the report opens fully
styled offline. Writes the report to /mnt/data and returns a file link.

The report has two halves:
- FinOps overview: spend by subscription and resource group, and estimated
  monthly savings by dimension.
- Termination candidates: idle or orphaned resources scored by a confidence to
  terminate value from 0 to 100, each with a copyable az delete command. The
  agent never runs these commands; they are for an operator to review and run.

See references/report-layout.md for the input shape.
"""

import html
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

# Confidence band to its shared pill class and bar colour variable, so the
# palette adapts to the light and dark theme.
BAND_CLASS = {"Very high": "c-vhigh", "High": "c-high", "Medium": "c-medium", "Low": "c-low"}
BAND_VAR = {
    "Very high": "var(--conf-very-high)",
    "High": "var(--conf-high)",
    "Medium": "var(--conf-medium)",
    "Low": "var(--conf-low)",
}
CURRENCY_SYMBOL = {"USD": "$", "EUR": "\u20ac", "GBP": "\u00a3", "JPY": "\u00a5"}


def _esc(value):
    return html.escape("" if value is None else str(value), quote=True)


def _money(value, currency):
    if value is None:
        return "Not reconciled"
    symbol = CURRENCY_SYMBOL.get((currency or "").upper())
    number = f"{float(value or 0.0):,.2f}"
    return f"{symbol}{number}" if symbol else f"{number} {currency}".strip()


def _band_from_confidence(confidence):
    score = float(confidence or 0.0)
    if score >= 90:
        return "Very high"
    if score >= 70:
        return "High"
    if score >= 50:
        return "Medium"
    return "Low"


def _group_title(text):
    return f"<div class='group-title'>{_esc(text)}</div>"


def _bar_rows(items, currency):
    """Horizontal CSS bars for a list of {name, cost}, already sorted descending."""
    rows = [item for item in items if item]
    if not rows:
        return "<p class='small'>No data.</p>"
    top = max(float(item.get("cost", 0.0) or 0.0) for item in rows) or 1.0
    out = []
    for item in rows:
        cost = float(item.get("cost", 0.0) or 0.0)
        width = max(2.0, cost / top * 100.0)
        out.append(
            "<div class='chart-row money'>"
            f"<div class='chart-name'>{_esc(item.get('name', ''))}</div>"
            f"<div class='chart-bar'><div style='width:{width:.1f}%;background:var(--accent)'></div></div>"
            f"<div class='chart-score'>{_money(cost, currency)}</div></div>"
        )
    return "".join(out)


def _candidate_chart(candidates):
    ranked = sorted(candidates, key=lambda c: float(c.get("confidence", 0.0) or 0.0), reverse=True)[:8]
    if not ranked:
        return ""
    top = max(float(c.get("confidence", 0.0) or 0.0) for c in ranked) or 1.0
    out = []
    for candidate in ranked:
        confidence = float(candidate.get("confidence", 0.0) or 0.0)
        band = candidate.get("band") or _band_from_confidence(confidence)
        width = max(2.0, confidence / top * 100.0)
        out.append(
            "<div class='chart-row'>"
            f"<div class='chart-name'>{_esc(candidate.get('resource', ''))}</div>"
            f"<div class='chart-bar'><div style='width:{width:.1f}%;background:{BAND_VAR.get(band, 'var(--conf-high)')}'></div></div>"
            f"<div class='chart-score'>{int(round(confidence))}</div></div>"
        )
    return "".join(out)


def _render_candidates(candidates, currency):
    if not candidates:
        return ""
    counts = {"Very high": 0, "High": 0, "Medium": 0, "Low": 0}
    for candidate in candidates:
        band = candidate.get("band") or _band_from_confidence(candidate.get("confidence"))
        candidate["band"] = band
        counts[band] = counts.get(band, 0) + 1

    cards = (
        "<div class='grid'>"
        f"<div class='card'><h3>Total candidates</h3><div class='num'>{len(candidates)}</div></div>"
        "<div class='card'><h3>Candidate savings</h3><div class='num'>Individual estimates only</div></div>"
        f"<div class='card'><h3>Very high confidence</h3><div class='num'>{counts['Very high']}</div></div>"
        f"<div class='card'><h3>High confidence</h3><div class='num'>{counts['High']}</div></div>"
        f"<div class='card'><h3>Medium or low confidence</h3><div class='num'>{counts['Medium'] + counts['Low']}</div></div>"
        "</div>"
    )

    note = (
        "<div class='small' style='margin:8px 0 0'>Estimates are not additive to recommendations and are not realized savings. Deallocated VMs show direct "
        "compute savings as 0 because compute is already stopped; their attached disks and public IPs may "
        "still bill and appear as their own candidates where detected. Resources that could not be priced "
        "are marked Excluded.</div>"
    )

    chart = _candidate_chart(candidates)
    chart_block = (
        "<div class='section'><h2>Top termination candidates</h2>"
        "<div class='note'>This chart favours the clearest evidence: unattached disks, old snapshots, orphan "
        "NICs, and unassociated public IPs. Shared network, DR, and firewall looking resources are "
        "intentionally scored low.</div>"
        f"<div style='margin-top:16px'>{chart}</div></div>"
    ) if chart else ""

    how = (
        "<div class='section'><h2>How to read the confidence score</h2>"
        "<div class='note'>Higher scores rank stronger evidence for owner review, never permission to delete. "
        "Even an old unattached disk or snapshot can hold required recovery data. Names alone cannot prove "
        "nonproduction, idleness or absence of dependencies.</div>"
        "<div class='small' style='margin-top:10px'>Before any deletion, confirm owner approval, dependencies, "
        "backup and recovery retention, locks, workload schedule and change approval. Delete commands are "
        "destructive operator instructions, not read only checks. The agent never runs them.</div></div>"
    )

    subs = sorted({str(c.get("subscription", "")) for c in candidates if c.get("subscription")})
    sub_options = "".join(f"<option value='{_esc(s)}'>{_esc(s)}</option>" for s in subs)

    ordered = sorted(candidates, key=lambda c: float(c.get("confidence", 0.0) or 0.0), reverse=True)
    body_rows = []
    for index, candidate in enumerate(ordered, start=1):
        confidence = float(candidate.get("confidence", 0.0) or 0.0)
        band = candidate.get("band") or _band_from_confidence(confidence)
        band_class = BAND_CLASS.get(band, "c-low")
        bar_color = BAND_VAR.get(band, "var(--conf-high)")
        if candidate.get("excluded"):
            saving_cell = (
                "<strong>Excluded</strong>"
                f"<div class='small'>{_esc(candidate.get('exclusion_reason', 'Not priced; excluded from total'))}</div>"
            )
        else:
            saving_cell = f"<strong>{_money(candidate.get('monthly_saving'), currency)}/mo</strong>"
            if candidate.get("saving_note"):
                saving_cell += f"<div class='small'>{_esc(candidate.get('saving_note'))}</div>"
        search = " ".join(
            str(candidate.get(key, ""))
            for key in ("resource", "resource_type", "subscription", "resource_group", "location", "reason")
        ).lower()
        delete_command = candidate.get("delete_command") or ""
        cmd_id = f"cmd-{index}"
        if delete_command:
            delete_cell = (
                f"<div class='code-box' id='{cmd_id}'>{_esc(delete_command)}</div>"
                f"<button class='copy-btn' data-copy='{cmd_id}'>Copy</button>"
            )
        else:
            delete_cell = "<span class='small'>No delete command</span>"
        bar_width = max(2.0, min(100.0, confidence))
        body_rows.append(
            f"<tr data-subscription='{_esc(candidate.get('subscription', ''))}' data-band='{_esc(band)}' data-search='{_esc(search)}'>"
            f"<td>{_esc(candidate.get('resource', ''))}</td>"
            f"<td>{_esc(candidate.get('resource_type', ''))}</td>"
            f"<td>{_esc(candidate.get('subscription', ''))}</td>"
            f"<td>{_esc(candidate.get('resource_group', ''))}</td>"
            f"<td>{_esc(candidate.get('location', ''))}</td>"
            f"<td>{saving_cell}</td>"
            f"<td><div class='bar-wrap'><div class='bar-fill' style='width:{bar_width:.0f}%;background:{bar_color}'></div>"
            f"<span class='bar-label'>{int(round(confidence))}</span></div></td>"
            f"<td><span class='pill {band_class}'>{_esc(band)}</span></td>"
            f"<td>{_esc(candidate.get('reason', ''))}</td>"
            f"<td>{_esc(candidate.get('next_step', ''))}</td>"
            f"<td>{delete_cell}</td></tr>"
        )

    table = (
        "<div class='section'><h2>Filterable termination candidates</h2>"
        "<div class='controls'>"
        "<div><label for='subscriptionFilter'>Subscription</label><br>"
        f"<select id='subscriptionFilter'><option value='all'>All subscriptions</option>{sub_options}</select></div>"
        "<div><label for='bandFilter'>Confidence band</label><br>"
        "<select id='bandFilter'><option value='all'>All bands</option>"
        "<option value='Very high'>Very high</option><option value='High'>High</option>"
        "<option value='Medium'>Medium</option><option value='Low'>Low</option></select></div>"
        "<div><label for='searchBox'>Search</label><br>"
        "<input id='searchBox' type='text' placeholder='resource, group, location, type'></div>"
        "</div>"
        f"<div id='resultSummary' class='summary-line'>Showing {len(ordered)} of {len(ordered)} candidates</div>"
        "<div style='overflow-x:auto'><table><thead><tr>"
        "<th>Resource</th><th>Type</th><th>Subscription</th><th>Resource group</th><th>Location</th>"
        "<th>Est. monthly savings</th><th>Confidence</th><th>Band</th><th>Why it looks unused</th>"
        "<th>Recommended next step</th><th>Delete command</th></tr></thead>"
        f"<tbody id='candidateRows'>{''.join(body_rows)}</tbody></table></div></div>"
    )

    return cards + note + chart_block + how + table


def _render_findings(findings, currency):
    if not findings:
        return ""
    headers = ["Resource", "Dimension", "Current", "Proposed", "Monthly saving", "Risk", "Priority"]
    numeric_columns = {4}
    head = ""
    for index, header in enumerate(headers):
        is_numeric = "true" if index in numeric_columns else "false"
        head += (
            f"<th><button type='button' class='sort-btn' data-numeric='{is_numeric}' "
            f"onclick=\"sortTable('findingsTable',{index},this)\">{_esc(header)}"
            "<span class='indicator'></span></button></th>"
        )
    body = ""
    for finding in sorted(findings, key=lambda item: float(item.get("priority_score", 0.0) or 0.0), reverse=True):
        cells = [
            _esc(finding.get("resource", "")),
            _esc(finding.get("dimension", "")),
            _esc(finding.get("current", "")),
            _esc(finding.get("proposed", "")),
            _esc(_money(finding.get("monthly_saving"), currency)),
            _esc(finding.get("risk", "")),
            _esc(finding.get("priority_band", "")),
        ]
        body += "<tr>" + "".join(f"<td>{cell}</td>" for cell in cells) + "</tr>"
    return (
        "<div class='section'><h2>Savings recommendations</h2>"
        "<div class='note'>Rate, tier, retention, commitment, and scheduling changes ranked by priority. "
        "These are proposals for a human to review; the agent applies nothing.</div>"
        "<div style='margin:12px 0'><input type='search' class='filter-input' placeholder='Filter rows...' "
        "oninput=\"filterTable('findingsTable',this.value)\"></div>"
        "<div style='overflow-x:auto'>"
        f"<table id='findingsTable'><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>"
        "<p class='small' id='findingsTable-count'></p></div>"
    )


# FinOps specific styling on top of the shared Azure Portal theme. Uses the same
# CSS variables so the report follows the light and dark palette.
FINOPS_CSS = """
.header{margin-bottom:8px}
.section table{width:100%;border-collapse:collapse;font-size:13px}
.section th,.section td{padding:10px;border-top:1px solid var(--border);vertical-align:top;text-align:left;color:var(--text)}
.section th{background:var(--surface-2);font-weight:600;white-space:nowrap}
.filter-input{min-width:260px}
@media (max-width:900px){.chart-row,.chart-row.money{grid-template-columns:1fr}}
"""


SCRIPT = r"""
(function () {
  var subscriptionFilter = document.getElementById('subscriptionFilter');
  var bandFilter = document.getElementById('bandFilter');
  var searchBox = document.getElementById('searchBox');
  var resultSummary = document.getElementById('resultSummary');
  var body = document.getElementById('candidateRows');
  if (body) {
    var rows = Array.prototype.slice.call(body.rows);
    var apply = function () {
      var sub = subscriptionFilter ? subscriptionFilter.value : 'all';
      var band = bandFilter ? bandFilter.value : 'all';
      var q = searchBox ? searchBox.value.trim().toLowerCase() : '';
      var visible = 0;
      rows.forEach(function (row) {
        var okSub = sub === 'all' || row.getAttribute('data-subscription') === sub;
        var okBand = band === 'all' || row.getAttribute('data-band') === band;
        var okSearch = !q || (row.getAttribute('data-search') || '').indexOf(q) !== -1;
        var show = okSub && okBand && okSearch;
        row.classList.toggle('hidden', !show);
        if (show) visible += 1;
      });
      if (resultSummary) resultSummary.textContent = 'Showing ' + visible + ' of ' + rows.length + ' candidates';
    };
    if (subscriptionFilter) subscriptionFilter.addEventListener('change', apply);
    if (bandFilter) bandFilter.addEventListener('change', apply);
    if (searchBox) searchBox.addEventListener('input', apply);
    apply();
  }

  function filterTable(id, query) {
    var table = document.getElementById(id);
    if (!table) return;
    var term = query.toLowerCase();
    var trs = table.tBodies[0].rows;
    var shown = 0;
    for (var i = 0; i < trs.length; i++) {
      var match = trs[i].textContent.toLowerCase().indexOf(term) !== -1;
      trs[i].style.display = match ? '' : 'none';
      if (match) shown++;
    }
    var counter = document.getElementById(id + '-count');
    if (counter) counter.textContent = shown + ' of ' + trs.length + ' rows';
  }
  window.filterTable = filterTable;

  function sortTable(id, col, btn) {
    var table = document.getElementById(id);
    if (!table) return;
    var tbody = table.tBodies[0];
    var trs = Array.prototype.slice.call(tbody.rows);
    var asc = btn.getAttribute('data-asc') !== 'true';
    btn.setAttribute('data-asc', asc ? 'true' : 'false');
    var numeric = btn.getAttribute('data-numeric') === 'true';
    trs.sort(function (a, b) {
      var x = a.cells[col].textContent.trim();
      var y = b.cells[col].textContent.trim();
      if (numeric) {
        var nx = parseFloat(x.replace(/[^0-9.\-]/g, '')) || 0;
        var ny = parseFloat(y.replace(/[^0-9.\-]/g, '')) || 0;
        return asc ? nx - ny : ny - nx;
      }
      return asc ? x.localeCompare(y) : y.localeCompare(x);
    });
    for (var j = 0; j < trs.length; j++) tbody.appendChild(trs[j]);
  }
  window.sortTable = sortTable;

  var buttons = document.querySelectorAll('.copy-btn');
  for (var b = 0; b < buttons.length; b++) {
    buttons[b].addEventListener('click', function () {
      var id = this.getAttribute('data-copy');
      var node = document.getElementById(id);
      if (!node) return;
      var btn = this;
      var original = btn.textContent;
      var reset = function (label) { btn.textContent = label; setTimeout(function () { btn.textContent = original; }, 1200); };
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(node.textContent).then(function () { reset('Copied'); }, function () { reset('Copy failed'); });
      } else {
        reset('Copied');
      }
    });
  }
})();
"""


def _validated_totals(data):
    """Reject mixed money and inconsistent baselines rather than silently sum."""
    totals = data.get("totals", {})
    currency = totals.get("currency")
    records = [item for key in ("subscriptions", "resource_groups", "findings", "candidates") for item in data.get(key, [])]
    if not currency or any(item.get("currency", currency) != currency for item in records):
        raise ValueError("Generate a separate report per explicit currency; no conversion is performed.")
    analyzed = float(totals.get("analyzed_spend", 0) or 0)
    subscriptions = data.get("subscriptions", [])
    if subscriptions:
        baseline = sum(float(item.get("cost", 0) or 0) for item in subscriptions)
        if abs(baseline - analyzed) > 0.01:
            raise ValueError("Analyzed spend does not reconcile to the selected subscription baseline.")
    savings = None
    if totals.get("savings_reconciled") is True and data.get("reconciliation_notes"):
        savings = float(totals.get("estimated_monthly_savings", 0) or 0)
    return currency, analyzed, savings


def main(report_data: dict, report_title: str = "Azure FinOps Cost Optimization Report", include_identifiers: bool = False) -> dict:
    """Render the HTML report and return its file link.

    report_data: see references/report-layout.md for the expected shape.
    """
    data = report_data or {}
    currency, analyzed, savings = _validated_totals(data)
    data = sanitized_copy(data, include_identifiers=include_identifiers)
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    window = int(data.get("window_days", 30) or 30)
    if window <= 0:
        raise ValueError("window_days must be positive.")
    monthly_baseline = analyzed * 30 / window
    pct = savings / monthly_baseline * 100 if monthly_baseline > 0 and savings is not None else None
    assessment_status = data.get("assessment_status", "Partial")
    if not data.get("subscriptions"):
        assessment_status = "Not assessed"
    elif savings is None or data.get("collection_failures"):
        assessment_status = "Partial"
    sources = data.get("sources") or [
        {"title": "Cost query and pagination", "url": "https://learn.microsoft.com/javascript/api/@azure/arm-costmanagement/queryproperties"},
        {"title": "Cost scope and access", "url": "https://learn.microsoft.com/azure/cost-management-billing/costs/assign-access-acm-data"},
    ]

    findings = data.get("findings", [])
    candidates = data.get("candidates", [])

    priority_bands = {"High": 0, "Medium": 0, "Low": 0}
    for finding in findings:
        band = finding.get("priority_band", "Low")
        priority_bands[band] = priority_bands.get(band, 0) + 1

    candidate_bands = {"Very high": 0, "High": 0, "Medium": 0, "Low": 0}
    for candidate in candidates:
        band = candidate.get("band") or _band_from_confidence(candidate.get("confidence"))
        candidate_bands[band] = candidate_bands.get(band, 0) + 1

    header = (
        "<div class='header'>"
        f"<h1>{_esc(report_title)}</h1>"
        f"<p class='subtitle'>Generated {generated}. Scope {_esc(data.get('generated_for', 'agent read scope'))}. "
        f"Window {int(data.get('window_days', 30) or 30)} days. Cost source {_esc(data.get('data_source', 'CostManagement'))}. "
        f"Accessible subscriptions only. Assessment: {_esc(assessment_status)}.</p></div>"
    )

    summary_cards = (
        "<div class='grid'>"
        f"<div class='card'><h3>Analyzed spend ({window} days)</h3><div class='num'>{_money(analyzed, currency)}</div></div>"
        f"<div class='card'><h3>Est. monthly savings</h3><div class='num' style='color:var(--conf-very-high)'>{_money(savings, currency)}</div></div>"
        f"<div class='card'><h3>Savings vs normalized 30 day spend</h3><div class='num'>{f'{pct:.1f}%' if pct is not None else 'Not reconciled'}</div></div>"
        f"<div class='card'><h3>Termination candidates</h3><div class='num'>{len(candidates)}</div></div>"
        f"<div class='card'><h3>Recommendations</h3><div class='num'>{len(findings)}</div></div>"
        "</div>"
    )

    overview = []
    subs = data.get("subscriptions", [])
    if subs:
        ordered_subs = sorted(subs, key=lambda item: float(item.get("cost", 0.0) or 0.0), reverse=True)
        overview.append(
            "<div class='section'><h2>Spend by subscription</h2>" + _bar_rows(ordered_subs, currency) + "</div>"
        )
    rgs = data.get("resource_groups", [])
    if rgs:
        ordered_rgs = sorted(rgs, key=lambda item: float(item.get("cost", 0.0) or 0.0), reverse=True)
        overview.append(
            "<div class='section'><h2>Spend by resource group</h2>" + _bar_rows(ordered_rgs, currency) + "</div>"
        )
    by_dimension = data.get("savings_by_dimension", {})
    if by_dimension and savings is not None:
        dim_items = sorted(
            [{"name": key, "cost": value} for key, value in by_dimension.items()],
            key=lambda item: float(item.get("cost", 0.0) or 0.0),
            reverse=True,
        )
        overview.append(
            "<div class='section'><h2>Estimated monthly savings by dimension</h2>" + _bar_rows(dim_items, currency) + "</div>"
        )

    candidates_html = _render_candidates(candidates, currency)
    findings_html = _render_findings(findings, currency)

    limitation = (
        "<div class='section'><h2>Method and limits</h2>"
        "<div class='note'>Spend narrows where to look; savings and confidence decide what to act on first. "
        "Termination candidates are scored by a conservative confidence to terminate heuristic based on "
        "association state, age, and naming. Where Azure Monitor metrics or Activity Logs could not be read, "
        "the score relies on those heuristics only and the resource is treated more cautiously.</div>"
        "<div class='small' style='margin-top:8px'>This report is read only. It proposes changes and provides "
        "operator instructions for review, but the agent runs none of them. Candidate estimates, Advisor findings, "
        "rightsizing and commitment alternatives may overlap. Savings are displayed as a total only after explicit "
        "reconciliation of currency, window, baseline and mutually exclusive choices. The spend percentage uses "
        "a normalized 30 day baseline, not invoice savings.</div>"
        f"<p>{_esc(data.get('reconciliation_notes', 'Savings not reconciled; individual opportunities only.'))}</p>"
        f"<p>{_esc('; '.join(data.get('notes', [])))}</p></div>"
    )

    parts = [header, summary_cards]
    if overview:
        parts.append(_group_title("FinOps overview"))
        parts.extend(overview)
    if candidates_html:
        parts.append(_group_title("Termination candidates"))
        parts.append(candidates_html)
    if findings_html:
        parts.append(findings_html)
    parts.append(limitation)
    parts.append("<div class='section'><h2>Sources</h2><ul>" + "".join(
        f"<li><a href='{_esc(source['url'])}'>{_esc(source['title'])}</a></li>"
        for source in sources if str(source.get("url", "")).startswith("https://learn.microsoft.com/")
    ) + "</ul></div>")

    document = document_shell(
        report_title,
        "".join(parts),
        extra_css=FINOPS_CSS,
        extra_js=SCRIPT,
        include_table_js=False,
        wrap_class="wrap wide",
    )

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    filename = f"finops-report-{stamp}.html"
    path = os.path.join(OUTPUT_DIR, filename)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(document)

    return {
        "assessment_status": assessment_status,
        "sources": sources,
        "report_path": f"/api/files/{filename}",
        "local_path": path,
        "summary": {
            "analyzed_spend": analyzed,
            "estimated_monthly_savings": savings,
            "savings_percent": round(pct, 1) if pct is not None else None,
            "findings_total": len(findings),
            "findings_by_band": priority_bands,
            "candidates_total": len(candidates),
            "candidates_by_band": candidate_bands,
            "currency": currency,
        },
    }


def _cli():
    import argparse
    import json
    import sys

    parser = argparse.ArgumentParser(description="Build a self contained HTML FinOps report.")
    parser.add_argument("--input", type=str, default=None, help="Path to a JSON file with report_data. Reads stdin if omitted.")
    parser.add_argument("--title", type=str, default="Azure FinOps Cost Optimization Report")
    parser.add_argument("--include-identifiers", action="store_true", help="Explicitly retain identifiers for an approved internal audience. Secrets remain filtered.")
    args = parser.parse_args()
    if args.input:
        with open(args.input, "r", encoding="utf-8") as handle:
            report_data = json.load(handle)
    else:
        report_data = json.load(sys.stdin)
    print(json.dumps(main(report_data=report_data, report_title=args.title, include_identifiers=args.include_identifiers), indent=2))


if __name__ == "__main__":
    _cli()
