# Test prompts

In a new chat, type `/agent`, select `rbac-access-reviewer` and send one prompt at a time. Before the tool is configured, every prompt returns a configuration message and makes no Azure call.

## 1. Monthly review

```text
Run the monthly Azure RBAC privileged access review and give me the links to the HTML report, CSV and JSON with the executive summary, Owner decisions, coverage and required actions.
```

Tool call:

```json
{}
```

**Expected:** One call to generate-rbac-privileged-review with no arguments. The answer gives the three file links first, then the executive summary, the Owner decisions (Remove orphaned, Remove redundant, Individual review, Compliant), the coverage and the actions. It proposes changes and never makes them.

## 2. Removable today

```text
From this review, list only the assignments that can be removed today without anybody losing access, with scope, role, identity and the reason for each one.
```

**Expected:** Only Remove orphaned and Remove redundant rows; each redundant row names the parent assignment that already covers the access.

## 3. Non-human identities that can grant access

```text
Which service principals and managed identities can grant access (Owner or User Access Administrator), which of them belong to another tenant and which have not signed in for more than 90 days?
```

**Expected:** The non-human identities with tier 0 roles, owner tenant and last sign-in when Microsoft Graph returned it; unresolved identities are labelled as such, not guessed.

## 4. Partial coverage

```text
Is the coverage of this review complete? If not, what was not read and which permission is missing?
```

**Expected:** The coverage block, for example groups not read because GroupMember.Read.All is missing, and the identities left as Unresolved identity. Partial coverage is never presented as a clean result.
