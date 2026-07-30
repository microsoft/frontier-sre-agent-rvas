# Student Challenge Template

Use this template to create `Student/Challenge-XX.md` files. Replace all `<PLACEHOLDER>` values.

---

```markdown
**[Home](../README.md)** — [Next Challenge >](./Challenge-<NEXT_NUM>.md)

# Challenge <NUM> — <TITLE>

## Introduction

<2–4 sentences that explain:
- Why this challenge matters
- What capability, concept, or problem it addresses
- What the student will accomplish (outcome, not steps)>

## Description

<What the student needs to achieve. Write goals, not instructions.
Use bullet points for distinct sub-tasks.
Do NOT include specific CLI commands that solve the challenge.>

- <Goal 1>
- <Goal 2>
- <Goal 3>

> **Note:** <Any important constraint or clarification that prevents confusion.>

## Success Criteria

1. <Verifiable outcome — what the coach can observe or the student can demonstrate.>
2. <Verifiable outcome.>
3. <Verifiable outcome.>
4. **Explain to your coach** — <open-ended conceptual question about what was learned.>

## Learning Resources

- [<Link title>](<URL>)
- [<Link title>](<URL>)
- [<Link title>](<URL>)

## Tips

- <Hint that guides without revealing the answer.>
- <Hint about a common pitfall.>
```

---

## Navigation header variants

**Challenge 00 (first):**
```
**[Home](../README.md)** — [Next Challenge >](./Challenge-01.md)
```

**Middle challenge (e.g., 03):**
```
[< Previous Challenge](./Challenge-02.md) — **[Home](../README.md)** — [Next Challenge >](./Challenge-04.md)
```

**Last challenge:**
```
[< Previous Challenge](./Challenge-<PREV_NUM>.md) — **[Home](../README.md)**
```

**Multi-track repo (inside `Student/dotnet/`, `Student/java/`, etc.):**
```
[< Previous Challenge](./Challenge-<PREV_NUM>.md) — **[Home](../../README.md)** — [Next Challenge >](./Challenge-<NEXT_NUM>.md)
```

---

## Pre-flight Validation Checklist (Challenge 00 only)

Add this section between `## Description` and `## Success Criteria` for Challenge 00:

```markdown
## Pre-flight Validation Checklist

Run these commands before starting the next challenge. Every check must pass:

```bash
# 1. <Tool> version check
<tool> --version

# 2. Azure CLI authenticated
az account show --query "{name:name,id:id,state:state}" -o table

# 3. <Other check>
<command>
```

---

## Agent capability callout (for agent/AI-product challenges only)

Add immediately after the `# Challenge XX — Title` heading:

```markdown
> **Capabilities added in this challenge**: <Capability Name> · <Capability Name>
```

---

## Optional challenge marking

When a challenge is optional, add to the title:

```markdown
# Challenge XX — <Title> *(optional)*
```

And add to the Introduction:

```markdown
> **This challenge is optional.** Complete it if your team finishes the core track ahead of schedule.
```
