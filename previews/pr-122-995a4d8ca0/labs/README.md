# Labs

Each folder here is one lab. The Scenario page and the Labs menu are generated from this folder, so adding a lab needs no web change.

| Lab | Description |
|---|---|
| [Azure Operations](01-azure-operations/README.md) | Configure an Azure SRE Agent, investigate incidents and remediate autonomously. |
| [SQL Server DBA](02-sql-server-dba/README.md) | Read-only SQL Server investigations through a hardened MCP server. |

## Layout

```
labs/<lab-id>/
  lab.yaml                    id (= folder), title, summary, accent, order, prefix
  README.md                   description, challenge table, requirements, facilitation notes
  challenges/NN-slug.md     frontmatter + instructions; purpose and solution steps visible; hints and notes in <details>
```

Challenge frontmatter: `title`, `summary`, `phase`, `group` (required), `tags`, `highlight`.

## Add a lab or challenge

1. Name the folder `NN-slug` (for example `03-my-lab`), where `NN` is the lab's order and the slug is kebab-case. Copy `_template/` to `labs/<lab-id>/` and edit `lab.yaml`, or add `challenges/NN-slug.md` to an existing lab. Numbers run `00..NN` with no gaps.
2. Put purpose first and the solution steps visible at the end of Description (`### Solution steps`); keep background, expected output, common issues and debrief inside `<details>` blocks.
3. Run `labs/_framework/labs.py validate`.

## Notes

Each lab owns its deployment code under `labs/<lab-id>/resources/` and its `Makefile`; challenges link to it there.
