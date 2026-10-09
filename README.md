# Frontier Azure SRE Agent Solution

## Introduction

The Frontier Azure SRE Agent Solution is a comprehensive framework designed to enhance the reliability, scalability, and performance of applications deployed on Microsoft Azure. This solution provides a set of tools, best practices, and automation scripts that enable Site Reliability Engineers (SREs) to effectively monitor, manage, and optimize their cloud infrastructure using Azure SRE agent.

## Requirements

**Run workshop commands in Linux Bash.** Use the supplied Dev Container in
**GitHub Codespaces on your own fork** (recommended), WSL2 with Ubuntu, a local
Linux Dev Container, or native Ubuntu. Native PowerShell, CMD, Git Bash, and
macOS shell execution are not supported by the workshop automation: it uses
Bash, GNU Make, GNU utilities, and Linux paths.

### Choose your environment

| Environment | What you need | Getting started |
|---|---|---|
| **GitHub Codespaces (recommended)** | GitHub account, permission to fork, Codespaces access and available quota/billing, browser | Fork this repository, then on **your fork** choose **Code → Codespaces → Create codespace**. The repository is already checked out; do not clone it again. Wait for container setup and local pre-flight checks to finish. |
| **WSL2 / Ubuntu** | Windows with WSL2, Ubuntu, and tools installed **inside Ubuntu** | Follow the [WSL environment guide](https://learn.microsoft.com/windows/wsl/setup/environment). Clone your fork under your Linux home directory (for example `~/src`), not `/mnt/c`. Open VS Code from Ubuntu using `code .` and confirm the window is connected to WSL. |
| **Local Linux Dev Container** | VS Code, Dev Containers extension, and a running Docker-compatible host; Windows hosts use WSL2/Linux containers | Clone your fork and choose **Dev Containers: Reopen in Container**. Run commands in the container terminal, not the host terminal. macOS users should use this Linux container path. |
| **Native Ubuntu** | Ubuntu and the tools below | Clone your fork and install/verify the common tools before deployment. |

Codespaces does **not** require Docker or Terraform installed on your laptop.
Container setup installs tools but does not log in to Azure, deploy resources,
create an agent, or configure its capabilities. If setup fails, inspect the
creation log and fix the reported dependency failure before continuing. After
container configuration changes, use **Codespaces: Rebuild Container** or
**Dev Containers: Rebuild Container**.

### Tools and accounts

| Requirement | Common / Azure Operations | SQL Server DBA additions |
|---|---|---|
| Linux tooling | Bash 4+, GNU Make, Git, GNU coreutils/findutils, `curl`, `jq`, `envsubst` (gettext), Python 3 | Microsoft ODBC `sqlcmd` with the approved Entra authentication method |
| YAML parsing | Python 3 with PyYAML (recommended), or **Mike Farah yq** supporting `yq -o=json`; other tools named `yq` are not interchangeable | Same |
| Terraform | **1.5+** for Make-based lab deployment | Needed when using the Coach reference Terraform deployment |
| Azure CLI | Working Linux installation and Azure login | **2.62+** and the `containerapp` extension |
| GitHub | Your own fork, `origin` pointing to it, Issues enabled; permission to authorize the workshop GitHub connector | Your own fork for workshop assets |
| Azure access | Enabled subscription; permission to create lab resources and role assignments (Owner, or Contributor plus an appropriate RBAC administration role) | Registry/image-pull and MCP caller-role assignments, approved SQL administrator, and Entra/database permissions |
| Agent access | Permission to create/use Azure SRE Agent; associate every deployed workload resource group and grant the agent Contributor for the full Operations track | Existing agent with custom MCP connector, skill, and custom-agent authoring access |

For Ubuntu/WSL, common utility packages are `make git jq curl gettext-base
coreutils findutils python3 python3-yaml`. Install [Azure CLI for Linux](https://learn.microsoft.com/cli/azure/install-azure-cli-linux)
and [Terraform](https://developer.hashicorp.com/terraform/install) using their
official instructions. For a manual Ubuntu/WSL setup, install the utility
packages explicitly before checking readiness:

```bash
sudo apt-get update
sudo apt-get install -y make git jq curl gettext-base coreutils findutils python3 python3-yaml
```

The Dev Container supplies these tools and the DBA
SQL client. Install the Container Apps extension explicitly when using your own
environment: `az extension add --name containerapp`. Validation never installs it.

Docker and language SDKs are **not required for the Azure Operations deployment
using published images**. Docker/registry build access is needed if you follow
the DBA guide's image-build path; a local .NET 10 SDK is only needed to build or
test the MCP source outside Docker. An approved graphical SQL client can replace
`sqlcmd` for manual SQL work, but the command-line DBA pre-flight intentionally
checks the reproducible `sqlcmd` path.

### Azure readiness

- Default region: **`swedencentral`**. Confirm availability of Azure SRE Agent,
  Container Apps and the other selected services for your subscription; a CLI
  quota check cannot guarantee live service capacity.
- The default Operations lab creates **eight `Standard_B2s_v2` VMs / 16 vCPUs**.
  Check both regional total and the applicable VM-family quota **available**
  above current usage. Disabling Madrid or Paris reduces the new-lab requirement
  by two vCPUs each and changes which scenarios you can complete.
- Operations requires a regional **`NetworkWatcher_<region>` in
  `NetworkWatcherRG`** before Terraform runs. Terraform reads it; it does not
  create it. Ask your administrator to enable it if absent.
- Required Operations providers: `Microsoft.App`, `Microsoft.Network`,
  `Microsoft.Compute`, `Microsoft.OperationalInsights`, `Microsoft.Insights`,
  `Microsoft.Storage`, `Microsoft.Web`, and `Microsoft.ManagedIdentity`.
  DBA hosting additionally uses `Microsoft.Sql` and `Microsoft.ContainerRegistry`.
  Administrators should register the required providers before the event.
- The DBA path needs a dedicated approved database, Entra administrator/identity
  mapping, and DNS/TLS connectivity from the MCP host to SQL. Azure RBAC does not
  grant SQL data-plane access. Keep the MCP identity in `sre_dba_observer`; never
  widen it to `db_owner` to bypass setup problems.
- Use isolated subscriptions or explicitly distinct Terraform resource names
  for each team and Coach reference lab. Default names collide if multiple
  independent states deploy into the same subscription.

### Check before you deploy

From the Linux terminal at the repository root:

```bash
git remote -v
# origin must point to your fork. Add upstream if it is not already present:
# git remote add upstream https://github.com/microsoft/frontier-sre-agent-rvas.git
cd Student
make preflight PREFLIGHT_ARGS=--local
az login                         # browser login
# Alternative for a remote/headless terminal: az login --use-device-code
az account set --subscription "<your-subscription-id>"
make preflight
# For the DBA track:
make preflight PREFLIGHT_TRACK=sql-dba
```

GitHub/Codespaces authentication does **not** authenticate Azure. Authenticate
inside the same Linux environment where you will run Terraform. Enable Issues
under your fork's **Settings → General → Features**.

`PASS` confirms the specific check, `FAIL` identifies a blocker, and `WARN`
requires manual review with your coach. Confirmed failures return a nonzero exit
and stop Make-based infrastructure deployment before Terraform init/apply.
Warnings do not certify readiness. Pre-flight never installs tools, registers
providers, changes roles, creates Network Watcher, or connects to your database.
`make validate`, `make validate-food`, and `make validate-parking` check
**post-deployment health**, not prerequisites.

Pass the same `TF_VARS` to pre-flight and deployment for regional/VM overrides.
Complex override sources such as `-var-file`, auto-loaded `.tfvars` files, and
`TF_CLI_ARGS` require manual profile verification;
the check warns instead of checking the wrong region. Quota on a rerun with
existing Terraform state is advisory: verify capacity for planned additions.

### Costs, state, and cleanup

Azure resources and Codespaces compute/storage have **separate costs**. Check
your Codespaces entitlement and organization policies before choosing it.
Stopping/deleting a Codespace does not remove Azure resources.

Keep the working directory, Terraform state, and your role-specific `.env`
private and intact. A normal container rebuild preserves the workspace, but
deleting a Codespace removes its local state. Before deletion, destroy your lab
or securely back up the Terraform state and configuration; never commit them or
share credentials. Lost state can cause conflicting deployment attempts.

Run `make destroy` from the same **Student** or **Coach** directory/state and with
the same deployment overrides. Student Terraform does not manage the manually
created SRE Agent: remove that agent and its dedicated resources separately when
finished. Never delete shared resource groups or another team's resources.

See [Azure Operations prerequisites](Student/Challenge-00.md) or
[SQL Server DBA prerequisites](Student/sql-server-dba/Challenge-00.md) next.

## Tracks

Choose a track based on the operational system you want Azure SRE Agent to
investigate:

| Track | Challenges | Focus |
|---|---:|---|
| [Azure Operations](#azure-operations-track) | 20 | Agent fundamentals, Azure observability, autonomous incident response, and FinOps |
| [SQL Server DBA](#sql-server-dba-track) | 10 | Read-only database discovery, Query Store, waits, blocking, query-performance diagnostics, and a build-your-own capstone |

Open `web/index.html` in a browser for the interactive UI (coach mode: **Shift+C**). See also the
[Scenario Explorer](web/scenarios.html) — a searchable library of 77 real-world Azure SRE Agent
scenario ideas with ready-to-use sample prompts, sourced from
[alsanch/azure-sre-agent-scenarios](https://github.com/alsanch/azure-sre-agent-scenarios).

### Azure Operations track

Twenty hands-on challenges with a progressive learning path: from agent
fundamentals through advanced autonomous operations and FinOps.

**Capability progression:** Knowledge → Skills → MCP → Subagents → Response Plans → Telemetry → Investigation → Incidents → GitHub → Code Analysis → Auto-Remediation → Scheduled Tasks → Executive Operations → FinOps

| # | Challenge | Capability |
|---|-----------|------------|
| [00](Student/Challenge-00.md) | Prerequisites & Lab Setup | Deploy infrastructure, configure agent |
| [01](Student/Challenge-01.md) | Connect Your Codebase | GitHub OAuth Connector · Repository Connection |
| [02](Student/Challenge-02.md) | Explore the Knowledge Base | Knowledge Bases · Grounded Responses |
| [03](Student/Challenge-03.md) | Discover Operational Skills | Skills · Operational Runbooks |
| [04](Student/Challenge-04.md) | Discover Connected Systems | MCP · Tool Discovery |
| [05](Student/Challenge-05.md) | Discover Specialist Agents | Subagents · Agent Routing |
| [06](Student/Challenge-06.md) | Understand Response Plans | Response Plans · Automation · Governance |
| [07](Student/Challenge-07.md) | Hybrid Ecosystem Telemetry | Log Analytics · Syslog · OpenTelemetry |
| [08](Student/Challenge-08.md) | Application Dependency Mapping | Service Dependency Analysis · App Topology |
| [09](Student/Challenge-09.md) | Daily Application Health Report | SLI/SLO · Operational Reporting |
| [10](Student/Challenge-10.md) | Incident to GitHub Issue | Incident Lifecycle · GitHub Integration |
| [11](Student/Challenge-11.md) | Guest OS Failure Investigation | Azure Monitor Agent · Syslog · VM Troubleshooting |
| [12](Student/Challenge-12.md) | Network Security Investigation | NSGs · Flow Logs · Network Forensics |
| [13](Student/Challenge-13.md) | Routing Failure Investigation | UDRs · Effective Routes · Next Hop |
| [14](Student/Challenge-14.md) | Application Root Cause Analysis | Telemetry Correlation · Source Code Analysis |
| [15](Student/Challenge-15.md) | Autonomous Remediation | Response Plans · Auto-remediation · Validation |
| [16](Student/Challenge-16.md) | Daily Network Health Report | Scheduled Tasks · Proactive Operations |
| [17](Student/Challenge-17.md) | Observability Freshness Verification | Monitoring the Monitoring · Coverage Analysis |
| [18](Student/Challenge-18.md) | Subscription Cost Optimization Review | FinOps · Azure Advisor · Cost Governance |
| [19](Student/Challenge-19.md) | Build Your Own Production-Ready SRE Agent | Capstone: design, implement & demo |

### SQL Server DBA track

Ten challenges use a dedicated, read-only SQL Server MCP server to turn Azure
SRE Agent into a database reliability specialist. The track moves from secure
deployment and schema orientation through deterministic performance incidents
to a build-your-own DBA agent capstone.

**Capability progression:** MCP trust boundary → Schema discovery → Query Store → Wait interpretation → Blocking → Index analysis → SARGability → Parameter sensitivity → Incident triage → Custom DBA agent capstone

| # | Challenge | Capability |
|---|-----------|------------|
| [00](Student/sql-server-dba/Challenge-00.md) | Deploy the Read-Only DBA Path | Managed identity · Least privilege · SQL Server MCP |
| [01](Student/sql-server-dba/Challenge-01.md) | Orient to the Database | Business domains · Schema · Relationships |
| [02](Student/sql-server-dba/Challenge-02.md) | Establish a Query Store Baseline | Historical evidence · Observation windows |
| [03](Student/sql-server-dba/Challenge-03.md) | Separate Duration from Pressure | Active requests · Wait interpretation |
| [04](Student/sql-server-dba/Challenge-04.md) | Trace a Blocking Chain | Head blocker · Wait resource · Transaction age |
| [05](Student/sql-server-dba/Challenge-05.md) | Build an Evidence-Based Index Case | Query Store · Existing indexes · Estimated plans |
| [06](Student/sql-server-dba/Challenge-06.md) | Diagnose Query Shape Problems | SARGability · Implicit conversion |
| [07](Student/sql-server-dba/Challenge-07.md) | Investigate Parameter Sensitivity | Data skew · Plan variation · Runtime distribution |
| [08](Student/sql-server-dba/Challenge-08.md) | Triage a Combined Database Incident | Evidence ranking · Alternative explanations · Handoff |
| [09](Student/sql-server-dba/Challenge-09.md) | Build Your Own SQL Server DBA Agent | Custom agent · Investigation design · Read-only validation |

The MCP server code, SQL setup, workloads, custom-agent assets, and secure
deployment guide are under
[`Student/Resources/sql-server-mcp/`](Student/Resources/sql-server-mcp/README.md).

**Coaches:** see [Coach/README.md](Coach/README.md) for the Azure Operations
guides and
[Coach/sql-server-dba/README.md](Coach/sql-server-dba/README.md) for the SQL
Server DBA guides.

## Contributors

Thanks to everyone who has contributed!

<a href="https://github.com/microsoft/frontier-sre-agent-rvas/graphs/contributors">
  <img src="https://contributors-img.web.app/image?repo=microsoft/frontier-sre-agent-rvas" />
</a>
