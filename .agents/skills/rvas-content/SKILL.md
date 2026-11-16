---
name: rvas-content
description: >
  Creates, formats, and validates lab content for RVAS events in the Microsoft Frontier RVAS
  format: labs under labs/<lab-id>/ with a lab README and one markdown file per challenge. Use this skill
  whenever someone asks to write, review, or validate a challenge, a lab README, or a whole lab,
  to add a new lab or track, or to check whether content follows the RVAS conventions.
---

# RVAS Content Skill

Content lives in `labs/`. There are no Student, Coach or hackathon folders: every instruction,
hint and solution is in the lab README or in the challenge it belongs to. The web page and the
Labs menu are generated from this folder (`labs/_framework/labs.py index`).

## Layout

```
labs/<lab-id>/
  lab.yaml                      id (= folder name), title, summary, accent, order, prefix
  README.md                     description, challenge table, requirements, facilitation notes
  challenges/NN-kebab-slug.md
```

Start from `references/lab-yaml-template.yaml`, `references/lab-readme-template.md` and
`references/challenge-template.md`. Read `references/validation-rules.md` before writing.

## Challenge file

Frontmatter (required): `title`, `summary`, `phase`, `group`. Optional: `tags`, `highlight`.

Body order: `# Challenge NN — Title`, optional capability callout, `## Introduction`,
`## Purpose`, `## Introduction`, `## Description`, `## Success Criteria`, optional
`## Learning Resources` and `## Tips`, then `## Hints and notes`.

- Description says what to achieve, not click-by-click how. Success criteria describe the outcome.
- At least one criterion is "Explain …" so the reader checks their own understanding.
- Purpose and the solution steps are visible; put the solution steps at the end of `## Description` under `### Solution steps`. Expected Output, Common Issues and Hints and Debrief go in `<details>` blocks under `## Hints and notes`.
- Challenge 00 covers prerequisites and a runnable pre-flight check.
- Link to other challenges with relative paths (`NN-slug.md`); never to Student/ or Coach/.

## Lab README

Description, challenge table, requirements (link the shared root README instead of copying),
and facilitation notes: agenda, principles, per-challenge blockers and when to intervene, restore steps.

## Workflow

1. Create or edit files from the templates.
2. Run `labs/_framework/labs.py validate` (structure, frontmatter, numbering, links) and fix every error.
3. Run `make build-web` when the page or data changed.

## Validating existing content

Report two parts: what passes, then numbered issues tagged [ERROR], [WARN] or [INFO] covering
missing frontmatter or sections, tutorial creep in the Description, missing "Explain" criterion, broken links, and numbering gaps.
