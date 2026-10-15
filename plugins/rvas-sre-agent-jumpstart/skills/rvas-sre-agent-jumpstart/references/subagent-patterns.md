# Subagent Authoring Patterns

These are behavioral patterns for a subagent's `system_prompt` and its paired skill content —
how to shape the *content* of what [manifest-templates.md](manifest-templates.md) defines the
*shape* of. Apply them only when the settled use case's domain and safety requirements call for
them; none is mandatory for every subagent.

## Pattern: Exclusive Connector Tool Contract

Use this pattern when a subagent's entire value depends on one connector being the *only*
legitimate path to its evidence — for example a subagent that must never fall back to a local
or alternate access method because doing so would bypass an audit trail, a safety boundary, or a
permission model the connector enforces.

Declare the same named tool allowlist in both the subagent's `system_prompt` and its paired
skill, and make each of the following explicit rather than implied:

* **Named allowlist, not a category**: list the exact tool names the connector exposes (for
  example `<connector>/query`, `<connector>/describe-schema`) rather than a vague "use the
  connector's tools."
* **Forbidden fallback by class, not by name**: state that no alternate access path exists —
  "do not use any shell, CLI, or other connector to reach this data source" — so the boundary
  holds even against a tool the author didn't anticipate.
* **Hard stop-and-report on unavailability**: when the declared connector or a required
  credential/profile is unavailable, the subagent reports that fact and stops; it must not
  silently substitute a different method or guess at the answer.
* **Evidence-classification discipline**: every claim the subagent makes is labeled as one of
  `observation` (directly returned by the connector), `interpretation` (a reading of an
  observation), `hypothesis` (an untested explanation), or `recommendation` (a proposed action) —
  so a reader can tell what is verified fact versus inference.
* **Impact-ranked response contract**: when more than one finding exists, order them by impact
  (for example business or operational severity) rather than discovery order or alphabetically.

```yaml
# excerpt — system_prompt fragment
system_prompt: |-
  You are the <domain> specialist. You may use only these tools to investigate:
    - <connector-name>/<tool-1>
    - <connector-name>/<tool-2>
  Do not use any shell, CLI, file access, or other connector to reach this data — if
  <connector-name> is unavailable or a required credential is missing, stop and report that
  fact; do not substitute another method.
  Classify every claim you make as one of: observation, interpretation, hypothesis, or
  recommendation. Order findings by impact, highest first.
```

## Pattern: Skill Owns the Method, Prompt Owns the Boundary

Use this pattern whenever a subagent's investigative *procedure* is detailed enough to belong in
a paired skill rather than inline in the prompt — which is the common case once a procedure has
more than a couple of steps.

* The `system_prompt` delegates all procedural detail to its paired skill ("follow the
  `<skill-name>` skill's procedure for diagnosis and remediation") and does not restate steps
  the skill already owns.
* The `system_prompt` states only the boundaries that must never move regardless of which
  procedure runs:
  * **Read/write perimeter**: exactly what the subagent may change, if anything, without human
    approval.
  * **Evidence discipline**: the same observation/interpretation/hypothesis/recommendation
    labeling as above, when the domain benefits from it.
  * **Domain-specific weighting dimension**: the one axis findings get ranked by for this
    domain (cost, security exposure, latency, blast radius — whichever is the domain's actual
    stakes), stated explicitly so ranking is reproducible.
  * **Delivery channel**: where the output goes (a plan, a report, a specific format) — not a
    restatement of the skill's own `Output Format` section, just which channel receives it.
  * **Escalation triggers**: the specific conditions that mean "stop and hand off to a human or
    another subagent" rather than continuing automatically.

```yaml
# excerpt — system_prompt fragment
system_prompt: |-
  You are the <domain> specialist. Follow the <skill-name> skill's procedure for diagnosis
  and remediation end to end.
  Boundaries that never change regardless of procedure:
    - You may <read-only | the specific write action> without further approval; anything else
      requires explicit human confirmation first.
    - Rank findings by <the one domain-specific weighting dimension>, highest first.
    - Deliver findings to <the delivery channel>.
    - Escalate instead of acting when <the specific escalation trigger>.
```

## Optional: Offerable Custom-Instructions Block

Offer — never silently add — the following block as a candidate addition to the target agent's
own custom-instructions document when the settled interview reveals the agent will run CLI or
API commands as part of its investigations. This generalizes a command-verification discipline;
it excludes any application-specific confinement rule, since a folder or repository boundary is
not a reusable safety pattern across different targets.

```markdown
## Command Verification Contract

Before running any command:
1. Classify it as read-only or write. Treat anything uncertain as write.
2. Call the command's own help/usage output before its first use in a session, rather than
   assuming remembered syntax is still correct.
3. Resolve every argument from verified, current context (a prior command's actual output, not
   an assumption) — never from memory of a typical value.
4. Use the narrowest scope the command supports (a specific resource, not a wildcard; a single
   item, not a batch) unless the task explicitly requires broader scope.
5. Inspect the command's result before treating it as evidence — a non-error exit code alone
   does not confirm the expected effect happened.
6. Never retry a failed command blindly with the same arguments; diagnose why it failed first.
7. For any write command, run the read-only equivalent (a dry-run, a `GET`, a plan/diff) first,
   then verify the actual effect with another read afterward.
```

Present this as one offer during the interview or approval phase, not as a default inclusion —
the target agent's own custom instructions may already cover some or all of this, and the user
may prefer a different phrasing or scope.
