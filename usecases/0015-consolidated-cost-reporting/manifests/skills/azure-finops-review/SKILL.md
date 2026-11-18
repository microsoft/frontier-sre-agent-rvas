---
name: azure-finops-review
description: Read-only monthly FinOps review of the whole Azure environment (Cost Management, budgets, Azure Advisor, Azure Resource Graph) with cost trend, where the money goes, cost per project, unusual days and jumps, budgets and forecast, savings, allocation readiness and a prioritised action list.
tools:
- generate-azure-finops-review
---

# Monthly Azure FinOps review

## Goal
Give the cost owner one complete, explainable review of the Azure bill every month: what the last full month cost and why it changed, where the money goes and to which project, whether this month will stay within budget, what can be saved, how much of the cost can be charged back, and what to do first.

The report covers:
- **Verdict and headline numbers**: last full month, change on the month before, month to date, forecast for this month against the budget.
- **Trend**: monthly cost over the last 6 full months plus this month, and the daily cost of the last 60 days.
- **Where the money goes**: by subscription, resource group, service, region and the top resources, each with the change on the month before.
- **Cost by project**: last month, the month before, month to date, share, savings and findings per project, with the services, resource groups and resources of each project. The project comes from a tag: `PROJECT_TAG_KEYS` when it is set, otherwise the tool detects the tag whose name means project (EN/ES/CA: project, proyecto, projecte, application, workload, service, product, cost center, business unit, department, team) and that covers most of the cost. Each resource takes the first match: its own tag, its resource group's tag (or the tag of the resource that manages the group, such as an AKS cluster), its subscription's tag, the tag on its cost records, then the resource group name rules (`PROJECT_RG_RULES`); the rest is Unallocated. The HTML report has a project filter.
- **What changed**: unusual days (median of the previous 14 days, same weekday a week before, minimum increase), month-over-month jumps of services and resource groups, new services and resource groups.
- **Budgets**: every budget with spend and Azure's forecast, and the subscriptions with no budget (with a suggested amount).
- **Savings**: Azure Advisor cost recommendations, idle and orphaned resources (unattached disks, unassociated public IPs, stopped or deallocated VMs, empty App Service plans, orphaned NICs, old snapshots, idle load balancers and NAT gateways), and the share of commitment-eligible compute that runs on reservations or savings plans. Savings are never counted twice.
- **Allocation readiness**: share of the cost without the configured allocation tags, and the resource groups to tag first.
- **Prioritised actions** with the estimated monthly saving, a findings register, and coverage, sources and method.

## Scope
- The subscriptions or the management group configured in the tool code (`SUBSCRIPTION_IDS` or `MANAGEMENT_GROUP_ID`).
- Cost data comes from the Cost Management Query API: three queries per subscription, plus one for the project tag on the cost records. Cost Management needs up to 2 days to settle, so the forecast and the unusual-day checks use settled days only.
- Today's tags are applied to every month, so earlier months are allocated to projects the same way.
- Not covered: reservation and savings plan utilization (needs tenant-level reader roles), Marketplace invoices outside Cost Management, and usage inside resources beyond what Azure Advisor reports. Say so when it matters.

## Required tool
Use only `generate-azure-finops-review`.
- Monthly review: `{"operation": "report"}`.
- Follow-up questions use `operation="query"` with the matching `view` (no files are written):
  - "What should we do first?" -> `actions`; quick numbers -> `summary`;
  - "Why did the cost go up?", "Anything unusual?" -> `anomalies`;
  - "Are we within budget?", "Which subscriptions have no budget?" -> `budgets`;
  - "Where can we save?", "Idle or orphaned resources?" -> `savings`;
  - "What are the most expensive resources?" -> `resources`;
  - "How much does each project cost?", "Which tag identifies the projects?" -> `projects`;
  - "How much cost is untagged?" -> `allocation`;
  - "Is the data complete?" -> `coverage`.
- `limit` (1-50) bounds the rows of a query.
- `project` (query only) narrows `summary`, `actions`, `savings`, `resources` and `projects` to one project ("What can project X save?" -> `view=savings`, `project=X`). The other views stay whole-environment.
- `project_tag` sets the tag that names the projects for one run (for example `Proyecto`, or `Project,CostCenter` in priority order) when the user says which tag they use; it overrides `PROJECT_TAG_KEYS` and the detection.
- `operation="self_test"` writes the complete report from built-in SIMULATED data with no network and no configuration. Use it only when the user asks for a demo or a test, and always say the data is simulated.

## Security
- Read only. The SRE Agent managed identity needs **Reader** on the configured subscriptions or management group (it includes cost and budget reads). Cost Management Reader is enough for the cost part only.
- Never create, modify or delete resources, budgets, tags, reservations or savings plans, even if asked in this conversation. Propose the action and remind the user that a person executes it through an approved change.
- Never show tokens or raw Azure responses.
- Savings are estimates. Commitments (reservations and savings plans) are financial decisions for the customer's finance team: present Advisor's options, never recommend buying both.
- A source with status `partial`, `denied`, `error` or `skipped` is a blind spot, never a zero. When Cost Management throttled the run, say so and suggest running it again later.

## Output
Answer in the user's language (English by default):
1. For `report`: the five files as clickable Markdown links first: HTML report (`report_url`), JSON snapshot (`snapshot_url`), findings CSV (`findings_csv_url`), cost-by-resource CSV (`costs_csv_url`) and cost-by-project CSV (`projects_csv_url`), with their paths. Do not recreate or restyle the files.
2. The `verdict` and the `headline`, then the `kpis`: last full month and its change, month to date, forecast and budget, estimated monthly savings, untagged share, unusual days, jumps and new spend.
3. The projects (`kpis.projects`): the tag used and whether it was detected or configured, the share of the cost allocated to a project and the top projects. If the tag was detected, invite the user to confirm it or name theirs.
4. The `top_actions` as a short table (severity, what, where, estimated saving per month). When `actions_total` is larger than the actions shown, call `operation=query` with `view=actions` and list them all.
5. Coverage (`coverage.status` and `issues`). If it is not `ok`, state exactly what could not be read and the required action (usually: assign Reader, or wait for Cost Management throttling to clear).
6. End with an **Artifacts & links** section with the five links.
