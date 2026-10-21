# Postmortem template

The structure the renderer expects, and the prompts to fill each part. Assemble a JSON object with these keys and pipe it into tools/postmortem_render.py.

## Structure and prompts

- title: a short, neutral incident name, for example "Checkout latency, 9 July 2026".
- incident_id: your tracking reference, if any.
- severity: the incident severity your organisation uses (for example Sev2).
- status: Resolved, or Monitoring if a follow up is still open.
- assessment_status: Complete, Partial or Not assessed, describing evidence collection, not approval to share. Failed or unknown evidence must not be marked Complete.
- sources: a list of `{title, url}` entries for the incident evidence.
- collection_errors: a list of failed or incomplete evidence reads, when applicable.
- summary: three or four sentences a busy reader can stop at. What happened, who or what was affected, how long, and how it was resolved.
- impact: an object with
  - duration: from first symptom to all clear, and the time to detect and time to mitigate if known.
  - scope: which services, regions, or customers were affected, and how many.
  - customer: the customer facing effect in plain terms (for example errors on checkout for some users).
- timeline: a list of {time, event}, from detection to resolution. Include detection, escalation, the key diagnostic steps, the mitigation, and the all clear. Use a consistent time zone and label it.
- root_cause: the chain of conditions that made the incident possible, stated in terms of systems. Separate the trigger (what set it off) from the underlying weakness (why the trigger had that effect).
- contributing_factors: a list of the conditions that made it worse or slower to resolve, for example a missing alert, an unclear runbook, or a single point of failure.
- detection: how the incident was detected, and how long that took. If detection was slower than it should be, say so; that is often its own action item.
- resolution: what actually restored service, and whether it was a fix or a mitigation that needs a durable follow up.
- lessons: an object with three lists, went_well, went_wrong, and got_lucky. The got_lucky list is where near misses hide.
- action_items: a list of {action, owner, due, type}. type is Prevent, Detect, or Mitigate. Each item must be specific, owned, and dated, and should address an underlying weakness, not only the trigger.

## Minimal example

All rendered documents remain drafts for human evidence and sharing review. Default output sanitizes identifiers and credentials; no automatic external send is performed. Use `--include-identifiers` only for an explicitly requested internal draft.

```
{
  "title": "Checkout latency, 9 July 2026",
  "severity": "Sev2",
  "status": "Resolved",
  "summary": "Checkout responses slowed for about 40 minutes after a configuration change reduced the connection pool. Some customers saw timeouts. Rolling back the change restored service.",
  "impact": {"duration": "40 minutes, detected in 12", "scope": "Checkout API, West Europe", "customer": "Intermittent timeouts for a minority of checkout requests"},
  "timeline": [{"time": "10:02 UTC", "event": "Config change deployed"}, {"time": "10:14 UTC", "event": "Latency alert fired"}, {"time": "10:42 UTC", "event": "Change rolled back, latency normal"}],
  "root_cause": "A configuration change lowered the database connection pool below peak demand (trigger). The pool size had no guardrail or review check, and no alert watched pool saturation (underlying weakness).",
  "contributing_factors": ["No alert on connection pool saturation", "Change review did not flag the pool setting"],
  "detection": "A latency metric alert fired 12 minutes after the change. Customer reports had not yet arrived.",
  "resolution": "Rolling back the configuration change restored service. This was a mitigation; a durable fix sets a safe minimum pool size.",
  "lessons": {"went_well": ["Alert caught it before customer reports"], "went_wrong": ["No guardrail on the pool setting"], "got_lucky": ["Change happened at low traffic; peak would have been worse"]},
  "action_items": [{"action": "Add a saturation alert on the connection pool", "owner": "Platform team", "due": "2026-07-23", "type": "Detect"}, {"action": "Set and enforce a safe minimum pool size", "owner": "Checkout team", "due": "2026-07-30", "type": "Prevent"}]
}
```
