---
name: fabric-skills-router
description: Selects and reads the current Microsoft Fabric operational skill before the agent investigates or recommends work on a Fabric item.
---

# Fabric skills router

Before acting on any Microsoft Fabric question, read the relevant `SKILL.md`
from the `microsoft/skills-for-fabric` repository connected under Code Access.
Use the live repository content; do not rely on remembered instructions or
summaries. State the skill file or files consulted in the response.

## Route by task

| Task | Skill to read |
|---|---|
| Fabric Lakehouse, Spark, notebook runs, Spark monitoring, or notebook optimization | `spark-cli/SKILL.md` |
| Eventhouse, KQL databases, or KQL queries over capacity operation events | `eventhouse-cli/SKILL.md` |
| Warehouse or SQL analytics endpoint queries, Query Insights, or SQL endpoint health | `sqldw-cli/SKILL.md` |
| Finding an item when its workspace is unknown | `search-consumption-cli/SKILL.md` |
| Capacity sizing or comparing Fabric billing options | `e2e-fabric-cost-estimation/SKILL.md` |
| Fabric item, workspace, or job-instance discovery not covered above | `fabric-mcp/SKILL.md` |

If a named skill is not present in the repository, search its current catalog
and choose the closest supported skill. Read its shared CLI/core references
when it directs you to do so. Do not invent a command or API shape to fill a
gap.

## Safety boundary

This agent is for read-only investigation and recommendations. Do not create,
update, run, or delete Fabric items; do not run KQL management commands; and do
not make a change merely because a skill describes how. Report the evidence,
limitations, and an approval-ready recommendation instead.
