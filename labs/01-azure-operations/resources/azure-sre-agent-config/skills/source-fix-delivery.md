---
name: source-fix-delivery
description: Use when an incident is traced to a source-code defect and a fix must be delivered. Proves the causal mechanism from telemetry and code, derives the smallest change that removes the mechanism rather than masking the symptom, adds a regression test that fails before and passes after, and delivers issue plus pull request without merging.
---

# source-fix-delivery

Use this skill when an incident has been traced to a source-code defect and a fix must be
delivered as a pull request. It defines the engineering standard the fix must meet and the
delivery workflow that produces reviewable artifacts.

Do not use it for configuration drift, infrastructure faults, or capacity problems: those are
resolved by the owning domain specialist, not by a code change.

---

## 1. Prove the mechanism before proposing anything

Never infer the defective file, symbol, or patch from an alert name, a label, or a runbook title.
The repository is the source of discovery, not a pre-solved exercise.

1. Search memory for similar past incidents and for the incident report template.
2. Collect telemetry evidence: exception type and message, stack frames, request path, timing
   relative to deployments, and the resource metric that breached.
3. Form at least two competing hypotheses that could produce that evidence.
4. Read the connected repository under `codeRefs/` (or use `get_file_contents` and `search_code`)
   and trace the failing request through the actual code path.
5. Discard every hypothesis the code contradicts. State explicitly which one survived and which
   line or lines implement the failing mechanism.

Stop and report without a pull request if no hypothesis survives. An unproven fix is worse than
no fix.

---

## 2. The engineering standard the fix must meet

A change is only a fix when it removes the mechanism that produces the failure. Mitigating the
consequence while leaving the mechanism in place is a workaround and must be labelled as such.

| Which question must the change answer? | What counts as acceptable |
| --- | --- |
| Does it remove the cause, or only limit its effect? | The causal construct is deleted or replaced. A cap, a clamp, a retry, or a larger limit around a construct that should not exist is a workaround, not a fix. |
| Does it introduce a magic number? | No arbitrary threshold is added. If a bound is genuinely required, it is derived from a documented requirement and named as a constant with the derivation in a comment. |
| Is unrelated code preserved? | The diff touches only what the mechanism requires. No opportunistic refactoring, no formatting churn. |
| Is the behavioral contract preserved? | Public signatures, response shapes, and status codes are unchanged unless the incident proves they are the defect. |
| Is the change reversible? | It can be reverted by reverting one commit, with no data migration and no manual step. |
| Does it respect the platform limits it runs under? | Memory, request timeout, and concurrency of the hosting service are checked against the new behavior. |

**Worked example of the distinction, drawn from this project's own cart incident.**
The defect is a static `List<byte[]>` that retains a freshly allocated `new byte[10 * 1024 * 1024]`
on every write, so a few hundred requests exhaust a one-gibibyte container.

- Capping that list at fifty megabytes is a **workaround**: the pointless ten-megabyte allocation
  still happens on every request and the static retention still exists.
- Removing the allocation and the static retention is the **fix**: the mechanism no longer exists.
  If a cache is genuinely required by a stated requirement, it is replaced by a bounded cache with
  an eviction policy and a documented size derived from that requirement.

Report a workaround only when the real fix is out of scope, and say so in one explicit sentence.

---

## 3. Prove the fix with a test that fails first

1. Run the repository's existing test suite and record the result before any change.
2. Write a regression test that reproduces the incident condition and **fails on the unmodified
   code**. If it passes before the change, it does not reproduce the incident: rewrite it.
3. Apply the change.
4. Run the same test and the full suite again. The regression test must now pass and no previously
   passing test may fail.
5. Report both runs. A fix with no failing-then-passing evidence is a claim, not a proof.

When the toolchain to run tests is unavailable in the sandbox, say so explicitly, include the test
in the pull request, and state that execution is pending in the pipeline.

---

## 4. Deliver the artifacts

1. Search existing issues first and reuse an equivalent open issue instead of creating a duplicate.
2. Create the issue following the incident report template exactly. Complete every section,
   including References with full ARM resource IDs, workspace IDs, and Application Insights
   resource IDs. Leave no section empty.
3. Create a branch `sre-agent/fix-<issue-number>-<short-slug>` from `main`. Never commit to `main`.
4. Commit the smallest change that satisfies section 2, plus the regression test from section 3.
5. Open the pull request against `main` with these sections:
   - **Summary** — the observable failure in one paragraph.
   - **Root Cause** — the proven mechanism, with `file:line` references.
   - **Changes** — what was removed or replaced, and why that removes the mechanism.
   - **Validation** — the before and after test evidence.
   - **Risk and Rollback** — blast radius and the single revert command.
   - `Closes #<issue>`.
6. Read both artifacts back and report their verified numbers and URLs. Never claim success
   without a successful tool result.

---

## 5. The human boundary is non-negotiable

The pull request is the approval boundary and the end of your work. Never merge autonomously and
never deploy the proposed change. Opening the issue and the pull request completes the task.

This workshop does not build, publish, or deploy Grubify changes. The running application consumes
the canonical public images that are already available on GitHub Packages. Releasing a merged
source change is an external operator activity outside both your scope and this repository's
workshop automation.

Always distinguish these three states in every report, and never conflate them:

| Which state has been reached? | What it means |
| --- | --- |
| Pull request opened | The fix is proposed and reviewable. Nothing is deployed. |
| Pull request merged | A human approved the change. Deployment has not necessarily run. |
| Fix deployed and verified | An external release process completed and the original failure no longer reproduces. |

---

## 6. Report structure

Close every execution with:

- The surviving hypothesis and the evidence that eliminated the others.
- The `file:line` location of the mechanism.
- Whether the change is a fix or a labelled workaround, and why.
- The before and after test evidence.
- The verified issue and pull request URLs.
- The explicit statement that no merge and no deployment were performed.
