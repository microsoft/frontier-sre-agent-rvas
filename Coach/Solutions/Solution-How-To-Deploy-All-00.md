# Solution 00 — How To Deploy Everything

This is the **single entry point** to deploy the whole solution from a clean checkout:
**Terraform infrastructure + Grubify application (built and pushed to ACR) + Azure SRE Agent
(control plane) + Azure SRE Agent data-plane configuration.**

All the pieces live under `Coach/Solutions/`:

| Folder | What it is | Deployment path |
| --- | --- | --- |
| [`Infra/`](Infra/) | Terraform: hub-spoke network, IaaS spokes, monitoring, ACR + Container Apps, and the SRE Agent resource + connectors + RBAC | `terraform apply` |
| [`Infra/scripts/`](Infra/scripts/) | SRE Agent config scripts: `sre-agent-config.sh` (data-plane) and `.sre-agent-apply-all.sh` (validate → plan → apply → verify wrapper) | bash |
| [`Student/Resources/scenarios/scripts/`](../../Student/Resources/scenarios/scripts/) | Demo scenario scripts: trigger/restore faults, generate traffic, validate, run KQL queries | bash |
| [`AZ-SRE-Agent-Configuration/`](AZ-SRE-Agent-Configuration/) | SRE Agent **desired state** (skills, subagents, tools, connectors, knowledge, incident filters, scheduled tasks, repos) applied via the data-plane API | `sre-agent-config.sh apply` |
| [`Student/Resources/grubify/`](../../Student/Resources/grubify/) | The Grubify / Sample Food application (backend + frontend) deployed to Container Apps | `az acr build` (run by Terraform) |
| [`docs/`](docs/) | Deep-dive reference docs (ADRs, KQL catalog, resource references, use-case maps) | — |

> **From a clean checkout the whole thing is three commands:** `terraform apply`, then
> `sre-agent-config.sh apply`, then `sre-agent-config.sh verify`.

## What gets deployed (and where)

- **Azure SRE Agent** — `contoso-sre-agent-dev` in `rg-sec-sreagent` (**Sweden Central**). Default
  model **Anthropic Claude Opus** via Microsoft Foundry.
- **Hub-spoke lab** (**West Europe**): `rg-weu-hub-connectivity` (Azure Firewall, Bastion, shared
  observability), `rg-weu-spoke-web-api-iaas` (client + web VMs + internal LB),
  `rg-weu-spoke-data-iaas` (API + PostgreSQL VMs).
- **Grubify on Azure Container Apps** (**France Central**): `rg-frc-spoke-foodapp-paas`
  (ACR + Container Apps environment + `ca-vflta-food-api` + `ca-vflta-food-frontend`).

Ownership boundary (see [ADR 0001](docs/azure-sre-agent/adr/0001-sre-agent-iac-boundaries.md)):

| Area | Source of truth | Mechanism |
| --- | --- | --- |
| Resource group, managed identity, RBAC, Log Analytics, App Insights | `Infra/` | AzureRM provider |
| SRE Agent resource + Azure Monitor incident platform + telemetry connectors | `Infra/` | AzAPI `Microsoft.App/agents@2026-01-01` |
| Skills, subagents, tools, common prompts, scheduled tasks, incident filters, repos, knowledge | `AZ-SRE-Agent-Configuration/` | Data-plane REST API via `sre-agent-config.sh` |
| Grubify container images | `Student/Resources/grubify/` | `az acr build`, run by Terraform before the Container Apps are created |

Official references: Azure SRE Agent IaC — <https://learn.microsoft.com/en-us/azure/sre-agent/deploy-iac> ·
API — <https://learn.microsoft.com/en-us/azure/sre-agent/api-reference>.

---

## Step 0: Prerequisites

**Local tools** (on your `PATH`):

| Tool | Min version | Why | Install |
| --- | --- | --- | --- |
| **Azure CLI** (`az`) | 2.60+ | Deployment, `az acr build`, config script | <https://learn.microsoft.com/cli/azure/install-azure-cli> |
| **Terraform** | 1.5.0+ | Provisions all Azure resources and orchestrates the image build | <https://developer.hashicorp.com/terraform/install> |
| **jq** | 1.6+ | JSON parsing in the scripts | <https://jqlang.github.io/jq> |
| **Python 3 + PyYAML** (or `yq`) | 3.8+ | YAML parsing in `sre-agent-config.sh` | `pip install pyyaml` |
| **GitHub CLI** (`gh`) | 2.0+ | Supplies the token for the `github-mcp` connector | <https://cli.github.com> |
| **curl**, **bash 4+** | any | Endpoint checks; all scripts are bash | preinstalled on Linux/macOS/WSL |

