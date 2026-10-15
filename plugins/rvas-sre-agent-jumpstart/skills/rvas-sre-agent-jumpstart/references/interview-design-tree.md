# Interview Design Tree

Follow the `grilling` skill's round/frontier protocol exactly: ask the whole
settled frontier in one round, one question per decision, each carrying a recommended answer,
and wait for the user's answers before the next round. Per that protocol, present each round
through the `ask_user`-style structured-form tool when one is available — one field per
question below, titled/described from the question, defaulted to the recommended answer — and
fall back to the plain-text `❓ **Qn**` / `➡️` layout shown below only when no such tool exists.
Finding facts is always this skill's job, never the user's — dispatch a sub-agent for anything
the filesystem, Azure CLI, or the target agent's current configuration can answer, and ask the
rest of the frontier now rather than blocking on it.

## Round 1: Root Frontier

These questions have no prerequisites and are always asked first. (Shown in the plain-text
fallback form; route them through `ask_user` instead whenever that tool is available.)

```
❓ **Q1** - **New agent or existing agent?**: Are you provisioning a brand-new Azure SRE Agent
resource, or adding a capability to an agent that already exists?

➡️ Answering "existing" alone is enough — this skill never needs your resource group or agent
name; the apply script you run after approval takes them as its own parameters.

---

❓ **Q2** - **Do you have an architecture diagram?**: Do you have an architecture diagram of the
system the agent will operate on, that you can share with this skill?

➡️ No recommended default — this is a factual yes/no, not a judgment call. Encourage sharing a
diagram when one exists: it grounds candidate use cases in the actual depicted topology rather
than a verbal description alone. This question gates which of Q2a/Q2b runs next; it is never
skipped.

---

❓ **Q2a** (asked only if Q2 = yes) - **Share the architecture diagram**: Attach the diagram now.

➡️ No recommended default. Once attached, read the diagram to identify the depicted resources
and topology, then activate
the `azure-sre-agent` skill and cross-reference those
resources against its Troubleshooting, Architecture & Design Patterns, and Integrations &
Coding Patterns categories to propose 2-3 candidate use cases, connectors, and knowledge
sources grounded in that lookup. Present these candidates to the user and let them pick or
redirect rather than committing to a candidate unconfirmed; the user's confirmed choice becomes
the settled use case (standing in for Q2b) and the interview then continues as normal from Q3.

---

❓ **Q2b** (asked only if Q2 = no) - **What operational problem are you solving?**: Describe the
use case in your own words — for example "SQL query timeouts," "asymmetric network routing,"
"AKS SNAT port exhaustion," or anything else. There is no fixed list; name whatever you're
actually facing.

➡️ No recommended default — treat whatever the user names as the input to the research step
rather than offering a fixed menu of use cases. Once answered, the interview continues as
normal from Q3.

---

❓ **Q3** - **Run mode**: Should the resulting capability run in fully autonomous mode
(diagnose and remediate without waiting for approval) or with a human approval gate before any
write action?

➡️ Recommend an approval gate by default for anything touching production-like resources;
autonomous mode is appropriate only when every in-scope action has a verified restore or
rollback path.

---

❓ **Q4** - **Connectors or knowledge sources**: Does this use case need a connector (for
example Log Analytics, PagerDuty, Dynatrace, GitHub) or a knowledge file beyond what
`.agents/skills/azure-sre-agent` already indexes?

➡️ If Q2 settled "yes" (diagram path, Q2a ran) and Q2a's proposal named at least one
candidate connector or knowledge source, restate those proposed candidates and ask the user to
confirm or override them rather than asking this question cold a second time. Otherwise —
whether Q2b ran instead, or Q2a ran but proposed no connector/knowledge-source candidates —
default to "research will tell us": leave this open if the user doesn't already know; the
research step (`references/iac-surfaces.md`) resolves it from the settled use case.
```

## Round 2: Fact-Finding (Agent-Owned, Never Asked)

