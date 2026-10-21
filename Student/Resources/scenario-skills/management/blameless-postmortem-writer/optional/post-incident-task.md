# Optional post incident task

A postmortem is written once per incident, so this is not a scheduled sweep. It is most useful triggered when an incident is marked resolved, so a first draft is waiting for the team's review meeting.

## Wiring it after an incident

- Trigger: from your incident tool when an incident moves to Resolved, or on request.
- Response agent: the blameless_postmortem_writer custom agent, or the main agent.
- Autonomy: Review. A human always reviews and edits the draft before it is shared.

## Task instructions

An incident was resolved. Draft a blameless postmortem.

1. Use the blameless-postmortem-writer skill.
2. Gather the facts from the incident record, any prior incident report, and the Activity Log and Resource Health for the affected resources. Build the timeline from first symptom to all clear, with time to detect and time to mitigate.
3. Write it blameless: separate the trigger from the underlying weakness, and write specific, owned, dated action items balanced across Prevent, Detect, and Mitigate.
4. Produce a sanitized local HTML draft and a short summary for review. Do not automatically post a link, upload, email or send externally. The incident owner must review the evidence, sanitization, impact and action items before approving sharing.

Mark the draft as a draft for the team to review. Name any unknown fact as an action item rather than guessing it.
