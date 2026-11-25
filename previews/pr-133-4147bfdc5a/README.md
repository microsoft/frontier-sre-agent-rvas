# Frontier Azure SRE Agent Solution

## Introduction

Build and test Azure SRE Agent capabilities in hands-on labs. Use the tools, runbooks, and automation here to investigate Azure workloads, respond to incidents, and review costs.

## Tracks

Choose the track that matches the system you want Azure SRE Agent to
investigate:

| Track | Challenges | Focus |
|---|---:|---|
| [Azure Operations](#azure-operations-track) | 20 | Agent fundamentals, Azure observability, autonomous incident response, and FinOps |
| [SQL Server DBA](#sql-server-dba-track) | 10 | Read-only database discovery, Query Store, waits, blocking, query-performance diagnostics, and a build-your-own capstone |

Open `web/index.html` in a browser for the [Scenario Explorer](web/index.html), a searchable library of Azure SRE Agent use cases, from ideas to built agents, generated from the folders in [usecases/](usecases/README.md). The labs are in `web/labs.html`. To add one, run
`usecases/_framework/usecases.sh new <domain> <slug>`, fill in the files, then run `usecases/_framework/usecases.sh validate`.
The ideas come from
[alsanch/azure-sre-agent-scenarios](https://github.com/alsanch/azure-sre-agent-scenarios).

### Azure Operations track

Twenty challenges cover agent fundamentals, autonomous operations, and FinOps.

**Capability progression:** Knowledge → Skills → MCP → Subagents → Response Plans → Telemetry → Investigation → Incidents → GitHub → Code Analysis → Auto-Remediation → Scheduled Tasks → Executive Operations → FinOps

| # | Challenge | Capability |
|---|-----------|------------|
| [00](labs/01-azure-operations/challenges/00-prerequisites-and-lab-setup.md) | Prerequisites & Lab Setup | Deploy infrastructure, configure agent |
| [01](labs/01-azure-operations/challenges/01-connect-your-codebase.md) | Connect Your Codebase | GitHub OAuth Connector · Repository Connection |
| [02](labs/01-azure-operations/challenges/02-explore-the-knowledge-base.md) | Explore the Knowledge Base | Knowledge Bases · Grounded Responses |
| [03](labs/01-azure-operations/challenges/03-discover-operational-skills.md) | Discover Operational Skills | Skills · Operational Runbooks |
| [04](labs/01-azure-operations/challenges/04-discover-connected-systems.md) | Discover Connected Systems | MCP · Tool Discovery |
| [05](labs/01-azure-operations/challenges/05-discover-specialist-agents.md) | Discover Specialist Agents | Subagents · Agent Routing |
| [06](labs/01-azure-operations/challenges/06-understand-response-plans.md) | Understand Response Plans | Response Plans · Automation · Governance |
| [07](labs/01-azure-operations/challenges/07-hybrid-ecosystem-telemetry.md) | Hybrid Ecosystem Telemetry | Log Analytics · Syslog · OpenTelemetry |
| [08](labs/01-azure-operations/challenges/08-application-dependency-mapping.md) | Application Dependency Mapping | Service Dependency Analysis · App Topology |
| [09](labs/01-azure-operations/challenges/09-daily-application-health-report.md) | Daily Application Health Report | SLI/SLO · Operational Reporting |
| [10](labs/01-azure-operations/challenges/10-incident-to-github-issue.md) | Incident to GitHub Issue | Incident Lifecycle · GitHub Integration |
| [11](labs/01-azure-operations/challenges/11-guest-os-failure-investigation.md) | Guest OS Failure Investigation | Azure Monitor Agent · Syslog · VM Troubleshooting |
| [12](labs/01-azure-operations/challenges/12-network-security-investigation.md) | Network Security Investigation | NSGs · Flow Logs · Network Forensics |
| [13](labs/01-azure-operations/challenges/13-routing-failure-investigation.md) | Routing Failure Investigation | UDRs · Effective Routes · Next Hop |
| [14](labs/01-azure-operations/challenges/14-application-root-cause-analysis.md) | Application Root Cause Analysis | Telemetry Correlation · Source Code Analysis |
| [15](labs/01-azure-operations/challenges/15-autonomous-remediation.md) | Autonomous Remediation | Response Plans · Auto-remediation · Validation |
| [16](labs/01-azure-operations/challenges/16-daily-network-health-report.md) | Daily Network Health Report | Scheduled Tasks · Proactive Operations |
| [17](labs/01-azure-operations/challenges/17-observability-freshness-verification.md) | Observability Freshness Verification | Monitoring the Monitoring · Coverage Analysis |
| [18](labs/01-azure-operations/challenges/18-subscription-cost-optimization-review.md) | Subscription Cost Optimization Review | FinOps · Azure Advisor · Cost Governance |
| [19](labs/01-azure-operations/challenges/19-build-your-own-production-ready-sre-agent.md) | Build Your Own Production-Ready SRE Agent | Capstone: design, implement & demo |

### SQL Server DBA track

Ten challenges use a dedicated, read-only SQL Server MCP server for database
investigation. You deploy it securely, explore the schema, diagnose repeatable
performance incidents, and build your own DBA agent.

**Capability progression:** MCP trust boundary → Schema discovery → Query Store → Wait interpretation → Blocking → Index analysis → SARGability → Parameter sensitivity → Incident triage → Custom DBA agent capstone

| # | Challenge | Capability |
|---|-----------|------------|
| [00](labs/02-sql-server-dba/challenges/00-deploy-the-read-only-dba-path.md) | Deploy the Read-Only DBA Path | Managed identity · Least privilege · SQL Server MCP |
| [01](labs/02-sql-server-dba/challenges/01-orient-to-the-database.md) | Orient to the Database | Business domains · Schema · Relationships |
| [02](labs/02-sql-server-dba/challenges/02-establish-a-query-store-baseline.md) | Establish a Query Store Baseline | Historical evidence · Observation windows |
| [03](labs/02-sql-server-dba/challenges/03-separate-duration-from-pressure.md) | Separate Duration from Pressure | Active requests · Wait interpretation |
| [04](labs/02-sql-server-dba/challenges/04-trace-a-blocking-chain.md) | Trace a Blocking Chain | Head blocker · Wait resource · Transaction age |
| [05](labs/02-sql-server-dba/challenges/05-build-an-evidence-based-index-case.md) | Build an Evidence-Based Index Case | Query Store · Existing indexes · Estimated plans |
| [06](labs/02-sql-server-dba/challenges/06-diagnose-query-shape-problems.md) | Diagnose Query Shape Problems | SARGability · Implicit conversion |
| [07](labs/02-sql-server-dba/challenges/07-investigate-parameter-sensitivity.md) | Investigate Parameter Sensitivity | Data skew · Plan variation · Runtime distribution |
| [08](labs/02-sql-server-dba/challenges/08-triage-a-combined-database-incident.md) | Triage a Combined Database Incident | Evidence ranking · Alternative explanations · Handoff |
| [09](labs/02-sql-server-dba/challenges/09-build-your-own-sql-server-dba-agent.md) | Build Your Own SQL Server DBA Agent | Custom agent · Investigation design · Read-only validation |

The MCP server code, SQL setup, workloads, custom-agent assets, and secure
deployment guide are under
[`labs/02-sql-server-dba/resources/sql-server-mcp/`](labs/02-sql-server-dba/resources/sql-server-mcp/README.md).

**Labs:** see [labs/01-azure-operations/README.md](labs/01-azure-operations/README.md) for the Azure Operations
guides and
[labs/02-sql-server-dba/README.md](labs/02-sql-server-dba/README.md) for the SQL
Server DBA guides.

## Requirements

**Run all lab commands in Linux Bash.** Use the supplied Dev Container in
**GitHub Codespaces on your own fork** (recommended), WSL2 with Ubuntu, a local
Linux Dev Container, or native Ubuntu. The lab automation uses Bash, GNU Make,
GNU utilities, and Linux paths, so native PowerShell, CMD, Git Bash, and macOS
shells are not supported.

### Choose your environment

| Environment | What you need | Getting started |
|---|---|---|
| **GitHub Codespaces (recommended)** | GitHub account, permission to fork, Codespaces access and available quota/billing, browser | Fork this repository, then on **your fork** choose **Code → Codespaces → Create codespace**. The repository is already checked out; do not clone it again. Wait for container setup and local pre-flight checks to finish. |
| **WSL2 / Ubuntu** | Windows with WSL2, Ubuntu, and tools installed **inside Ubuntu** | Follow the [WSL environment guide](https://learn.microsoft.com/windows/wsl/setup/environment). Clone your fork under your Linux home directory (for example `~/src`), not `/mnt/c`. Open VS Code from Ubuntu using `code .` and confirm the window is connected to WSL. |
| **Local Linux Dev Container** | VS Code, Dev Containers extension, and a running Docker-compatible host; Windows hosts use WSL2/Linux containers | Clone your fork and choose **Dev Containers: Reopen in Container**. Run commands in the container terminal, not the host terminal. macOS users should use this Linux container path. |
| **Native Ubuntu** | Ubuntu and the tools below | Clone your fork and install/verify the common tools before deployment. |

Codespaces does **not** require Docker or Terraform on your laptop.
Container setup installs tools but does not log in to Azure, deploy resources,
create an agent, or configure its capabilities. If setup fails, read the
creation log and fix the reported dependency failure before continuing. After
changing the container configuration, use **Codespaces: Rebuild Container** or
**Dev Containers: Rebuild Container**.

### Tools and accounts

| Requirement | Common / Azure Operations | SQL Server DBA additions |
|---|---|---|
| Linux tooling | Bash 4+, GNU Make, Git, GNU coreutils/findutils, `curl`, `jq`, `envsubst` (gettext), Python 3 | Microsoft ODBC `sqlcmd` with the approved Entra authentication method |
| YAML parsing | Python 3 with PyYAML (recommended), or **Mike Farah yq** supporting `yq -o=json`; other tools named `yq` are not interchangeable | Same |
| Terraform | **1.5+** for Make-based lab deployment | Needed for the Make-based lab deployments |
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
  Administrators should register the required providers before the lab.
- The DBA path needs a dedicated approved database, Entra administrator/identity
  mapping, and DNS/TLS connectivity from the MCP host to SQL. Azure RBAC does not
  grant SQL data-plane access. Keep the MCP identity in `sre_dba_observer`; never
  widen it to `db_owner` to bypass setup problems.
- Use isolated subscriptions or explicitly distinct Terraform resource names
  for each team and each lab. Default names collide if multiple
  independent states deploy into the same subscription.

### Check before you deploy

From the Linux terminal at the repository root:

```bash
git remote -v
# origin must point to your fork. Add upstream if it is not already present:
# git remote add upstream https://github.com/microsoft/frontier-sre-agent-rvas.git
cd labs/01-azure-operations
make preflight PREFLIGHT_ARGS=--local
az login                         # browser login
# Alternative for a remote/headless terminal: az login --use-device-code
az account set --subscription "<your-subscription-id>"
make preflight
# For the DBA track:
make preflight PREFLIGHT_TRACK=sql-dba
```

GitHub/Codespaces authentication does **not** authenticate Azure. Log in to
Azure in the same Linux environment where you will run Terraform. Enable Issues
under your fork's **Settings → General → Features**.

`PASS` confirms the check, `FAIL` identifies a blocker, and `WARN`
needs manual review. A confirmed failure returns a nonzero exit
and stops Make-based infrastructure deployment before Terraform init/apply.
Warnings do not certify readiness. Pre-flight never installs tools, registers
providers, changes roles, creates Network Watcher, or connects to your database.
`make validate`, `make validate-food`, and `make validate-parking` check
**post-deployment health**, not prerequisites.

Pass the same `TF_VARS` to pre-flight and deployment for regional/VM overrides.
Pre-flight can't evaluate complex override sources such as `-var-file`,
auto-loaded `.tfvars` files, and `TF_CLI_ARGS`. It warns instead of checking
the wrong region, so verify the profile manually. Quota on a rerun with
existing Terraform state is advisory: verify capacity for planned additions.

### Costs, state, and cleanup

Azure resources and Codespaces compute/storage have **separate costs**. Check
your Codespaces entitlement and organization policies before choosing it.
Stopping or deleting a Codespace does not remove Azure resources.

Keep the working directory, Terraform state, and your role-specific `.env`
private and intact. A normal container rebuild preserves the workspace, but
deleting a Codespace removes its local state. Before deleting, destroy your lab
or securely back up the Terraform state and configuration. Never commit them or
share credentials. Lost state can cause conflicting deployment attempts.

Run `make destroy` from the same lab directory and state, with
the same deployment overrides. The lab Terraform does not manage the manually
created SRE Agent, so remove that agent and its dedicated resources separately.
Never delete shared resource groups or another team's resources.

See [Azure Operations prerequisites](labs/01-azure-operations/challenges/00-prerequisites-and-lab-setup.md) or
[SQL Server DBA prerequisites](labs/02-sql-server-dba/challenges/00-deploy-the-read-only-dba-path.md) next.

## Contributors

Thanks to everyone who has contributed!

<a href="https://github.com/microsoft/frontier-sre-agent-rvas/graphs/contributors">
  <img src="https://contributors-img.web.app/image?repo=microsoft/frontier-sre-agent-rvas" />
</a>