> **No local Docker is required** — the Grubify images build server-side with `az acr build`.

**Azure subscription & identity**

- An Azure subscription and an identity signed in with `az login` and selected via
  `az account set --subscription <id>`, in the subscription's Microsoft Entra ID tenant.
- **Model availability:** the agent's default model (Anthropic Claude Opus via Foundry) must be
  enabled for your subscription/tenant; the agent runs in **swedencentral** — check data residency.

**RBAC** — the deploying identity creates resource groups **and role assignments**, so it must be
able to *grant* roles:

| Scope | Role(s) | Why |
| --- | --- | --- |
| Subscription | **Owner** *(simplest)* — or **Contributor** + **User Access Administrator** | Create every resource **and** the RG/subscription-scope role assignments for the agent identity, plus your own **SRE Agent Administrator** grant. |

Terraform assigns these **for you**: the agent's user-assigned identity receives **Reader**,
**Log Analytics Reader**, **Monitoring Reader** on the managed scopes, **Monitoring Contributor** +
**Contributor** at subscription scope, and **AcrPull** for the Container Apps pull identity; your
signed-in user receives **SRE Agent Administrator** on the agent.

**Resource providers** (auto-registered by AzureRM; confirm enabled): `Microsoft.App`,
`Microsoft.ContainerRegistry`, `Microsoft.OperationalInsights`, `Microsoft.Insights`,
`Microsoft.Network`, `Microsoft.Compute`, `Microsoft.ManagedIdentity`, `Microsoft.Authorization`.

**Regions & quota:** `swedencentral` (agent), `westeurope` (hub + IaaS spokes),
`francecentral` (Grubify). Ensure quota for **~7 `Standard_B2s_v2` VMs**, one **Azure Firewall**,
one **Azure Bastion**, and Container Apps (Consumption).

**GitHub access** — run `gh auth login` with the **`repo`** scope, then
`export GITHUB_PAT="$(gh auth token)"` (feeds the `github-mcp` connector in Step 3).

---

## Deterministic naming (pinned suffix)

This solution **pins** the naming suffix so a from-clean `terraform apply` is reproducible:
`local.demo_suffix = "4iebz8"` in [`Infra/locals.tf`](Infra/locals.tf) produces the
exact names the solution expects — ACR `acrvflta4iebz8food`, flow-log storage `vflta4iebz8flow`,
workspace `law-vflta-4iebz8`. This keeps the ACR name hardcoded in
[`Student/Resources/grubify/scripts/build-and-push.sh`](../../Student/Resources/grubify/scripts/build-and-push.sh) valid with no manual step.

> **Deploying an isolated instance / a brand-new environment?** Change these **four** places so the
> names stay consistent and globally unique:
> 1. `local.demo_suffix` in `Infra/locals.tf` (e.g. a new 6-char lowercase-alphanumeric value).
> 2. `ACR_NAME` (and, if needed, `RESOURCE_GROUP`/`SUBSCRIPTION_ID`) in `Student/Resources/grubify/scripts/build-and-push.sh` — it must equal `acrvflta<suffix>food`.
> 3. The subscription ID in `Infra/main.tf` and `Infra/locals.tf`.
> 4. `SUB` (and `RG`/`AGENT` if you rename them) are resolved automatically from `terraform output` by `.sre-agent-apply-all.sh`.

---

## Step 1: Get the code

Everything is already in this repository under `Coach/Solutions/` — **Grubify is included as plain
files** (not a git submodule), so there is nothing extra to initialize. Just make sure you are on the
right branch and signed in to Azure:

```bash
az login
az account set --subscription "<Your Subscription ID>"
cd Coach/Solutions
```

All commands below are run from `Coach/Solutions/`.

---

## Step 2: Deploy infrastructure and application (Terraform)

A single `terraform apply` provisions the network, VMs, monitoring, ACR and Container Apps, **builds
and pushes the two Grubify images** (via a `terraform_data` `local-exec` that runs
`Student/Resources/grubify/scripts/build-and-push.sh`), and creates the Azure SRE Agent resource with its Azure
Monitor incident platform, telemetry connectors and RBAC.

