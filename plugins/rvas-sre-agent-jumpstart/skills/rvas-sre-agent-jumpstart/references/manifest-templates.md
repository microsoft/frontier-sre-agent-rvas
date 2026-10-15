# Capability Manifest Templates

Every capability this skill authors is a `azuresre.ai/v1` YAML+Markdown manifest pair (for a
skill) or a standalone YAML manifest (for a subagent, scheduled task, connector, or incident
filter) — this is the human-reviewable `spec` content presented in the plan for approval.
Applying it means running the copied, pre-built `apply.ps1`/`apply.sh` script pair (see
[iac-surfaces.md](iac-surfaces.md#surface-2-capability-authoring-self-contained--this-skills-own-mechanism)
and the Apply Script Convention below), which `PUT`s the properties as a plain (not
base64-encoded) JSON body to the agent's own data-plane `extendedAgent` REST API — this skill's
own turn never calls that API directly. Match these templates exactly — do
not invent new top-level fields; the agent's resource schema (confirmed via the Research Step's
live fetch) rejects unknown keys such as `agent_type` on a subagent. This file documents every
manifest kind this skill's own interview and plan ever author — Skill, SubAgent, ScheduledTask,
Connector/ConnectorV2, and IncidentFilter, plus the Knowledge File convention. The copied apply
scripts also recognize `Tool`, `CommonPrompt`, `Hook`, and `Plugin` kinds for forward
compatibility with manifests a user may author by other means, but this skill itself never
generates those kinds, so no template for them is needed here. Every template below uses
placeholder names only, and no bundled example files ship alongside it.

## Artifact Directory Layout

Write every authored file under a canonical `azure-sre-agent-config/` directory at the
repository root (reuse it only if it already exists there; otherwise create it fresh at the
repository root — see [iac-surfaces.md](iac-surfaces.md)). Do not search elsewhere in the
repository for a differently-placed or differently-named directory to reuse.
Surface 1 (agent-resource-provisioning) IaC files, if any are generated, live in their own
`infra/` subdirectory inside this same tree — kept separate from the capability manifests, never
interleaved file-by-file:

```
azure-sre-agent-config/
├── skills/
│   ├── <skill-name>.yaml
│   ├── <skill-name>.md
│   └── <skill-name>/references/<supporting-file>.md   # only if deep reference material is needed
├── subagents/
│   └── <subagent-name>.yaml
├── automations/
│   ├── scheduled-tasks/
│   │   └── <task-name>.yaml
│   └── incident-filters/
│       └── <filter-name>.yaml
├── connectors/           # only touch if the settled plan adds/changes a connector
├── knowledge/files/      # only touch if the settled plan uploads new knowledge documents
├── scripts/              # Surface 2 only — copied, pre-built apply.ps1/apply.sh pair, see
│                          # Apply Script Convention below
├── infra/                # Surface 1 only — Terraform/Bicep files the fetched recipe generates;
│                          # never mixed into the capability-manifest subdirectories above
├── custom-instructions.md
└── README.md
```

Only create the subdirectories and files the settled plan actually calls for — do not scaffold
empty sibling directories you have no content for, and do not invent additional top-level
directories beyond what's shown here without a concrete need from the plan.

## Apply Script Convention

Whenever Surface 2 applies, `scripts/apply.ps1` and `scripts/apply.sh` are copied unmodified
from this skill's own `assets/scripts/` — never templated, never regenerated, and never
re-authored per plan. Both files are always copied together as a pair. See
[iac-surfaces.md](iac-surfaces.md#surface-2-capability-authoring-self-contained--this-skills-own-mechanism)
for the full contract each script implements (required parameters, manifest discovery,
preflight and exit codes, REST shape, kind-name mapping, and the `AgentConnector` ARM
exception) — not restated here to keep that contract in one place.

* **OS parity**: `apply.ps1` and `apply.sh` implement equivalent discovery, preflight,
  apply, and verification semantics, so a user on either OS gets the same guarantees, subject to
  each platform's own dependencies (for example `curl`/`jq` on bash vs. `Invoke-RestMethod` on
  PowerShell) and native error-handling conventions.

