# Azure Backup jobs review

![Azure Backup operations review with field marks 1 to 4](docs/images/report-preview.png)

*Lab run. 1 Requested window · 2 Approved vaults and coverage note · 3 Full downloads · 4 Expected protection shown as Unknown, never guessed.*

> **The problem.** We assume backups work, but nobody looks at the failed jobs until the day we need a restore.

**What the agent does.** It reviews the backup jobs, errors and warnings of your Recovery Services vaults and which items are protected, so IT operations can decide what needs action. It never starts, stops or changes a backup.

Expected protection and coverage percentages stay **Unknown** unless a source proves them: the review shows what the vaults returned and what needs a human decision, not a protection or recovery certification.

## At a glance

| | |
|---|---|
| **Runs** | Monthly, on the 1st at 10:30 UTC (last 14 days), and on demand from chat |
| **Reads** | Azure Backup jobs, job details and protected items of the approved Recovery Services vaults |
| **Changes** | Nothing. Read-only; it never starts, stops or changes a backup and creates no incidents |
| **Delivers** | HTML workpaper, jobs CSV, items and coverage CSV and the complete JSON |
| **Agent pieces** | Tool `generate-azure-backup-report` · skill `azure-backup-live` · subagent `azure-backup-live` · scheduled task `Monthly Azure Backup operations review` |
| **Access** | `Reader` on the monitored subscription |
| **Report language** | English |

