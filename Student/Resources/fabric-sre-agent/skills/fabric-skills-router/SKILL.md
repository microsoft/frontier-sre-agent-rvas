---
name: fabric-skills-router
description: REQUIRED for every Microsoft Fabric request (lakehouse, warehouse, Spark, KQL, Eventstream, semantic model, OneLake, Fabric workspace or item). Load before answering or calling any Fabric tool.
---

## Source of truth

The official Fabric skills are in the repository connected under
**Builder > Code Access**:

- Repo: `https://github.com/microsoft/skills-for-fabric`
- Branch: `main`
- Skills root: `plugins/fabric-skills/skills/`
- Shared files: `plugins/fabric-skills/common/`

Always read these files from the Code Access repository with the
code-read / file-read tools. Do NOT answer from memory, and do NOT
fetch them from the web.

## Steps

1. Choose the skill folder under `plugins/fabric-skills/skills/`:
   - Spark / notebooks → `spark-cli`
   - Warehouse / SQL endpoint → `sqldw-cli`
   - SQL database → `sqldb-cli`
   - Eventhouse / KQL → `eventhouse-cli`
   - Eventstream → `eventstream-cli`
   - Activator → `activator-cli`
   - Dataflows → `dataflows-cli`
   - Semantic models → `semantic-model-authoring`
   - Deployment pipelines → `deployment-pipelines-authoring-cli`
   - Git integration → `git-integration-operations-cli`
   - Variable libraries → `variable-library-cli`
   - OneLake catalog / governance → `onelake-catalog-govern-cli`
   - Fabric IQ / ontology → `fabriciq`, `fabriciq-ontology-cli`
   - Migrations → `databricks-migration`, `synapse-migration`,
     `hdinsight-migration`, `pipeline-migration`
   - Architecture / cost → `e2e-medallion-architecture`,
     `e2e-fabric-cost-estimation`
   - Not listed → list `plugins/fabric-skills/skills/` in the repo and pick one
2. Read `plugins/fabric-skills/skills/<folder>/SKILL.md` from the repo, in full.
3. Read every file it marks **Mandatory**. Resolve relative links from the
   skill folder, e.g. `../../common/COMMON-CLI.md` →
   `plugins/fabric-skills/common/COMMON-CLI.md`.
4. State which skill file(s) you read, then follow them exactly.
5. Execute using the Fabric MCP connector tools. Never invent endpoints.

## Workshop safety and execution boundary

This agent is read-only. Skills describing authoring do not authorize creating,
updating, running, or deleting Fabric items or KQL management commands.
If a required file cannot be read, report the Code Access/sync error and stop;
do not substitute a web copy or remembered instructions.

Use MCP tools for operations they actually expose. Where no connector tool
exists, only the explicitly configured, read-only REST/CLI paths in the active
backend instructions are allowed (for example Eventhouse KQL queries using the
agent UAMI). Read the selected skill and mandatory references first; never
invent a tool or endpoint, silently use a human identity, or bypass a missing
permission. The retail-price tool remains the sole source of rates.
