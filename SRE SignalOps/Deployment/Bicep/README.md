**[Home](../../README.md)** | [Lab Details](../../Lab-Details.md)

# Deploy with Bicep

Build the SRE SignalOps environment with Azure Developer CLI (azd) and the Bicep
templates maintained in this project. Deploy Grubify, establish the agent's
identity and access boundary, then validate its operational evidence.

## Prepare

### Project and tools

Install PowerShell 7, Azure CLI, Azure Developer CLI, and Git. Run the guide
commands from the repository root. The azd project is `SRE SignalOps`.

| Deployment component | Local source |
|---|---|
| Service definitions and container builds | [azure.yaml](../../azure.yaml) |
| Deployment parameters and stages | [main.bicep](../../infra/main.bicep) |
| Workload, registry, and observability | [workload.bicep](../../infra/modules/workload.bicep) |
| Agent, identity, and telemetry connectors | [agent.bicep](../../infra/modules/agent.bicep) |
| Workload access roles | [workload-rbac.bicep](../../infra/modules/workload-rbac.bicep) |
| Presenter commands | [Scripts](../../Scripts/README.md) |
| Specialist and response-plan registration | [Register-SignalOpsAgent.ps1](../../Scripts/Register-SignalOpsAgent.ps1) and [Config](../../Config) |

The service manifest builds application sources from this checkout and publishes
them to the environment's registry. The `Student/Resources` service paths are
local directories in this repository, not a dependency on a separate repository.
No external lab checkout, deployed endpoint, or workshop site is required.

Supply your approved tenant and subscription at setup time. Resource names and
verification URLs come from the selected azd environment, not a previous
presenter's deployment. Azure APIs, Microsoft container base images, package
registries, and Microsoft Learn remain normal product dependencies.

## Deploy

Complete these deployment stages in order. Their numbers are separate from
operational missions 01–12. Review each provisioning preview and confirm the
selected environment, subscription, and resource scope before approving writes.

| Stage | Guide | Outcome |
|---|---|---|
| 00 | [Deploy the Workload](./Challenge-00.md) | Grubify API/frontend, registry, Container Apps, Log Analytics, and Application Insights |
| 01 | [Deploy the Agent Core](./Challenge-01.md) | SRE Agent, managed identity, governed RBAC, and managed resource scope |
| 02 | [Deploy Evidence and Incident Routing](./Challenge-02.md) | Two ARM telemetry connectors, then three data-plane Review specialists and an all-severity Review response plan |

The core deployment does not create VM backups, a Teams workflow, or a backup
approval Function. Mission 07 has a separate, explicitly parameterized
[advanced add-on](../../infra/backup.bicep); prepare and approve its VM and
Teams prerequisites with the coach before deploying it.

## Verify

Use the verification checks at the end of each stage. Confirm application health,
current logs and traces, the agent's managed scope and RBAC, both telemetry
connectors, all three Review specialists, and the enabled matching Review
response plan. Missing telemetry or routing is a blocker, not a successful setup.

From the repository root, load the selected environment into the same terminal
used for missions:

```powershell
$Lab = & '.\SRE SignalOps\Scripts\Get-SignalOpsContext.ps1' -EnvironmentName signalops-core
$Lab | Format-List
az account show --query '{subscription:id,tenant:tenantId}' -o table
```

Replace `signalops-core` with the environment you deployed and verify that its
subscription matches the active account. The context helper reads outputs; it
does not provision resources.

After stage 02, record the [Grubify baseline](../../Lab-Details.md), then open
[Missions](../../Missions/README.md). Network and VM scenarios require a separate
coach-provided sandbox or a clearly labeled evidence pack; this deployment does
not provision the hub-spoke or parking scenarios.