**Compare with:** [Monthly operations digest](https://microsoft.github.io/frontier-sre-agent-rvas/usecase.html?id=0084-operations-incidents-anomalies-digest) · [Backup policy compliance and gap detection (idea)](https://github.com/microsoft/frontier-sre-agent-rvas/tree/main/usecases/0010-backup-policy-compliance-gap-detection) · [RTO/RPO gap analysis (idea)](https://github.com/microsoft/frontier-sre-agent-rvas/tree/main/usecases/0066-rto-rpo-gap-analysis)

## Why it matters

- **Failed jobs reviewed every month:** failures, warnings, unfinished and cancelled jobs are listed with their native details before the day a restore is needed.
- **A clear human queue:** every record that needs a decision, by severity, with the evidence.
- **Honest coverage:** history that cannot be verified and sources that were not read are stated, never shown as healthy zeros.

## Prerequisites

- An Azure SRE Agent with its user-assigned managed identity.
- SRE Agent Author and SRE Agent Standard User, or SRE Agent Administrator, on the agent resource for the person deploying.
- The resource IDs of the Recovery Services vaults to review, and someone who can assign `Reader` on the monitored subscription.

## Setup

Create the pieces by hand in the portal, or deploy the manifests with the framework CLI (end of this section). The tool, skill and subagent names reference each other: keep them exactly.

1. **Find the agent identity.** In the Azure portal, open the agent resource group and the managed identity whose name starts with `id-`. Note its **Client ID** for the tool and its **Object (principal) ID** for role assignments. A Client ID is not a secret.
2. **Grant read access.** Run [`permissions/grant-backup-review-reader.ps1`](permissions/grant-backup-review-reader.ps1) with `-IdentityClientId` (or `-PrincipalId`) and the monitored `-SubscriptionId`. It assigns only `Reader` and skips what the identity already has, also inherited. Add `-WhatIf` first to see what it would assign.
3. **Configure a private copy of the tool.** Download [`generate-azure-backup-report.py`](manifests/tools/generate-azure-backup-report.py) and set `SUBSCRIPTION_ID`, `TENANT_ID`, `MANAGED_IDENTITY_CLIENT_ID` and `APPROVED_VAULT_IDS`, and optionally `CLIENT_NAME` and the logo. Keep configured copies outside Git. Until they are set, the tool returns a configuration error before any authentication.
4. **Create the Python tool.** In the [SRE Agent portal](https://sre.azure.com), **Build + configure > Agent Canvas > Create ▾ > Tool > Python tool**. Tool Name `generate-azure-backup-report`, the description from the manifest, the code of your configured `generate-azure-backup-report.py`, timeout `900` seconds and the 1 parameters of [`manifests/tools/generate-azure-backup-report.yaml`](manifests/tools/generate-azure-backup-report.yaml). Leave **Enable Azure Identity** off: the code gets its own tokens with the agent managed identity. Run **Test** on the **Test playground** tab with `{"period": "last_14d"}` (the only parameter), then **Create tool**.

   ![Create a Python tool: name, timeout, description and code](docs/images/setup-tool.png)
5. **Create the skill.** **Create ▾ > Skill**: name `azure-backup-live`, the description from its front matter, **Choose tools** > only `generate-azure-backup-report`, and paste the body of [`SKILL.md`](manifests/skills/azure-backup-live/SKILL.md) below the front matter the form generates.

   ![Create skill: name, description, SKILL.md and Choose tools](docs/images/setup-skill.png)
6. **Create the subagent.** **Create ▾ > Custom agent**: name `azure-backup-live`, instructions from `system_prompt` in [`manifests/subagents/azure-backup-live.yaml`](manifests/subagents/azure-backup-live.yaml), **Choose skills** > `azure-backup-live` and **Choose tools** > `generate-azure-backup-report`. Choosing them replaces the inherited global tools and skills, so the subagent can only run this read-only tool.

   ![Create a custom agent: name, instructions, Choose skills and Choose tools](docs/images/setup-subagent.png)
7. **Test from chat.** **New chat**, type `/agent`, pick `azure-backup-live` and send the prompt under **Run it**. The answer links the four files and states the requested window, the human review queue and the coverage.

   ![New chat with the subagent chip and the test prompt](docs/images/setup-chat.png)
8. **Schedule it.** **Automation > Create ▾ > Scheduled task**: task name `Monthly Azure Backup operations review`, response subagent `azure-backup-live`, **Custom cron** `30 10 1 * *` (UTC), task details from `prompt` in [`manifests/scheduled-tasks/monthly-azure-backup-operations-review.yaml`](manifests/scheduled-tasks/monthly-azure-backup-operations-review.yaml) and **New chat thread for each run**. Run it once (in **Automation**, tick only this task and select **Run now**) and check the thread before you rely on the schedule.

   ![Create scheduled task: name, response subagent, task details, frequency and message grouping](docs/images/setup-task.png)

**Or deploy the manifests with the CLI.** From the repository root, or the unzipped package, and from a configured copy of the tool (the CLI sends the code as it is in the folder; it has not been run against a live agent yet):

```bash
usecases/_framework/usecases.sh deploy 0082-azure-backup-operations-review --endpoint https://<agent>.azuresre.ai --dry-run
usecases/_framework/usecases.sh deploy 0082-azure-backup-operations-review --endpoint https://<agent>.azuresre.ai
usecases/_framework/usecases.sh verify 0082-azure-backup-operations-review --endpoint https://<agent>.azuresre.ai
```

Every click, with a screenshot, is in the [upstream step-by-step guide](https://github.com/marioaguileraaa/sre-agent-use-cases/tree/main/06-azure-backup-operations-review).

## Run it

In a **New chat**, type `/agent`, pick `azure-backup-live` and send:

```text
Use azure-backup-live and only generate-azure-backup-report. Make exactly one call with period="last_14d" for the fixed approved vaults. Deliver HTML, complete source JSON, jobs CSV and items/coverage CSV using all four actual native links. Keep native failures, warnings, unfinished/cancelled jobs and other operations separate. State the returned UTC reference/window and requested versus verified history, source issues and unknown expected protection. Do not recollect, shorten the window, change Azure or create incidents.
```

More prompts, with the expected result of each, are in [`tests/prompts.md`](tests/prompts.md).

## Read the report

- **Summary and verdict:** backup records in the window by state, the human review queue by severity and expected protection (Unknown unless proven).
- **Jobs and human review:** each job with its native state, error and detail, grouped for a decision.
- **Items and coverage:** protected items as returned by the vaults, and which history could not be verified.
- **Sources:** every read with its status; the downloads always include every received record, regardless of filters.

![Source ledger with the status of every read](docs/images/report-source-ledger.png)

*Source ledger: every read with its HTTP status and pagination, so a missing source is never mistaken for an empty one.*

## Sample report

[`sample-report/`](sample-report/) holds the four files of a SIMULATED run generated offline from the upstream synthetic fixtures, with the fictitious client name `Contoso`: the [HTML report](sample-report/simulated-20261014T090000Z-ac528d818534.html) (download it and open it in a browser), the complete JSON, the jobs CSV and the items and coverage CSV. No Azure call was made and the figures are not real.

## Cadence

Monthly, on day 1 at 10:30 UTC, for the last 14 days. The cadence leaves gaps between runs; ask in chat for the last 14 days whenever you need a fresh view.

## Status

`validated`: built, with test prompts in `tests/` and a SIMULATED sample report. Upstream ran it live in a lab on 2026-10-14 (a normal report and one manual run of the monthly task, each with four verified downloads). The sidecar-token identity fix of 16 November 2026 is covered upstream by unit tests. It has not been deployed from this repository with `usecases.sh deploy` yet.

## Credits

Built and tested by Mario Aguilera ([@marioaguileraaa](https://github.com/marioaguileraaa)). Source: [`06-azure-backup-operations-review`](https://github.com/marioaguileraaa/sre-agent-use-cases/tree/main/06-azure-backup-operations-review) in `marioaguileraaa/sre-agent-use-cases` (MIT), commit `4eb2e90`. The upstream guide has every step with a screenshot, troubleshooting and the acceptance checks. Field guide: [plate 06](https://marioaguileraaa.github.io/sre-agent-use-cases/#plate-06).