## Skill Manifest

Author the YAML as `skills/<skill-name>.yaml` and its paired Markdown as
`skills/<skill-name>.md`, following this shape exactly and opening with the Provenance Comment
Convention below:

```yaml
# <one-line provenance / history comment: new vs. consolidated, and why>
# Source: <official Learn URL this skill's procedure is grounded in>
api_version: azuresre.ai/v1
kind: Skill
metadata:
  name: <skill-name>
spec:
  description: <single sentence: what it diagnoses/remediates, the specific signals it correlates, and the remediation boundary>
  files:
    - ./<skill-name>.md   # required: the apply script inlines only this first entry as skillContent
    - ./<skill-name>/references/<supporting-file>.md   # optional: stays a local reference file,
                                                        # never uploaded or inlined — cite its
                                                        # relative path from the Markdown body instead
  tools:
    - RunAzCliReadCommands
    - QueryLogAnalyticsByWorkspaceId
    - GetAzCliHelp
    # add RunAzCliWriteCommands only when the active trigger explicitly permits remediation
```

```markdown
---
name: <skill-name>
description: <identical to the YAML spec.description>
---

# <skill-name>

<one or two sentences: what operational problem this solves and why it's scoped this way>

## Trigger Conditions

Load this skill when the user reports any of the following:

- <concrete symptom 1>
- <concrete symptom 2>

## Tool Selection Decision Tree

| Symptom | First diagnostic | Why |
| --- | --- | --- |
| <symptom> | <tool/command> | <one-line reason> |

## Non-Goals

- Do not <action> unless the active trigger permits it and evidence identifies the exact minimal change.
- Do not assume <single source of evidence> is the only truth; correlate with <second source>.

## Procedure

1. <evidence-gathering step>
2. <correlation step>
3. <root-cause classification step>
4. Recommend or execute the smallest reversible remediation allowed by the active trigger, then verify end to end.

## Evidence Required

- <what must be cited in the final report>

## Output Format

<the report shape: impacted resource, evidence, root cause, confidence, remediation, verification>

## Escalation

<when to hand off instead of acting, and to whom>

## Related Skills

- <other skill names this one hands off to or is consolidated with>

## Official Sources

- <Learn URL(s)>
```

Keep the skill's `description` under roughly one sentence of genuine density — this is what the
agent's own routing uses to decide whether to load the skill, so vague or overlapping wording
risks silent mis-routing between skills.

## SubAgent Manifest

Author as `subagents/<subagent-name>.yaml`, following this shape exactly and opening with the
Provenance Comment Convention below:

```yaml
# <provenance comment: where this subagent's domain/scope came from>
# Run mode (<date>): <Autonomous | approval-gated>, and why this scope chose it.
api_version: azuresre.ai/v1
kind: SubAgent
metadata:
  name: <subagent-name>
spec:
  description: <one sentence: the domain this specialist owns>
  enable_skills: true
  allowed_skills:
    - <skill-name-1>
    - <skill-name-2>
  handoff_description: <one sentence written for the meta-agent's routing decision>
  system_prompt: |-
    You are the <domain> specialist for <project/service>.
    Ground investigations in <named evidence sources>.
    <State run mode explicitly: either "You run in fully Autonomous mode: perform diagnostics,
    correlation, AND remediation end to end without waiting for approval," or "Investigate and
    recommend; do not execute a write action without explicit human approval.">
    For each in-scope scenario: <numbered investigate-then-act-then-verify steps>.
    <Explicit out-of-scope statement and where to defer instead, if another subagent owns an
    adjacent domain.>
    Always report impacted resource, observed evidence, probable root cause, confidence, the
    exact command run (if any), the verification result, and any restore step for demo fault
    scripts.
  tools:
    - SearchMemory
    - RunAzCliReadCommands
    # add RunAzCliWriteCommands only in Autonomous run mode with an explicit remediation scope
    - GetAzCliHelp
    - QueryLogAnalyticsByWorkspaceId
  mcp_tools:
    - microsoft-learn-mcp/*   # only when the subagent's procedure needs live Learn docs
  handoffs: []
```

