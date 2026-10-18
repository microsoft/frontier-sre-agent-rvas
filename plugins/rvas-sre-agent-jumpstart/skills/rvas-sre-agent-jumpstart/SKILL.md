---
name: rvas-sre-agent-jumpstart
description: >
  Sets up or extends an Azure SRE Agent. Use when someone wants to provision a new Azure SRE
  Agent resource, or give any agent a new capability for an operational problem (SQL
  troubleshooting, network asymmetry, AKS SNAT exhaustion, or anything else) — including when
  they're unsure which of the two IaC paths, agent-resource provisioning or capability
  authoring, applies to their request.
compatibility: Requires network access. Uses mcp_microsoftdocs:microsoft_docs_fetch or
  fetch_webpage (via the azure-sre-agent pointer skill) to fetch Learn pages during the
  Research Step.
---

# SRE Agent Jumpstart Skill

Guide a user from an operational need to a working Azure SRE Agent capability or a newly
provisioned agent resource — always plan first, then generate artifacts only after the user
approves the plan.

## How This Skill Works

This skill has five phases, always in this order:

1. **Interview** — grill the user through an SRE-agent-specific design tree (reusing the
   `grilling` skill's round/frontier protocol) to settle whether the target is a
   new or existing agent, which IaC surface(s) apply, the named use case, run mode, and
   connector and knowledge needs. See
   [references/interview-design-tree.md](references/interview-design-tree.md).
2. **Research and plan** — activate the `azure-sre-agent` skill
   and follow its own Category Index procedure directly (its stated fetch tooling and freshness
   check) rather than re-describing that procedure here; layer only the use-case-specific
   lookup on top — always perform an additional targeted lookup for the named use case's
   domain, grounded in fetched documentation rather than any existing file in the target
   repository. Emit exactly one reviewable Markdown
   plan naming the IaC surface(s), target manifests or recipe, run mode, connector/knowledge
   needs, and the exact CLI commands to run, and write that plan to a file in addition to
   showing it in chat. See [references/iac-surfaces.md](references/iac-surfaces.md#plan-output-template).
3. **Approval gate** — stop and wait for the user's explicit approval of the plan. Never
   generate an artifact before this gate is cleared.
4. **Authoring** — once approved, generate capability manifests in this skill's own
   `azuresre.ai/v1` convention under the canonical `azure-sre-agent-config/` artifact layout,
   including its `infra/` subdirectory, which is created only when Surface 1 applies (see
   [references/manifest-templates.md](references/manifest-templates.md#artifact-directory-layout)).
   For Surface 2, write the capability manifests and copy this skill's own pre-built
   `apply.ps1`/`apply.sh` script pair (never regenerated, always the same vetted asset) that
   performs the agent's own REST API sequence — the user runs the script themselves afterward,
   against their own tenant; this skill's own turn never invokes, tests, or otherwise calls that
   script or any live agent endpoint (see
   [references/iac-surfaces.md](references/iac-surfaces.md)). For Surface 1, write the
   fetched agent-resource-provisioning command sequence into the plan as reference content — the
   user applies it via their own existing IaC procedure; this skill never executes it and never
   generates a script for it (see [references/iac-surfaces.md](references/iac-surfaces.md)) —
   never merging the two outputs.

5. **Verification handoff** — after authoring, write `azure-sre-agent-config/VERIFY.md` so the
   user can prove the capability works. It is done when every Definition of Done item from the
   plan has at least one sample prompt or trigger with its expected behaviour, and the plan's
   rollback steps are included. The user runs it; this skill only writes it.

## Two IaC Surfaces, Never Conflated

Every request resolves to one or both of two genuinely different surfaces —
**agent-resource provisioning** and **capability authoring** — never conflated or merged into
one plan section. Read [references/iac-surfaces.md](references/iac-surfaces.md) for what each
means, how to tell which applies, and where the separate `Azure/sre-agent-plugins` connector
marketplace fits.

## Any Use Case, Not a Fixed Catalog

This skill has no fixed list of supported use cases — whatever the user names is the input to
research, never a menu to pick from. See [references/iac-surfaces.md](references/iac-surfaces.md)
for how a named use case is matched to an existing skill or researched fresh.

## Five-Active-Skill Cap

Azure SRE Agent enforces a hard cap of five active skills per agent. This check is unconditional
for every existing-agent path — see the skill-cap branch in
[references/interview-design-tree.md](references/interview-design-tree.md) for when it runs
during the interview as a plan-time heads-up based on the user's own stated count, as distinct
from the copied apply script's own live preflight check (run later, by the user, against their
tenant), which hard-stops by default if the cap is actually exceeded.
