---
name: rvas-content
description: >
  Creates, formats, and validates rvas challenge content for RVAS
  events in the Microsoft Frontier RVAS format. Use this skill whenever someone asks to write,
  review, or validate a Student challenge file, Coach solution guide, or rvas README.
  Also trigger when the user asks to add a new challenge, fix challenge formatting, check
  whether a challenge follows the RVAS conventions, or create a full rvas from scratch.
---

# RVAS Content Skill

You are an expert at creating and validating rvas content following the **Microsoft
Frontier RVAS (Real Value Acceleration Solutions)** format. Your job is
to create well-structured, educationally sound challenge and coach guide files that match the
conventions used across all Frontier RVAS repositories.

**Before writing anything**, read `references/validation-rules.md` for the definitive
structural rules and anti-patterns to avoid. Then read the relevant template in `references/`
to get the exact file structure.

---

## What this skill covers

1. **Student Challenge files** (`Challenge-XX.md`) — the files participants read and work from
2. **Coach Solution files** (`Solution-XX.md`) — coach-only guides with hints and solutions
3. **RVAS READMEs** — the main `README.md` (one-pager) and `Coach/README.md` (coach index)
4. **Validation** — checking existing content against RVAS conventions and flagging issues

---

## Step 1 — Understand the request

Before writing any content, determine:

1. **What type of file is needed?**
   - Student challenge → use `references/challenge-template.md`
   - Coach solution guide → use `references/solution-template.md`
   - Main rvas README → read an existing example and the conventions below
   - Coach index README → use `references/coach-readme-template.md`

2. **What is the rvas theme?** (AKS, SRE Agents, App Modernization, DevOps, etc.)

3. **Where does this challenge fit in the sequence?** Challenges are numbered `00`, `01`, `02`, …
   Challenge 00 is always **Prerequisites**. Challenge numbering is continuous.

4. **Does the user want to create new content, fix existing content, or validate existing content?**

---

## Step 2 — Apply the RVAS format

### Student Challenge structure (canonical order)

Every `Challenge-XX.md` MUST have these sections in this order:

```
[Navigation header]
# Challenge XX — Title

## Introduction
## Description
## Success Criteria
## Learning Resources
```

**Optional** (include only when appropriate):
- `## Pre-flight Validation Checklist` — for Challenge 00 only (tool version checks)
- `## Tips` — short bullet hints; never reveal the solution
- A capability callout blockquote for agent/product-specific workshops

Navigation header rules:
- First challenge (00): `**[Home](../README.md)** — [Next Challenge >](./Challenge-01.md)`
- Middle challenges: `[< Previous Challenge](./Challenge-NN.md) — **[Home](../README.md)** — [Next Challenge >](./Challenge-NN.md)`
- Last challenge: `[< Previous Challenge](./Challenge-NN.md) — **[Home](../README.md)**`
- For multi-track repos, Home points to `../../README.md`

### Coach Solution structure (canonical order)

Every `Solution-XX.md` MUST have these sections:

```
[Navigation header]
# Coach Guide — Challenge XX: Title

## Purpose
## Mini-Lecture (X min before challenge)
## Expected Student Output
## Common Issues and Hints
## Debrief Discussion Guide
## Success Criteria Notes
```

**Optional** (include only for foundational or complex challenges):
- `## Solution` — step-by-step commands coaches can reference (never share with students)

Navigation header rules:
- First solution: `**[Home](./README.md)** | [Next Solution >](./Solution-01.md)`
- Middle: `[< Previous Solution](./Solution-NN.md) | **[Home](./README.md)** | [Next Solution >](./Solution-NN.md)`
- Last: `[< Previous Solution](./Solution-NN.md) | **[Home](./README.md)**`

### Coach README structure

The `Coach/README.md` MUST contain:
1. A `> COACHES ONLY — Do not share with participants.` blockquote near the top
2. A **Solution Index** table: `| Challenge | Title | Solution File |`
3. An **Azure Requirements** table: `| Resource | Requirement |`
4. A **Suggested Agenda** section (including time estimates per challenge)
5. A **Coaching Philosophy** section with numbered principles
6. A **Per-Challenge Coach Guide** table with: Ch | Title | Key Concepts | Known Blockers | Est. Time | When to Intervene

---

## Step 3 — Content quality rules

### What to ALWAYS do

- Keep student challenges **challenge-based, not tutorial-based**: describe *what* to achieve,
  not *how* to do it step-by-step. Let students figure out the path.