Declare the run mode only in this manifest's `system_prompt` and comments, and on the response
plan or scheduled task that invokes the subagent — never invent a top-level `agent_type` or
`run_mode` field; the agent's resource schema does not define one and rejects unknown keys.

## ScheduledTask Manifest

Author as `automations/scheduled-tasks/<task-name>.yaml`, following this shape and opening with
the Provenance Comment Convention below:

```yaml
# <one-line purpose and cadence rationale>
api_version: azuresre.ai/v1
kind: ScheduledTask
metadata:
  name: <task-name>
spec:
  description: <one sentence: what this recurring review covers>
  schedule: "<cron expression>"
  time_zone: UTC
  enabled: true
  agent: <subagent-name>
  mode: Autonomous   # scheduled tasks are read-only/report-only by convention; state explicitly if not
  prompt: >-
    <the full numbered investigation/report prompt, written the same way a one-off investigation
    request would be, including an explicit statement of what it must NOT do (e.g. "Recommend
    only; change nothing" for a read-only review)>
```

## Provenance Comment Convention

Open every manifest file — every kind listed in this document — with a short comment block
before `api_version:` that records why the manifest exists and where its procedure came from.
At minimum, state:

* **Why**: the specific operational need this manifest addresses (one line).
* **History**: `new` for a first authoring, or `consolidated from <prior-skill-names>` when this
  manifest folds in capability that used to live elsewhere (see the Skill-Cap Branch in
  [interview-design-tree.md](interview-design-tree.md)).
* **Date**: the authoring or last-consolidation date.
* **Source**: the official Learn URL (or other authoritative reference) the procedure is
  grounded in, when one exists.

```yaml
# Why: <one-line operational need this manifest addresses>
# History: new | consolidated from <prior-skill-name-1>, <prior-skill-name-2>
# Date: <YYYY-MM-DD>
# Source: <official reference URL, or 'none' when the procedure is purely interview-derived>
api_version: azuresre.ai/v1
kind: <Skill | SubAgent | ScheduledTask | Connector | ConnectorV2 | IncidentFilter>
# ...rest of the manifest
```

A reader opening any authored manifest months later should be able to tell, from this block
alone, why it exists and whether its procedure is still grounded in a current authoritative
source — never rely on commit history or an external document to answer that.

## Connector Manifest

