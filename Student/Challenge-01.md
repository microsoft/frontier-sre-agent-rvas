[< Previous Challenge](./Challenge-00.md) — **[Home](../README.md)** — [Next Challenge >](./Challenge-02.md)

# Challenge 01 — Skills & Knowledge Docs

## Introduction

Before you watch the SRE Agent respond to incidents, you need to understand how it *knows what to do*. The Azure SRE Agent's intelligence comes from two building blocks that work together:

- **Skills** — structured YAML files that give an agent a named, focused procedure and a constrained set of tools to execute it
- **Knowledge documents** — Markdown files that contain the actual runbook, KQL catalog, or reference material a skill uses

In this challenge you will write both from scratch, apply them to the live agent, and verify they appear in the portal — just as the lab's 8 pre-built skills were applied during Challenge 00.

## Description

### Step 1 — Understand the skill YAML format

Open an existing skill as a reference:

```bash
cat Coach/Solutions/azure-sre-agent-config/skills/connectivity-diagnostics.yaml
```

Key fields:
```yaml
api_version: azuresre.ai/v1
kind: Skill
metadata:
  name: <unique-name>          # lowercase, hyphens only
spec:
  description: <one sentence>  # shown in portal; used for routing
  content_file: ./<name>.md    # relative path to the knowledge doc
  tools:
    - RunAzCliReadCommands      # tools this skill may use
    - QueryLogAnalyticsByWorkspaceId
  safety:
    default_mode: read_only
    requires_approval_for_actions: true
```

> **Tool grants are additive.** A skill only gets the tools you list. Start with `read_only` until you understand the blast radius.

### Step 2 — Write a knowledge document

Create a file at `Coach/Solutions/azure-sre-agent-config/skills/<your-skill-name>.md`.

Write a **1-page investigation runbook** for a simple, real scenario you might encounter — for example:
- "Check if a VM's OS disk is nearing full capacity"
- "Verify that all diagnostic settings are sending logs to the Log Analytics workspace"
- "List any NSG rules that allow inbound from Internet on non-standard ports"

The runbook should include:
1. When to use this skill (trigger condition)
2. The Azure CLI commands or KQL queries to run
3. How to interpret the results
4. Recommended actions

### Step 3 — Write the skill YAML

Create `Coach/Solutions/azure-sre-agent-config/skills/<your-skill-name>.yaml` pointing at the knowledge doc you just wrote.

Choose appropriate tools from:
- `RunAzCliReadCommands` — read-only `az` commands
- `QueryLogAnalyticsByWorkspaceId` — KQL against Log Analytics
- `GetAzCliHelp` — discover CLI syntax
- `SearchMemory` — search the agent's knowledge base

Keep `safety.default_mode: read_only`.

### Step 4 — Apply the skill

```bash
cd Coach/Solutions/infra
source scripts/.sre-agent-apply-all.sh --section skills
```

Or apply just your new skill:
```bash
cd Coach/Solutions
./infra/scripts/sre-agent-config.sh apply --target skills --name <your-skill-name>
```

### Step 5 — Verify in portal

1. Open the SRE Agent portal URL (from `terraform output agent_portal_url`)
2. Navigate to **Skills**
3. Confirm your new skill appears with the correct name and description
4. Optionally: open the portal chat and ask the agent to "use the `<your-skill-name>` skill to investigate [your scenario]"

## Success Criteria

- [ ] A valid `<skill-name>.yaml` + `<skill-name>.md` exist under `Coach/Solutions/azure-sre-agent-config/skills/`
- [ ] The skill appears in the portal under **Skills** with the correct name and description
- [ ] You can explain the difference between a skill's **YAML** (metadata + tool grants) and its **knowledge doc** (actual runbook content)
- [ ] You can explain what `safety.default_mode: read_only` prevents the agent from doing

## Learning Resources

- [Azure SRE Agent — Skills documentation](https://learn.microsoft.com/en-us/azure/sre-agent/skills)
- [Azure SRE Agent — Tool grants reference](https://learn.microsoft.com/en-us/azure/sre-agent/tools)
- Existing skills in `Coach/Solutions/azure-sre-agent-config/skills/` — use as reference

## Tips

- Keep your skill **focused**: one procedure, one failure domain. The agent uses the `description` field to decide which skill to invoke.
- The `content_file` path is relative to the YAML file's location — both files must be in the same directory.
- If `apply` returns an error about the skill already existing, use `--force` or change the `metadata.name`.
- The lab enforces a **5 active skills** limit — if you hit it, delete one of the existing ones first (or check the `example-` prefix convention to disable without deleting).
