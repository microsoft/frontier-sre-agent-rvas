# Validation Rules — RVAS Content

Use this checklist when validating existing content or reviewing your own output.
Report findings with severity: **[ERROR]** (blocks merge), **[WARN]** (should fix), **[INFO]** (style suggestion).

---

## 1. Student Challenge File (`Challenge-XX.md`)

### Required sections (in order)

- [ ] **[ERROR]** Navigation header is present on line 1 (before the `#` title)
- [ ] **[ERROR]** Title follows pattern `# Challenge XX — <Title>` (two em-dashes `—`, not hyphens)
- [ ] **[ERROR]** `## Introduction` section is present and non-empty
- [ ] **[ERROR]** `## Description` section is present and non-empty
- [ ] **[ERROR]** `## Success Criteria` section is present with at least 3 numbered items
- [ ] **[ERROR]** `## Learning Resources` section is present with at least 3 links
- [ ] **[WARN]** `## Tips` section, if present, does not reveal the solution

### Navigation header

- [ ] **[ERROR]** Home link exists: `**[Home](...README.md)**`
- [ ] **[ERROR]** Next link exists for all challenges except the last
- [ ] **[ERROR]** Previous link exists for all challenges except the first (Challenge 00)
- [ ] **[WARN]** Navigation header uses `—` (em-dash), not `-` (hyphen) between segments
- [ ] **[WARN]** For multi-track repos (files under `Student/<track>/`), Home points to `../../README.md`, not `../README.md`

### Content quality