```bash
terraform -chdir=Infra init
terraform -chdir=Infra plan
terraform -chdir=Infra apply
```

> The image build runs **before** the Container Apps are created (they pull
> `grubify-api:v1.0.0` / `grubify-frontend:v1.0.0` on their first revision). No local Docker is used.

Capture the values you will need next:

```bash
terraform -chdir=Infra output agent_portal_url
terraform -chdir=Infra output -raw sample_food_resource_group_name
```

---

## Step 3: Configure the Azure SRE Agent (data plane)

The agent's **behavior** (skills, subagents, tools, connectors, knowledge, incident filters,
scheduled tasks, repos) lives in [`AZ-SRE-Agent-Configuration/`](AZ-SRE-Agent-Configuration/) and is
applied with `sre-agent-config.sh`. See [Solution 03](Solution-How-To-Azure-SRE-Agent-Config-03.md)
for the full command model.

```bash
export SUB="<Your Subscription ID>"
export RG="rg-sec-sreagent"
export AGENT="contoso-sre-agent-dev"
export GITHUB_PAT="$(gh auth token)"   # for the github-mcp connector

# Validate locally (no Azure writes), then apply the full desired state:
./Infra/scripts/sre-agent-config.sh validate
./Infra/scripts/sre-agent-config.sh apply --subscription "$SUB" --resource-group "$RG" --agent "$AGENT"
```

Or run the whole `validate → plan → apply → verify` cycle with the wrapper (it reads `SUB`/`RG`/`AGENT` from `terraform output` automatically):

```bash
./Infra/scripts/.sre-agent-apply-all.sh
```

> The GitHub **OAuth** connector (`connectors/github.yaml`) is applied automatically; after the first apply, complete the one-time OAuth authorization in the SRE Agent portal (Connectors → github → Authorize). The Outlook/Teams notification connectors are OAuth-interactive and stay `example-`-prefixed (excluded from apply).

---

## Step 4: Verify

```bash
./Infra/scripts/sre-agent-config.sh verify --subscription "$SUB" --resource-group "$RG" --agent "$AGENT"
terraform -chdir=Infra output agent_portal_url   # open this in the browser
Student/Resources/scenarios/scripts/validate.sh             # end-to-end lab sanity check
Student/Resources/scenarios/scripts/validate-sample-food-app.sh
```

Open the **agent portal URL** and confirm the skills, subagents, connectors, incident filters and
scheduled tasks are present.

---

## Day-2: rebuild the Grubify images manually

The images are built automatically during Step 2. To rebuild after code changes:

```bash
cd Student/Resources/grubify
bash scripts/build-and-push.sh v1.0.0     # server-side az acr build; also updates :latest
```

Then restart the Container Apps revisions (or `az containerapp update`) to pick up the new image.

---

## Teardown

```bash
terraform -chdir=Infra destroy
```

This removes all Azure resources created by the solution. The data-plane configuration lives on the
agent; delete individual items with `./Infra/scripts/sre-agent-config.sh delete --target <t> --name <n> --yes`
before destroying the agent if you need a clean slate.

---

## Where to go next

- **[Solution 01 — Architecture](Solution-Architecture-01.md)** — the lab and the agent's desired-state design, object by object.
- **[Solution 02 — Demo Runbook](Solution-Demo-Runbook-02.md)** — the 6 live demo scenarios end to end.
- **[Solution 03 — SRE Agent Config script guide](Solution-How-To-Azure-SRE-Agent-Config-03.md)** — every `sre-agent-config.sh` command.
- **[Infra README](Infra/README.md)** — the Terraform layer.
- **[docs/](docs/)** — ADRs, KQL catalog, resource references, use-case maps.

## References

- Azure SRE Agent — deploy with IaC: <https://learn.microsoft.com/en-us/azure/sre-agent/deploy-iac>
- Azure SRE Agent — API reference: <https://learn.microsoft.com/en-us/azure/sre-agent/api-reference>
- `Microsoft.App/agents` (Terraform): <https://learn.microsoft.com/en-us/azure/templates/microsoft.app/agents?pivots=deployment-language-terraform>
- `agents/connectors` (Terraform): <https://learn.microsoft.com/en-us/azure/templates/microsoft.app/agents/connectors?pivots=deployment-language-terraform>
- Terraform style guide: <https://developer.hashicorp.com/terraform/language/style>
