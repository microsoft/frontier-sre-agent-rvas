# Report mapping

The incident report uses the shared generator, tools/report_render.py. Unlike the estate wide skills, the agent assembles the report_data here, because the timeline, the hypotheses, and the mitigations come from the agent's reasoning over the gathered evidence. Then pipe it in:

```
echo '<report_data json>' | python tools/report_render.py
```

## report_data to assemble

- title: "Incident Report: <resource name>". subtitle: the one line probable cause with its confidence.
- generated_for: the incident or alert reference.
- meta: window is the lookback used, scope is the affected resource, source is "Resource Health, Activity Log, Monitor".
- summary_cards: current health, symptom start, impact (what is affected), and probable cause confidence.
- charts: optional. A small bar of neighbouring resource health counts (Available, Degraded, Unavailable) can help; omit if not useful.
- findings: the timeline. Columns time, source, signal, detail, severity. Rows are the change and health events from gather_context plus any metric or log evidence you add, most recent first. Set _band per row from the event severity.
- candidates: the ranked mitigations. For each set resource to the mitigation name, resource_type to "Mitigation", reason to the hypothesis it addresses, next_step to the check that confirms it, confidence to a 0 to 100 value, band to Very high, High, Medium, or Low, and command to the exact command a human runs. The renderer shows a copy button on the command.
- method_notes: the ranked hypotheses, each as one line with its evidence and confidence, and the honest note that correlation is not proof, plus any scope not assessed.

## How gather_context maps in

The evidence object from gather_context provides:

- current_health: use it in the summary card and as the first timeline row.
- timeline: change events from the Activity Log and health transitions, already severity tagged and sorted. These become the findings rows.
- neighbors: same resource group inventory only, not proven dependencies or health observations. Do not construct a neighbour health chart without separate health evidence.
- assessment_status, sources and notes: preserve collection completeness and caps in the derived report. Additional failed metric or log reads can only reduce completeness.

Add your metric and log evidence as extra timeline rows so the whole story sits in one table.
