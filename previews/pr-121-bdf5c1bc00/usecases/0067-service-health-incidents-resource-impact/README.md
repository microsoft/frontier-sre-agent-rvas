# Azure Service Health incidents and planned maintenance review

![Service Health review summary with field marks 1 and 2](docs/images/report-preview.png)

*SIMULATED render of the current report design. 1 The dated reference, the requested window and the retained lookback stay visible · 2 Active, in-window and future counts are separate views; they overlap and are not additive.*

> **The problem.** Azure had an incident, or planned maintenance, and we found out from our own users.

**What the agent does.** It gathers the service incidents and planned maintenance that Microsoft has published for your subscriptions, the resources that may be affected and what is coming next, in one monthly review.

Three views stay separate and are never added up: communications **updated in the requested window**, events **Active when read**, and **future planned maintenance**. Published potential impact is not a measured workload outage, and a Tracking ID is not a support case number.

## At a glance

| | |
|---|---|
| **Runs** | Monthly, on the 1st at 10:00 UTC, and on demand from chat |
| **Reads** | Azure Service Health events and their impacted resources for one subscription |
| **Changes** | Nothing. Read-only |
| **Delivers** | HTML report, events CSV, impacted-resources CSV and the complete JSON |
| **Agent pieces** | Tool `generate-service-health-report` · skill `service-health-live` · subagent `service-health-live` · scheduled task `Monthly Service Health events review` |
| **Access** | `Reader` on the monitored subscription (or a custom role with `Microsoft.ResourceHealth/events/read` and `events/impactedResources/read`) |
| **Report language** | English |

