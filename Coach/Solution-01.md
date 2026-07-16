[< Previous Solution](./Solution-00.md) | **[Home](./README.md)** | [Next Solution >](./Solution-02.md)

# Coach Guide — Challenge 01: Skills & Knowledge Docs

## Purpose

This challenge shifts students from **consumers** to **authors** of SRE Agent intelligence. The goal is to demystify what the agent "knows" — it's just YAML + Markdown — and give students confidence that they can extend the agent for their own environments.

Expected time: **20–25 minutes**.

## Mini-Lecture (5 min before challenge)

Cover:
- The two-layer model: skill YAML (metadata + tool grants + pointer) + knowledge doc (actual runbook)
- Why tool grants are separate from the runbook: the agent can only call tools you explicitly allow — separation of concern between "what the agent knows" and "what the agent can do"
- The 5-skill limit: production agents have bounded capability by design; this is intentional, not a bug
- How the agent selects a skill: it reads the `description` field of each skill and picks the best match for the current situation — quality of description = quality of routing

## Expected Student Output

- A YAML file with valid `kind: Skill` structure, meaningful `description`, correct `content_file` path, and appropriate tool grants
- A Markdown knowledge doc with: trigger condition, investigation procedure (CLI commands or KQL), interpretation guide, recommended actions
- Both applied via `sre-agent-config.sh` and visible in the portal

## Common Issues and Hints

### `content_file` path error
- The path is relative to the YAML file's location. If both files are in `skills/`, use `./my-skill.md`
- If the file doesn't exist at that exact relative path, apply will fail with a file-not-found error

### Skill doesn't appear in portal after apply
- Check the apply output for HTTP errors — a 400 usually means schema validation failed (missing required field)
- Run `./sre-agent-config.sh verify --target skills` to compare applied state vs. desired state
- Common omission: missing `spec.safety` block

### Student hits the 5-skill limit
- Show them how to use `./sre-agent-config.sh delete --target skills --name <existing-skill>` to remove one
- Or: rename their file to `example-<name>.yaml` to exclude it from the apply (explain the `example-` convention)

### Knowledge doc quality is poor
- The agent will produce poor results even if the YAML is valid
- Coach prompt: "Would you trust a new hire to follow this runbook without asking any questions?" — if no, the runbook needs more specificity
- Good runbooks name exact CLI commands, exact KQL table names, and specific threshold values

## Debrief Discussion Guide (5 min)

1. **What makes a good skill description?** — It should be a single sentence that tells the agent exactly when to invoke it. "Investigate connectivity issues" is too broad. "Check if a VM can reach a target IP using Network Watcher IP Flow Verify and Next Hop" is actionable.
2. **Why separate the YAML from the Markdown?** — The YAML can be version-controlled and validated; the Markdown can be authored by domain experts who don't know YAML. Different people can own different parts.
3. **What would you put in YOUR team's first skill?** — Surfaces real-world runbooks students already have.

## Success Criteria Notes

- Accept any valid skill + knowledge doc, regardless of the domain chosen — the learning is in the structure, not the content
- If the student's skill doesn't apply cleanly, walk through the error with them — debugging the config tool is itself a learning objective
- Portal visibility is the primary acceptance signal — if it shows up with the right name and description, the round-trip worked
