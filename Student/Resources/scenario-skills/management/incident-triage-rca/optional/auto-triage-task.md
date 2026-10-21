# Optional automatic first pass on alert

Unlike the estate wide skills, incident triage is not a scheduled sweep. It is most useful triggered the moment an alert fires, so an on call engineer opens a ready made first pass instead of a blank page.

## Wiring it to an alert

Two common ways to trigger this skill automatically:

- Action group to the agent: on the alert rule's action group, add the action that notifies this SRE Agent, passing the affected resource id from the alert payload.
- Scheduled or event task: create a task whose instruction is the block below, and trigger it from your incident tool or a webhook when an incident opens.

- Name: Incident triage first pass
- Response agent: the incident_triage_rca custom agent, or the main agent.
- Autonomy: Review. Mitigations always wait for a human.

## Task instructions

An alert fired or an incident opened for a resource. Produce a triage first pass.

1. Use the incident-triage-rca skill.
2. Take the affected resource id from the alert or incident payload. Run gather_context.py on it, then pull the metrics around the symptom start and a focused error log query.
3. Build the timeline, write two to four ranked hypotheses tied to evidence with confidences, and propose safe mitigations with the exact command and the check to confirm each.
4. Produce the self contained HTML incident report and post the link with a short summary: symptom and impact, probable cause and confidence, timeline highlights, and the first mitigation to try.

Do not restart, scale, or change any resource. Every mitigation is a proposal a human runs.
