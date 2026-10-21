# Optional trigger: readiness gate in a change process

Unlike the sweep skills, readiness is run on demand against a specific scope, usually as a gate in a change or release process rather than on a schedule.

## Wiring it as a gate

- Trigger: from your change or release process, or on request, before a launch or migration.
- Response agent: the pre_change_readiness custom agent, or the main agent.
- Autonomy: Review. The verdict informs a human decision; the skill changes nothing.

## Task instructions

Check readiness for the target scope before the change.

1. Use the pre-change-readiness skill.
2. Run readiness_check.py with the target subscription id and optional resource group to run the reliability, exposure, and capacity checks scoped to it.
3. Produce the self contained HTML report and post the file link with a short summary: the overall verdict, the per category verdicts, and the blocking findings to clear before shipping.
4. If the overall verdict is caution or no-go, list the exact findings that must be cleared to reach go, and suggest re running the check after they are addressed.

Do not change anything. The skill reports readiness for a human to act on.
