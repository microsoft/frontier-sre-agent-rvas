[< Previous Challenge](./Challenge-05.md) — **[Home](../../README.md)** — [Next Challenge >](./Challenge-07.md)

# Challenge 06 — Validate Live Skills and Agent Instructions

> **Capabilities added in this challenge**: Code Access Freshness · Mandatory Skill Reads · Instruction Regression Tests

## Introduction

A connected skills repository and a saved instruction file do not prove that
the agent uses either correctly. This challenge deepens the initial setup from
Challenge 02 by testing freshness, file-read evidence, backend grounding, and
failure behavior before the Spark investigation.

## Description

First ask which skill and source the agent would use for a bounded Fabric
question, and inspect whether it actually reads the required files.
Use the [Code Access/router procedure](../Resources/fabric-sre-agent/README.md#connect-the-latest-fabric-skills-and-install-the-router)
and [instruction procedure](../Resources/fabric-sre-agent/README.md#apply-the-backend-specific-agent-instructions)
to audit and correct the existing configuration.

- Confirm `https://github.com/microsoft/skills-for-fabric` is connected on `main`,
  refresh/sync it, and record the sync time and revision where available.
- Validate the installed `fabric-skills-router` against the supplied router,
  including its required trigger and full `plugins/fabric-skills/skills/` paths.
- Use a notebook diagnostic question and a backend-specific query question to
  prove the agent reads the full selected `SKILL.md`, follows every Mandatory
  reference under `plugins/fabric-skills/common/` or the skill folder, and names
  the files before executing the supported read-only tools.
- Audit the complete active FUAM **or** Capacity Events custom instructions,
  including section 3.0 identifiers, pricing source, CU units, explicit failure
  reporting, and read-only boundaries. Correct missing or truncated sections;
  never combine both global instruction sets.
- Test a nonexistent item and a harmless change request. Verify explicit
  uncertainty/refusal, no invented endpoint, no write call, and no fallback
  to another identity, consumption source, web copy, or remembered skill.
- Demonstrate the missing-file failure path through a coach-approved test
  fixture or reviewed trace; do not disconnect shared sources or corrupt
  the upstream repository to manufacture an error.

## Success Criteria

- [ ] Code Access points to `main`, has a recorded successful refresh, and exposes the full skills and common-reference directories.
- [ ] Tool traces show the required router and full skill/Mandatory-file reads before Fabric execution; naming a file without reading it does not pass.
- [ ] Notebook and backend queries select appropriate skills (`spark-cli`, `sqldw-cli`, or `eventhouse-cli`) and use only supported read-only execution paths.
- [ ] Exactly one complete backend instruction set is active with the coach's real identifiers and no unresolved section 3.0 placeholders.
- [ ] The instruction audit covers model/data approval, shared-source scope, TOTAL reconciliation, correct period-share denominator or unavailable label, and explicit query/price failure reporting.
- [ ] Missing-file, nonexistent-item, and write-request checks fail explicitly and safely without web/memory or identity fallback.
- [ ] **Explain to your coach** — why does Code Access synchronization plus verified file reads provide fresher guidance than installing static skill copies or trusting model memory?

## Learning Resources

- [Fabric skills repository](https://github.com/microsoft/skills-for-fabric)
- [Workshop router SKILL.md](../Resources/fabric-sre-agent/skills/fabric-skills-router/SKILL.md)
- [Shared skills and instruction setup](../Resources/fabric-sre-agent/README.md#connect-the-latest-fabric-skills-and-install-the-router)
- [FUAM agent instructions](../Resources/fabric-sre-agent/fuam/agent-instructions.md)
- [Capacity Events agent instructions](../Resources/fabric-sre-agent/capacity-events/agent-instructions.md)
- [SRE Agent skills](https://learn.microsoft.com/azure/sre-agent/skills)

## Tips

- A recent Connection badge is not a sync timestamp; latest means the latest successfully synchronized `main`.
- Resolve `../../common/COMMON-CLI.md` from the selected skill folder, not the repository root.
- An upstream authoring skill cannot override the workshop's read-only contract.