- [ ] **[ERROR]** No step-by-step CLI commands that solve the challenge in `## Description`
  (hint: if a `bash` code block in Description contains `az`, `kubectl`, `helm`, `terraform apply`,
  `flux`, `make deploy`, etc. and it completes a success criterion — it's a tutorial, not a challenge)
- [ ] **[ERROR]** At least one Success Criterion contains `**Explain to your coach**`
- [ ] **[WARN]** Success Criteria use numbered list (not checkboxes `- [ ]`) unless the challenge
  is an agent/product type that uses checkbox style consistently
- [ ] **[WARN]** Description uses bullet points or paragraphs — not a numbered steps list
- [ ] **[INFO]** Tips do not duplicate Learning Resources (links belong in Learning Resources)

### Challenge 00 specific

- [ ] **[ERROR]** `## Pre-flight Validation Checklist` section is present in Challenge 00
- [ ] **[WARN]** Pre-flight checklist contains at least 3 runnable `bash` commands
- [ ] **[WARN]** Pre-flight checklist covers: tool version check, Azure auth check, subscription check

### Optional challenges

- [ ] **[WARN]** Optional challenges have `*(optional)*` in the title heading
- [ ] **[WARN]** Optional challenges have a callout blockquote in Introduction explaining they are optional

---

## 2. Coach Solution File (`Solution-XX.md`)

### Required sections (in order)

- [ ] **[ERROR]** Navigation header is present on line 1
- [ ] **[ERROR]** Title follows pattern `# Coach Guide — Challenge XX: <Title>`
  (note: colon `:` after challenge number, not `—`)
- [ ] **[ERROR]** `## Purpose` section is present and includes expected time
- [ ] **[ERROR]** `## Mini-Lecture` section is present (with time estimate in heading)
- [ ] **[ERROR]** `## Expected Student Output` section is present
- [ ] **[ERROR]** `## Common Issues and Hints` section is present with at least 3 items
- [ ] **[ERROR]** `## Debrief Discussion Guide` section is present with at least 3 questions
- [ ] **[ERROR]** `## Success Criteria Notes` section is present

### Navigation header

- [ ] **[ERROR]** Home link exists: `**[Home](./README.md)**` (note: pipe `|` separator, not `—`)
- [ ] **[ERROR]** Solution uses `|` as separator (not `—` em-dash like Student challenges)
- [ ] **[WARN]** For multi-track repos (files under `Coach/<track>/`), Home points to `../../README.md`

### Content quality

- [ ] **[WARN]** Common Issues use the `**Symptom:** … **Fix:** …` pattern for clarity
- [ ] **[WARN]** Time estimate is present in `## Purpose` (e.g., "Expected time: 30–45 minutes.")
- [ ] **[INFO]** Mini-Lecture time estimate in heading is 5–15 min for most challenges
- [ ] **[WARN]** If a `## Solution` section is present, it contains actual commands (not just descriptions)

---

## 3. Coach README (`Coach/README.md`)

### Required sections

- [ ] **[ERROR]** Contains a `> COACHES ONLY` blockquote warning near the top
- [ ] **[ERROR]** Contains a **Solution Index** table with columns: Challenge | Title | Solution File
- [ ] **[WARN]** Contains an **Azure Requirements** table
- [ ] **[WARN]** Contains a **Suggested Agenda** section with at least one event format
- [ ] **[WARN]** Contains a **Coaching Philosophy** section with numbered principles
- [ ] **[WARN]** Contains a **Per-Challenge Coach Guide** table

### Solution Index table

- [ ] **[ERROR]** Every `Challenge-XX.md` in `Student/` has a corresponding row in the table
- [ ] **[ERROR]** All solution file links in the table point to files that actually exist
- [ ] **[WARN]** Optional challenges are marked `*(optional)*` in the Title column

### Per-Challenge table

- [ ] **[WARN]** Each row has a non-empty "Known Blockers & Hints" column
- [ ] **[WARN]** Each row has an "Est. Time" in bold with "min" suffix
- [ ] **[WARN]** Each row has a "When to Intervene" trigger condition

---

## 4. Main README (`README.md`)

### Required sections

- [ ] **[ERROR]** Challenge list is present — every challenge file is listed
- [ ] **[WARN]** Contains a **Prerequisites** or **Tools to Install** section
- [ ] **[WARN]** Contains a **Repository Contents** section (directory tree or description)
- [ ] **[INFO]** Contains a **Learning Objectives** section (numbered list of skills gained)

---

## 5. File naming and cross-references

- [ ] **[ERROR]** Challenge files are named `Challenge-00.md`, `Challenge-01.md`, … (zero-padded, two digits)
- [ ] **[ERROR]** Solution files are named `Solution-00.md`, `Solution-01.md`, … (zero-padded, two digits)
- [ ] **[ERROR]** No gap in challenge numbering (0, 1, 2, 3 — not 0, 1, 3)
- [ ] **[WARN]** AI/special challenges use a suffix like `Challenge-AI-01.md` only when they are
  a separate optional track (not part of the main sequence)
- [ ] **[ERROR]** Every Previous/Next navigation link points to a file that actually exists
- [ ] **[ERROR]** Home links (`README.md`) resolve to the actual README at the expected path

---

## 6. Common anti-patterns (instant [ERROR])

| Anti-pattern | What to look for | Correct approach |
|---|---|---|
| Tutorial creep | `bash` blocks in `## Description` that contain solution commands | Move commands to Coach Solution `## Solution` section |
| Missing coach question | No "Explain to your coach" in Success Criteria | Add at least one conceptual discussion question |
| Wrong separator in nav header | Student challenge uses `\|` instead of `—` | Use `—` (em-dash) in Student challenges |
| Wrong separator in coach solution | Coach solution uses `—` instead of `\|` | Use `\|` in Coach solutions |
| Missing Home bold | Nav header has `[Home]` but not `**[Home]**` | Bold the Home link with `**` |
| Broken relative links | `../README.md` from `Student/<track>/Challenge-00.md` | Use `../../README.md` for multi-track repos |
| Optional challenge not marked | Optional challenge title missing `*(optional)*` | Add `*(optional)*` to title and Introduction |
| No pre-flight in Ch 00 | Challenge 00 lacks runnable validation commands | Add `## Pre-flight Validation Checklist` |
