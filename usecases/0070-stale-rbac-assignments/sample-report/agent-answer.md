# Azure RBAC privileged access review: 2026-11-03 (partial coverage)

- HTML report: [rbac-privileged-access-review-2026-11-03.html](rbac-privileged-access-review-2026-11-03.html) (path: /root/sreagent/terminalRoot/tmp/ThreadFiles/00000000-0000-4000-8000-148c248f3b91/rbac-privileged-access-review-2026-11-03.html)
- CSV for Excel: [rbac-privileged-access-review-2026-11-03.csv](rbac-privileged-access-review-2026-11-03.csv) (path: /root/sreagent/terminalRoot/tmp/ThreadFiles/00000000-0000-4000-8000-148c248f3b91/rbac-privileged-access-review-2026-11-03.csv)
- JSON for automation: [rbac-privileged-access-review-2026-11-03.json](rbac-privileged-access-review-2026-11-03.json) (path: /root/sreagent/terminalRoot/tmp/ThreadFiles/00000000-0000-4000-8000-148c248f3b91/rbac-privileged-access-review-2026-11-03.json)

## Executive summary
- **175** role assignments were inventoried. **69** are privileged, held by 46 distinct identities: Tier 0 (access control) 35, Tier 1 (full control) 10, Tier 2 (service admin) 24.
- **Owner: 30 assignments.** 14 can be removed without anyone losing access (10 belong to deleted identities, 4 are duplicates). The other 16 need individual review. None are compliant.
- Across all privileged roles, **17** assignments can be removed without changing effective access.
- **All Tier 0 and Tier 1 access is permanent (100%)** and there are **no PIM eligibilities**. No one requests privileged access just in time.
- Coverage is **partial**: Microsoft Graph could not resolve 3 groups.

## Owner decisions
| Owner | Count |
|---|---|
| Total | 30 |
| Remove · orphaned (deleted identity) | 10 |
| Remove · redundant (already covered by another assignment) | 4 |
| **Removable without access loss** | **14** |
| Individual review | 16 |
| Compliant | 0 |

## Decisions by type (all privileged roles)
| Decision | Count |
|---|---|
| Remove · orphaned | 10 |
| Remove · redundant | 7 |
| Individual review | 30 |
| Compliant | 22 |

## Main review signals
| Signal | Assignments |
|---|---|
| Non-human identity that can grant access | 17 |
| No sign-in for more than 90 days | 17 |
| Management group or subscription scope | 10 |
| Unresolved identity (Graph permissions) | 5 |
| Access delegation without a condition | 3 |
| Application from another tenant | 2 |

## Top 5 review items
| # | Decision | Role | Identity | Scope | Proposed action |
|---|---|---|---|---|---|
| 1 | Remove · orphaned | Owner | Deleted identity | Root management group | Remove the assignment through an approved change |
| 2 | Remove · orphaned | Owner | Deleted identity | Root management group | Remove the assignment through an approved change |
| 3 | Remove · orphaned | Owner | Deleted identity | Root management group | Remove the assignment through an approved change |
| 4 | Remove · orphaned | Owner | Deleted identity | Root management group | Remove the assignment through an approved change |
| 5 | Remove · orphaned | Owner | Deleted identity | Root management group | Remove the assignment through an approved change |

All five are Owner at the root management group held by identities that no longer exist, so they are the top priority. Assignment IDs are in the CSV and JSON.

## Coverage: **partial**
| Source | Status |
|---|---|
| Subscription contoso-production: role assignments | ok |
| Microsoft Graph token | ok |
| Apps and managed identities | 31 resolved, 10 orphaned |
| Users | 2 resolved |
| **Groups** | **3 denied** |
| User sign-in activity | ok |
| Service principal sign-in activity | ok |
| Group membership | ok |

## Required actions
1. **3 groups could not be read in Microsoft Graph.** For assignments made to those groups, the review cannot confirm the group's identity or whether the assignment is redundant. They are counted under "Unresolved identity (Graph permissions)" (5 assignments in total). Check that the agent's managed identity has the Graph application permissions `GroupMember.Read.All` (or `Group.Read.All`), `User.Read.All`, `Application.Read.All` and `AuditLog.Read.All`, granted with admin consent. Then run the review again.
2. **Only one subscription was covered.** Assignments inherited from management groups are included, but other subscriptions are not. To cover them, give the agent `Reader` on those subscriptions or on the management group.
3. **Removals and changes:** this review is read only. Removing the 17 assignments flagged as removable, and moving permanent Tier 0 and Tier 1 access to PIM eligibility, must be done by a person through an approved change.

## Artifacts & links
- [rbac-privileged-access-review-2026-11-03.html](rbac-privileged-access-review-2026-11-03.html)
- [rbac-privileged-access-review-2026-11-03.csv](rbac-privileged-access-review-2026-11-03.csv)
- [rbac-privileged-access-review-2026-11-03.json](rbac-privileged-access-review-2026-11-03.json)