Only author a connector manifest when the settled interview names a data source the target
agent does not already have connected — confirmed from the user's own settled answer (asked
during the interview if genuinely unknown, never assumed), since the skill's own turn never
issues a live `GET`. The copied apply script's preflight step (see
[iac-surfaces.md](iac-surfaces.md#surface-2-capability-authoring-self-contained--this-skills-own-mechanism))
independently re-checks for a name collision before applying, surfacing one there if the user's
answer was stale by the time they run the script. Two distinct shapes exist — confirm which one
the fetched REST API reference names for the chosen connector type before authoring, since they
are not interchangeable:

### Shape A: ARM-Managed MCP Connector

Used for a connector that exposes an MCP endpoint through the agent's own ARM-managed resource,
authenticated by a header-based credential:

```yaml
# Why: <one-line operational need this connector addresses>
# History: new
# Date: <YYYY-MM-DD>
# Source: <fetched REST API reference URL>
api_version: azuresre.ai/v1
kind: Connector
metadata:
  name: <connector-name>
spec:
  dataConnectorType: Mcp
  endpoint: <mcp-endpoint-url>
  extendedProperties:
    authType: <header-based-auth-scheme, e.g. ApiKey or Bearer>
    # additional header/credential fields as the fetched reference names them
```

### Shape B: Data-Plane OAuth Connector (ConnectorV2)

Used for a connector that authenticates via OAuth at the data-plane level rather than through an
ARM-managed MCP endpoint:

```yaml
# Why: <one-line operational need this connector addresses>
# History: new
# Date: <YYYY-MM-DD>
# Source: <fetched REST API reference URL>
api_version: azuresre.ai/v1
kind: ConnectorV2
metadata:
  name: <connector-name>
spec:
  apiName: <provider-api-name>
  connectionName: <connection-name>
  requireApprovalTools:
    - <tool-name-requiring-human-approval-before-use>
    # list every tool this connector exposes that should not run unattended; omit the key
    # entirely when every tool from this connector is safe to run without approval
```

Never invent a third shape or mix fields between the two — confirm the exact shape and property
names from the Research Step's live fetch each time, since this is a preview surface.

## IncidentFilter Manifest

Only author an incident filter when the settled interview calls for routing specific incoming
incidents to a particular subagent rather than relying on default routing. Author as
`automations/incident-filters/<filter-name>.yaml`:

```yaml
# Why: <one-line routing need this filter addresses>
# History: new
# Date: <YYYY-MM-DD>
# Source: none (interview-derived routing rule)
api_version: azuresre.ai/v1
kind: IncidentFilter
metadata:
  name: <filter-name>
spec:
  incidentPlatform: <platform-name, e.g. the connected incident-management system>
  priorities:
    - <priority-level-this-filter-matches>
  titleContains:
    - <substring-that-must-appear-in-the-incident-title>
  titleNotContains:
    - <substring-that-must-not-appear, to avoid overlapping with another filter>
  handlingAgent: <subagent-name>
  agentMode: Autonomous   # or approval-gated — state explicitly, matching the settled run mode
  maxAutomatedInvestigationAttempts: <integer>
```

Keep `titleContains`/`titleNotContains` narrow enough that two filters never both match the same
incoming incident — an ambiguous match is worse than an unrouted one, since it hides which
subagent actually handled it.

## Knowledge File Convention

Only author knowledge files when the settled interview calls for domain reference material the
target agent's skills need but should not duplicate inline (for example a reusable lookup table
cited by more than one skill). Write each file under a topic-scoped subdirectory:

```
azure-sre-agent-config/
└── knowledge/files/<topic>/
    └── <reference-file-name>.md
```

Structure the reference content as a source-cited table rather than prose, so skills can cite a
specific row as evidence:

```markdown
# <Topic> Reference

| <Dimension, e.g. lever/signal> | <What to check> | <Guardrail or threshold> | Source |
| --- | --- | --- | --- |
| <item> | <concrete check> | <guardrail> | <authoritative reference or 'interview-derived'> |
```

Cite the specific row (not just the file) from any skill `Procedure` or `Evidence Required`
section that depends on it, so the evidence chain stays traceable from report back to source.

## Choosing Which Manifests to Generate

Only generate the manifest kinds the settled interview and plan actually call for:

* A skill pair is the default when the use case is a bounded diagnostic/remediation procedure.
* A subagent is needed only when the use case defines a durable specialist domain distinct from
  existing subagents — decide from the settled interview and research, and prefer extending an
  existing one's `allowed_skills` over creating a new subagent when the user's own answer says
  one already exists, consistent with the skill-cap discipline in
  [interview-design-tree.md](interview-design-tree.md). The copied apply script's preflight (per
  [iac-surfaces.md](iac-surfaces.md#surface-2-capability-authoring-self-contained--this-skills-own-mechanism))
  independently re-checks for a name collision before applying.
* A scheduled task is needed only when the use case is explicitly recurring (a periodic review),
  not a one-time or incident-triggered diagnostic.
* A connector is needed only when the settled use case names a data source not already connected
  (per the Connector Manifest section above).
* An incident filter is needed only when the settled use case requires routing specific incoming
  incidents to a particular subagent rather than relying on default routing.
* A knowledge file is needed only when the settled use case needs reusable reference material
  that more than one skill would otherwise have to duplicate inline.

