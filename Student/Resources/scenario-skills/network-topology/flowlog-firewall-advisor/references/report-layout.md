# Report layout

The shape `flowlog_firewall_advisor.py` prints on standard output and
`report_render.py` consumes. Keys match the shared renderer exactly.

```json
{
  "title": "Flow log firewall advisor",
  "subtitle": "Azure Firewall network rules derived from observed virtual network traffic",
  "meta": { "window": "...", "scope": "...", "source": "..." },
  "summary_cards": [ { "label": "...", "value": "...", "sub": "..." } ],
  "charts": [ { "title": "...", "unit": "bytes", "items": [ { "name": "...", "value": 0, "band": "High" } ] } ],
  "findings": { "title": "...", "columns": [ { "key": "...", "label": "..." } ], "rows": [ { "_band": "High" } ] },
  "candidates": [ { "resource": "...", "band": "High", "confidence": 0, "reason": "...", "next_step": "...", "command": "..." } ],
  "method_notes": [ "..." ]
}
```

## Ordering, and why

The renderer emits sections in a fixed order, and this skill uses that deliberately.

1. **Summary cards.** Proposed rules, critical and high count, policy budget consumed,
   and how many connections were excluded because they are already blocked. The
   exclusion count sits on the front page on purpose: it is the number that stops a
   reader assuming the rule set is the whole picture.
2. **Chart.** Volume split between traffic crossing the virtual network boundary and
   traffic staying inside it. Boundary traffic is banded High so it draws the eye,
   because that is the part a firewall actually changes.
3. **Findings.** One row per proposed rule, sortable and filterable by severity. Every
   row carries `_band` so the renderer can colour the left border and drive the filter.
4. **Candidates.** The same rules as action items, with a Bicep snippet in `command`
   so the renderer gives it a copy button.
5. **Method notes.** The window, the exclusions, and the limits. Always present.

## Band mapping for candidates

The findings table uses severity, where Critical is worst. The candidates table uses
confidence, where Very high is best. These are opposite scales, so the mapping is
inverted on purpose:

| Finding severity | Candidate confidence | Reading |
|---|---|---|
| Critical | Low | Do not adopt this rule without a decision |
| High | Medium | Adopt only once the destination is understood |
| Medium | High | Adopt, consider narrowing |
| Low | Very high | Lower review priority, still requires intent validation and staging tests |

These are heuristic review labels, not proof that a rule is safe to adopt.
Flow records do not establish business intent, application delivery or completeness.

## Method notes always included

Written on every run, whether or not anything was flagged, because their absence would
imply a completeness the data cannot support:

- The window analysed, and that traffic outside it is absent from the rules.
- That consolidation is lossless, and that host to subnet widening is listed separately.
- The count of connections permitted at one point and denied at another.
- The count of platform flows excluded.
- That these are network rules only, and application rules need names the flow logs do
  not carry.
- That derived rules remain drafts until isolated staging tests, owner approval and a controlled deployment with rollback.
- The exact policy budget formula: `protocolCount * sourceCount * destinationCount * ceil(portCount / 14)`.
- Assessment status, source URLs, actual logging target filters and skipped workspaces.
