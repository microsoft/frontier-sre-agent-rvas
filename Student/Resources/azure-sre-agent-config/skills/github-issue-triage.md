---
name: github-issue-triage
description: Use when open GitHub issues must be classified, labelled, and answered with a triage comment. Selects untriaged customer issues, classifies them against the project taxonomy, applies labels, posts a structured comment, and decides whether the evidence justifies escalating to a source fix.
---

# github-issue-triage

Use this skill to triage open GitHub issues: select the untriaged ones, classify them, label them,
and answer with a structured comment.

The classification taxonomy, the comment template, and the guardrails are reference content and live
in the knowledge base document *Sample Food Ordering App GitHub Issue Triage Runbook*. Search memory
for it before you start; this skill defines only the procedure that executes against it.

---

## 1. Select what to triage

Repository: the connected `grubify` repository, which is the workshop repository. The application
source you may act on lives under `Student/Resources/grubify`; everything outside that folder is
out of scope.

Process an issue only when **all** of these are true:

- The title contains `[Customer Issue]`.
- No comment starting with `🤖 **Grubify SRE Agent Bot**` already exists on it.

Skip everything else and say how many issues you skipped and why. Never re-triage an issue that
already carries a bot comment: duplicate triage destroys the signal the labels are meant to carry.

---

## 2. Classify

Read the title and the full body before deciding. Classify into exactly one primary category:

| Which category applies? | Choose it when |
| --- | --- |
| Bug | Observable application behaviour is wrong, or an endpoint fails |
| Performance | Latency, memory, processor, or scaling symptoms are reported |
| Feature Request | The reporter asks for behaviour that does not exist yet |
| Question | The reporter needs an explanation, not a change |

For a Bug, add exactly one sub-category: `api-bug`, `frontend-bug`, `infrastructure`, or
`memory-leak`.

Assign the severity from the reported impact, not from the tone of the report. A single user
inconvenienced is not the same as checkout failing for everyone.

---

## 3. Label

Apply the labels that match the classification and the severity. Use `get_label` and
`list_issue_types` to read the available label metadata rather than inventing label names that do
not exist in the repository.

Add `needs-more-info` when the issue is a Bug and any of these is missing: reproduction steps, the
timestamp in Coordinated Universal Time, the affected endpoint or path, or the observed versus
expected behaviour.

---

## 4. Comment

Post one comment that starts with `🤖 **Grubify SRE Agent Bot**` and contains:

- the classification and, for a Bug, the sub-category;
- a short analysis of what the evidence actually shows;
- the next step, or the precise question the reporter must answer;
- a status indicator at the end.

Follow the comment template in the knowledge base runbook. Keep the operator-visible text in
Italian, as the agent-level instructions require, while leaving identifiers, labels, endpoints, and
log excerpts in their original technical form.

---

## 5. Decide whether to escalate to a source fix

Escalate only when **all** of these are true:

- the issue is a Bug, not a Question or a Feature Request;
- it is reproducible from the evidence in the issue;
- the evidence is sufficient to identify a causal code path.

When they hold, follow the `source-fix-delivery` skill, which owns the engineering standard and the
pull-request workflow. Do not restate that procedure here: execute it.

When they do not hold, stop at the triage comment and state explicitly why no fix was proposed.

---

## 6. Guardrails

- Never close an issue automatically.
- Never label a security-sensitive issue publicly without human review.
- Never push directly to `main` and never merge a pull request autonomously.
- Never claim a repository action succeeded without a successful tool result to quote.

---

## 7. Report

Close every run with the number of issues examined, the number triaged, the number skipped with the
reason, the classification distribution, and the verified URL of every comment and pull request
created.
