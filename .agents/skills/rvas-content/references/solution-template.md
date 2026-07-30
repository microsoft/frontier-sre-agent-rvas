# Coach Solution Template

Use this template to create `Coach/Solution-XX.md` (or `Coach/<track>/Solution-XX.md`) files.
Replace all `<PLACEHOLDER>` values.

---

```markdown
**[Home](./README.md)** | [Next Solution >](./Solution-<NEXT_NUM>.md)

# Coach Guide — Challenge <NUM>: <TITLE>

## Purpose

- <One-line statement of what this challenge teaches the student.>
- <What operational or conceptual skill they practice.>
- Expected time: <X–Y minutes>.

## Mini-Lecture (<X> min before challenge)

<3–5 bullet points of talking points to deliver before students start the challenge.
Cover the "why", introduce key concepts, and draw any important dependency chains.>

- <Talking point 1>
- <Talking point 2>
- <Talking point 3>

## Expected Student Output

<Bullet list of what a successfully completed challenge looks like.
These are the observable artefacts/states the coach checks.>

- <Observable outcome 1>
- <Observable outcome 2>
- <Observable outcome 3>

## Common Issues and Hints

- **Symptom:** <What the student sees / reports.> **Fix:** <How to resolve it.>
- **Symptom:** <What the student sees / reports.> **Fix:** <How to resolve it.>
- **Symptom:** <What the student sees / reports.> **Fix:** <How to resolve it.>

## Debrief Discussion Guide

<3–4 questions to ask the team after they complete the challenge.
Format: question → expected answer or concept to draw out.>

- <Question about the "why" behind a decision they made?>
- <Question connecting this challenge to the next one?>
- <Question about a trade-off or alternative approach?>

## Success Criteria Notes

<Guidance on how strictly to apply each success criterion.
Note any criteria where flexibility is acceptable.>

- Be strict on: <criteria that must pass exactly>
- Be flexible on: <criteria where partial completion is acceptable>
- Accept alternative approaches: <list any valid alternatives the template doesn't mention>
```

---

## Optional Solution section (for foundational or complex challenges)

Add this section at the end when a reference solution is needed for coaches to consult:

```markdown
## Solution

### <Step name>

```bash
# <Description of what this block does>
<command>
<command>
```

### <Step name>

```bash
<command>
```
```

---

## Navigation header variants

**Solution 00 (first):**
```
**[Home](./README.md)** | [Next Solution >](./Solution-01.md)
```

**Middle solution (e.g., 03):**
```
[< Previous Solution](./Solution-02.md) | **[Home](./README.md)** | [Next Solution >](./Solution-04.md)
```

**Last solution:**
```
[< Previous Solution](./Solution-<PREV_NUM>.md) | **[Home](./README.md)**
```

**Multi-track repo (inside `Coach/dotnet/`, `Coach/java/`, etc.):**
```
**[Home](../../README.md)** | [Next Solution >](./Solution-01.md)
```

---

## Time estimate conventions

| Challenge type | Typical range |
|----------------|---------------|
| Prerequisites (Ch 00) | 30–45 min |
| Infrastructure provisioning | 60–90 min |
| Configuration / integration | 45–75 min |
| Advanced / multi-service | 90–120 min |
| Optional / stretch | 60–90 min |

Coach time estimates include ~15 min for the mini-lecture + intro.