**Compare with:** [Monthly operations digest](https://microsoft.github.io/frontier-sre-agent-rvas/usecase.html?id=0084-operations-incidents-anomalies-digest) · [SQL Managed Instance maintenance](https://microsoft.github.io/frontier-sre-agent-rvas/usecase.html?id=0086-sqlmi-maintenance-resilience) · [Planned maintenance awareness (idea)](https://github.com/microsoft/frontier-sre-agent-rvas/tree/main/usecases/0050-planned-maintenance-awareness)

## Why it matters

- **One place to look:** incidents and planned maintenance for the subscription, the resources named in them and what is coming next, instead of repeated portal checks.
- **Honest evidence:** every count comes with its UTC window, its source and its coverage; a denied or incomplete read is never shown as zero.
- **Ready for questions:** bounded, filtered queries in chat for the last 24 hours, the next maintenance or the coverage.

## Prerequisites

- An Azure SRE Agent with its user-assigned managed identity.
- SRE Agent Author and SRE Agent Standard User, or SRE Agent Administrator, on the agent resource for the person deploying.
- Someone who can assign `Reader` (or an approved narrower custom role) on the monitored subscription.

## Setup

Create the pieces by hand in the portal, or deploy the manifests with the framework CLI (end of this section). The tool, skill and subagent names reference each other: keep them exactly.

1. **Find the agent identity.** In the Azure portal, open the agent resource group and the managed identity whose name starts with `id-`. Note its **Client ID** for the tool and its **Object (principal) ID** for role assignments. A Client ID is not a secret.
2. **Grant read access.** Run [`permissions/grant-service-health-reader.ps1`](permissions/grant-service-health-reader.ps1) with `-IdentityClientId` (or `-PrincipalId`) and the monitored `-SubscriptionId`. It assigns only `Reader` and skips what the identity already has, also inherited. Add `-WhatIf` first to see what it would assign.
3. **Configure a private copy of the tool.** Download [`generate-service-health-report.py`](manifests/tools/generate-service-health-report.py) and set `SUBSCRIPTION_ID`, `TENANT_ID` and `MANAGED_IDENTITY_CLIENT_ID`, and optionally `CLIENT_NAME` and `COMPANY_LOGO_DATA_URI`. Keep configured copies outside Git. Until they are set, the tool returns a configuration error before any authentication.
4. **Create the Python tool.** In the [SRE Agent portal](https://sre.azure.com), **Build + configure > Agent Canvas > Create ▾ > Tool > Python tool**. Tool Name `generate-service-health-report`, the description from the manifest, the code of your configured `generate-service-health-report.py`, timeout `900` seconds and the 11 parameters of [`manifests/tools/generate-service-health-report.yaml`](manifests/tools/generate-service-health-report.yaml). Leave **Enable Azure Identity** off: the code gets its own tokens with the agent managed identity. Run **Test** on the **Test playground** tab with `{"operation": "report", "period": "previous_month"}`, then **Create tool**.

   ![Create a Python tool: name, timeout, description and code](docs/images/setup-tool.png)
5. **Create the skill.** **Create ▾ > Skill**: name `service-health-live`, the description from its front matter, **Choose tools** > only `generate-service-health-report`, and paste the body of [`SKILL.md`](manifests/skills/service-health-live/SKILL.md) below the front matter the form generates.

   ![Create skill: name, description, SKILL.md and Choose tools](docs/images/setup-skill.png)
6. **Create the subagent.** **Create ▾ > Custom agent**: name `service-health-live`, instructions from `system_prompt` in [`manifests/subagents/service-health-live.yaml`](manifests/subagents/service-health-live.yaml), **Choose skills** > `service-health-live` and **Choose tools** > `generate-service-health-report`. Choosing them replaces the inherited global tools and skills, so the subagent can only run this read-only tool.

   ![Create a custom agent: name, instructions, Choose skills and Choose tools](docs/images/setup-subagent.png)
7. **Test from chat.** **New chat**, type `/agent`, pick `service-health-live` and send the prompt under **Run it**. The answer links the four files and states the UTC window, the reference and the coverage.

   ![New chat with the subagent chip and the test prompt](docs/images/setup-chat.png)
8. **Schedule it.** **Automation > Create ▾ > Scheduled task**: task name `Monthly Service Health events review`, response subagent `service-health-live`, **Custom cron** `0 10 1 * *` (UTC), task details from `prompt` in [`manifests/scheduled-tasks/monthly-service-health-events-review.yaml`](manifests/scheduled-tasks/monthly-service-health-events-review.yaml) and **New chat thread for each run**. Run it once (in **Automation**, tick only this task and select **Run now**) and check the thread before you rely on the schedule.

   ![Create scheduled task: name, response subagent, task details, frequency and message grouping](docs/images/setup-task.png)

**Or deploy the manifests with the CLI.** From the repository root, or the unzipped package, and from a configured copy of the tool (the CLI sends the code as it is in the folder; it has not been run against a live agent yet):

```bash
usecases/_framework/usecases.sh deploy 0067-service-health-incidents-resource-impact --endpoint https://<agent>.azuresre.ai --dry-run
usecases/_framework/usecases.sh deploy 0067-service-health-incidents-resource-impact --endpoint https://<agent>.azuresre.ai
usecases/_framework/usecases.sh verify 0067-service-health-incidents-resource-impact --endpoint https://<agent>.azuresre.ai
```

Every click, with a screenshot, is in the [upstream step-by-step guide](https://github.com/marioaguileraaa/sre-agent-use-cases/tree/main/05-service-health-events-review).

## Run it

In a **New chat**, type `/agent`, pick `service-health-live` and send:

```text
Use service-health-live and only generate-service-health-report. Make exactly one call with operation="report", period="previous_month", and all other parameters at their defaults. Deliver the four actual native file links (HTML, complete JSON, events CSV and impacted-resources CSV). State the returned UTC last-update interval, reference, retained source query start and partial or unknown coverage. Keep requested updates, observed Active and future maintenance distinct. Do not run extra queries or change Azure.
```

More prompts, with the expected result of each, are in [`tests/prompts.md`](tests/prompts.md).

## Read the report

- **Summary:** the review status, records received and in scope, Active when read and future maintenance, with the dated reference and window.
- **Review next:** prioritized steps, each opening the matching records.
- **Communications:** requested updates, Active when read and future maintenance, with the services and regions named and the potentially impacted resources.
- **Sources and method:** every source receipt with HTTP status and pagination, and what the review does not claim.

![Communications updated in the requested window](docs/images/report-requested-updates.png)

*Communications updated in the requested window, with their type, state and published impact.*

## Sample report

[`sample-report/`](sample-report/) holds the four files of a SIMULATED run, generated offline from the upstream mocked source pages (as `tests/offline_demo.py` does) with the fictitious client name `Contoso`: the [HTML report](sample-report/simulated-service-health-20261014T184000Z-d61d092bba3c.html) (download it and open it in a browser), the complete JSON and the two CSVs. No Azure call was made and there are no customer identifiers.

## Cadence

Monthly, on day 1 at 10:00 UTC, for the previous calendar month. It reviews the communications updated in that window; it is not a complete outage history. Use chat queries for the last 24 hours or 7 days between runs.

## Maintain

The tool in `manifests/tools/` is built from `src/`. Edit `src/engine.py` or the report template, then run `python3 src/build_tool.py` and `python3 -m unittest discover -s src/tests`. `usecases.sh validate` fails if the built file is stale.

## Status

`validated`: built, with test prompts in `tests/` and a SIMULATED sample report. Upstream validated it live in a lab on 2026-10-14 (a normal run and one manual run of the monthly task, each with four verified downloads). The sidecar-token identity fix of 16 November 2026 is covered by `src/tests/test_sidecar_tokens.py`. It has not been deployed from this repository with `usecases.sh deploy` yet. This entry turns the idea *Service Health incidents & resource impact* into a scheduled review with on-demand questions.

## Credits

- **Built and tested by** Mario Aguilera: [github.com/marioaguileraaa](https://github.com/marioaguileraaa)
- **Upstream source and step-by-step guide** (every step with a screenshot, troubleshooting and the acceptance checks): [github.com/marioaguileraaa/sre-agent-use-cases/tree/main/05-service-health-events-review](https://github.com/marioaguileraaa/sre-agent-use-cases/tree/main/05-service-health-events-review). MIT license; this entry was converted from commit [`4eb2e90`](https://github.com/marioaguileraaa/sre-agent-use-cases/commit/4eb2e90).
- **Field guide:** [plate 05](https://marioaguileraaa.github.io/sre-agent-use-cases/#plate-05)
- **Earlier idea:** this entry implements *Service Health incidents & resource impact*, first listed from [alsanch/azure-sre-agent-scenarios](https://github.com/alsanch/azure-sre-agent-scenarios), and keeps its id.
