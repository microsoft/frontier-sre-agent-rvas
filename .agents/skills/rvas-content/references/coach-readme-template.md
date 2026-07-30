# Coach README Template

Use this template to create the `Coach/README.md` file for a new rvas.
Replace all `<PLACEHOLDER>` values.

---

```markdown
# Coach Guide — <RVAS Name>

> **COACHES ONLY — Do not share with participants.**

<1–2 sentence overview of what the rvas covers and who it is for.>

---

## Solution Index

| Challenge | Title | Solution File |
|-----------|-------|---------------|
| 00 | Prerequisites | [Solution-00.md](./Solutions/Solution-00.md) |
| 01 | <Title> | [Solution-01.md](./Solutions/Solution-01.md) |
| <N> | <Title> *(optional)* | [Solution-<N>.md](./Solutions/Solution-<N>.md) |

---

## Azure Requirements

| Resource | Requirement |
|----------|-------------|
| **Role** | <e.g., Owner on the subscription> |
| **Region** | <recommended region and reason> |
| **vCPU quota** | <vCPU family and count per team> |
| **Resource providers** | <comma-separated list of Microsoft.* namespaces> |

<Optional: add a bash snippet for pre-registering providers.>

---

## Suggested Agenda

> Times below include **15 min of coach intro/guidance** per challenge on top of the
> hands-on estimate. Total core track (<Ch range>): **~<N> h**.

### <Full N-Day Event>

| Day | Block | Challenges | Est. Time | Focus |
|-----|-------|-----------|-----------|-------|
| Day 1 | AM (<N> h) | Ch 00–<N> | <X + Y + Z> min | <Theme> |
| Day 1 | PM (<N> h) | Ch <N>–<N> | <X + Y> min | <Theme> |

### <Focused 1-Day Event> (if applicable)

<Brief description of which challenges to include and which to skip.>

---

## Coaching Philosophy

1. **Don't give away answers.** When a team is stuck, ask guiding questions:
   - "<Example question using kubectl, az, or the relevant tool>"
   - "<Example question about a common misconception>"

2. **Use the solution files for yourself, not for participants.** Show CLI output
   and error messages — not the commands to fix them — unless a team is truly blocked
   and time is running out.

3. **Let teams choose their path.** <Note any choices students make that have multiple
   valid approaches.>

4. **Timebox each challenge.** Suggested max times (includes 15 min coach intro):
   - Ch 00: <X> min | Ch 01: <X> min | Ch 02: <X> min
   - <Continue for remaining challenges>

5. **Optional challenges are optional.** <Note any quota or resource dependencies for
   optional tracks.>

---

## Per-Challenge Coach Guide

| Ch | Title | Key Concepts to Introduce | Known Blockers & Hints | Est. Time | When to Intervene |
|----|-------|--------------------------|------------------------|-----------|-------------------|
| 00 | Prerequisites | <Key concepts> | <Known blockers> | **<N> min** | After <X> min if <condition> |
| 01 | <Title> | <Key concepts> | <Known blockers> | **<N> min** | After <X> min if <condition> |

> **Detailed solutions** are in the [`Solutions/`](./Solutions/) folder.
> Share only CLI *output* with teams — not the commands.

---

## Cleanup

Remind all teams to delete resources at the end:

```bash
az group delete --name <resource-group> --no-wait --yes
```
```

---

## Notes on the Solution Index table

- Challenges that are **optional** should be marked *(optional)* in the Title column.
- The Solution File column should use relative links: `[Solution-XX.md](./Solutions/Solution-XX.md)`
  or `[Solution-XX.md](./Solution-XX.md)` depending on whether solutions live in a subfolder.
- For multi-track repos, create a separate table per track with links like
  `[dotnet/Solution-00.md](./dotnet/Solution-00.md)`.

## Notes on the Per-Challenge table

Each row should include:
- **Key Concepts** — 3–5 comma-separated concepts the coach introduces (e.g., "Azure CNI Overlay; Workload Identity; availability zones")
- **Known Blockers & Hints** — specific error messages or configuration gotchas (not generic advice)
- **Est. Time** — bold, with "min" suffix, including 15 min coach intro
- **When to Intervene** — a concrete trigger condition (e.g., "After 60 min if no metrics appear")