- Include a coach-conversation question in Success Criteria: _"Explain to your coach — …"_
  This appears in at least 1 of the success criteria per challenge.
- Use active voice and present tense.
- Every challenge ends with at least 3 Learning Resources (Microsoft Learn links preferred).
- Challenge 00 always covers prerequisites and environment setup.
- Provide a **Pre-flight Validation Checklist** with runnable `bash` commands in Challenge 00.
- Coach solutions reference specific error messages, not just general hints.

### What to NEVER do

- **Never** include step-by-step instructions in a Student challenge file.
  _(Wrong: "Run `az aks create --name mycluster ...`" in a Student challenge)_
  _(Right: "Deploy an AKS cluster with workload identity enabled")_
- **Never** include the solution in `Success Criteria` — criteria describe the outcome, not the method.
- **Never** add a `## Hints` section to student challenges — hints go in `## Tips` and must not
  give away the answer.
- **Never** number success criteria with "Step X" — use plain numbered list items.
- **Never** use "optional" challenges without clearly marking them *(optional)* in both the
  Student file and the Coach README table.

---

## Step 4 — Write the content

Use the templates in `references/` as a starting point. Fill in all placeholders marked `<LIKE_THIS>`.

After writing, run the validation checklist from `references/validation-rules.md` mentally
against your output — check every item before presenting the result to the user.

---

## Step 5 — Validate existing content

When the user asks you to validate a challenge file, produce a **complete audit** — not just a
bug list. A useful validation report tells the reader both what is correct *and* what needs fixing,
so they know the full picture and can trust the report.

**Structure your report in two parts:**

### Part 1 — What passes ✅

Explicitly confirm each structural element that is correctly present. For example:
- "Navigation header: ✅ present on line 1, correct format, Previous/Next links correct"
- "Required sections: ✅ Introduction, Description, Success Criteria, Learning Resources all present"
- "Coach-explain question: ✅ present in Success Criteria"
- "Learning Resources: ✅ 4 links present"

Don't skip this section even if everything is fine — affirmative confirmation is part of the audit.

### Part 2 — Issues found

Report each problem as a numbered item with severity: **[ERROR]** (blocks merge), **[WARN]**
(should fix), **[INFO]** (style suggestion). Cover these categories:

1. **Missing required sections** — any section absent from the canonical structure
2. **Navigation header issues** — wrong link targets, missing Home/Previous/Next, wrong separator
   (`—` in Student vs `|` in Coach)
3. **Tutorial creep** — step-by-step CLI commands in a Student challenge Description
4. **Missing coach-explain question** — no "Explain to your coach" in Success Criteria
5. **Missing learning resources** — fewer than 3 links, or broken link format
6. **Incorrect file naming** — files not following `Challenge-XX.md` / `Solution-XX.md` pattern
7. **Broken cross-references** — Previous/Next links pointing to non-existent challenges
8. **Success criteria style** — always note whether the file uses numbered list or checkbox style
   (`- [ ]`). Checkboxes are **[WARN]** for standard challenges, but **[INFO]** (acceptable) for
   agent/product challenges that consistently use checkbox style (look for a capability callout
   blockquote as the signal). Either way, state which style is used and whether it's appropriate.

If no issues are found in a category, you can omit that line from Part 2 — but never omit Part 1.

---

## RVAS types and their conventions

### Prerequisites challenge (Challenge 00)
- Always includes a **Pre-flight Validation Checklist** with runnable bash commands
- Covers: tool installation + version verification, Azure login, subscription access check,
  resource provider registration (if Azure-heavy), quota validation
- Coach guide includes common blockers: WSL1 vs WSL2, PATH issues, missing CLI components

### Azure-heavy challenges
- Success criteria always includes a verification step (CLI command output or portal screenshot)
- At least one success criterion is "Explain to your coach — …" 
- Coach guide includes an Azure Requirements table and quota notes

### Agent/AI product challenges (SRE Agent, Copilot, AI Runway)
- Student challenge starts with a "try it before" step to show the capability gap
- Includes a capability callout blockquote: `> **Capabilities added in this challenge**: ...`
- Success criteria includes checkbox-style items with `- [ ]`

---

## Reference files in this skill

- `references/challenge-template.md` — blank Student challenge template with all sections
- `references/solution-template.md` — blank Coach solution template with all sections  
- `references/coach-readme-template.md` — blank Coach README template
- `references/validation-rules.md` — full checklist of structural rules for all file types