Whenever Q1 settles on "existing agent," "existing agent" is now just that settled Q1 answer
(new vs. existing) — nothing else needs resolving during the interview. Confirming the named
agent actually exists, its current skill/subagent/connector state, and any name collision are
all deferred to the generated apply script's own preflight step (see the Skill-Cap Branch below
and [iac-surfaces.md](iac-surfaces.md#surface-2-capability-authoring-self-contained--this-skills-own-mechanism));
this skill's own turn never attempts to resolve any of this, live or otherwise.

Never ask the user "how many skills does your agent have" — the apply script finds it at run
time; read that script's preflight output instead of counting manually.

Also resolve the IaC surface itself from Q1's answer as soon as Q1 is settled, rather than
asking it as a separate question: a brand-new agent needs resource provisioning first, then
usually capability authoring right after; an existing agent usually needs capability authoring
only. State this resolved default to the user alongside the Round 1 response as a confirmed,
overridable assumption — do not ask it as a question in the common case. The rare case where an
existing agent still needs resource provisioning is covered separately in Round 3 below.

## Round 3: Child Branches (Unlocked by Round 1 Answers)

Once Q1, Q2 (plus whichever of Q2a/Q2b it unlocked), Q3, Q4 settle, ask only the questions the
settled answers actually unlock:

* If Q1 settled on "existing agent" and the named use case, or the Round 2 fact-finding result,
  suggests resource provisioning might still be needed (for example a new region, a new
  environment, or a disaster-recovery pair) — ask the user to confirm the IaC surface
  explicitly before research begins, defaulting to "capability authoring only" if the user has
  no objection. Skip this question entirely in the ordinary existing-agent case where nothing
  suggests provisioning is needed.
* If the resolved IaC surface includes agent-resource provisioning, do not ask an interview
  question about the IaC backend — that choice depends on options the Research and plan phase
  has not fetched yet. Instead, note the open backend decision as a line item the plan will
  settle, and let the Research and plan phase fetch the actual options from
  `.agents/skills/azure-sre-agent`'s Deployment category, propose whichever that fetch names as
  the simplest default, and present the choice for the user to confirm or override at the
  approval gate (do not assume Bicep or any other backend name ahead of that fetch).
* Tell the user, as a heads-up rather than a question, that the Research and plan phase runs
  next and is mandatory — there is no yes/no gate to skip it.
* If Q4 named a connector whose minimum required inputs the user has not already supplied: ask
  for those minimum connection details (for example a Log Analytics workspace ID) — never by
  checking whether the connector is already configured on the live agent, only by checking
  whether the user has already given the needed values — recommending read-only
  diagnostic connectors as the default scope.

## Skill-Cap Branch (Unconditional for Every Existing-Agent Path)

This branch always runs when Q1 settles on "existing agent," regardless of use case, and never
waits for the user to ask about it:

1. State the plan's `## Skill-Cap Check` recommendation based on the authored manifest set —
   the generated apply script (see
   [iac-surfaces.md](iac-surfaces.md#surface-2-capability-authoring-self-contained--this-skills-own-mechanism))
   independently re-verifies the live count at run time and hard-stops if the plan's assumption
   no longer holds (for example another change applied the agent's sixth skill between plan
   approval and script execution).
2. If the count is already at 5, or would reach 5 after adding the new capability being planned,
   surface a warning naming the specific at-risk recommendation — do not use a generic cap
   reminder. Model the warning's shape and recommended resolution on the Provenance Comment
   Convention's `History` field in
   [manifest-templates.md](manifest-templates.md#provenance-comment-convention): name which
   existing skill the new capability could be folded into instead of added as a sixth.
3. Put the resolution to the user as an explicit decision — accept the consolidation, accept
   the cap risk and proceed anyway, or stop — never resolve it silently on the user's behalf,
   since it changes what gets deployed. "Stop" means the apply script already stopped for you
   (non-zero exit, nothing applied, by default) — rerun it with `-Force` (`apply.ps1`) or
   `--force` (`apply.sh`) only once you've made the explicit choice to accept the risk.

The session is done when this frontier is empty: Q1, Q2 (and its unlocked Q2a or Q2b), Q3, Q4,
every unlocked child branch, and (for an existing agent) the skill-cap branch have all been
visited and nothing is left silently assumed.
Do not move to the research-and-plan phase until the user has confirmed a shared understanding.
