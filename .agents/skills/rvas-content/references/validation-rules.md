# Validation rules

`labs/_framework/labs.py validate` enforces the ERROR rules. The rest are review checks.

## Structure (ERROR)

- Lab folder `labs/<id>/` contains `lab.yaml`, `README.md` and `challenges/`.
- `lab.yaml` has `id` (equal to the folder name), `title`, `summary`, `accent`, `order`.
- Challenge files are `NN-kebab-case.md`, numbered `00..NN` with no gaps or duplicates.
- Each challenge file has frontmatter with `title`, `summary`, `phase`, `group`, and a `## Success Criteria` section.
- All relative links in lab and challenge files resolve.

## Content (WARN)

- Description states outcomes, not step-by-step commands (tutorial creep).
- Purpose comes before Introduction; solution steps are visible at the end of Description (`### Solution steps`); hints and notes sit inside `<details>`.
- At least one success criterion asks the participant to explain something.
- Challenge 00 has a pre-flight check with runnable `bash` commands.
- Learning resources, when present, include at least 3 links (Microsoft Learn preferred).
- No references to Student/ or Coach/ paths, hackathon, or role-specific (coach/student) content.

## Style (INFO)

- Success criteria use checkboxes (`- [ ]`) for agent/product challenges that carry a `Capabilities added` callout.
- Active voice, present tense, one idea per sentence.
