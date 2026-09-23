# Frontier Azure SRE Agent Solution

## Introduction

The Frontier Azure SRE Agent Solution is a comprehensive framework designed to enhance the reliability, scalability, and performance of applications deployed on Microsoft Azure. This solution provides a set of tools, best practices, and automation scripts that enable Site Reliability Engineers (SREs) to effectively monitor, manage, and optimize their cloud infrastructure using Azure SRE agent.

## Tracks

Choose a track based on the operational system you want Azure SRE Agent to
investigate:

| Track | Challenges | Focus |
|---|---:|---|
| [Azure Operations](#azure-operations-track) | 20 | Agent fundamentals, Azure observability, autonomous incident response, and FinOps |
| [SQL Server DBA](#sql-server-dba-track) | 9 | Read-only database discovery, Query Store, waits, blocking, and query-performance diagnostics |

Open `web/index.html` in a browser for the interactive UI (coach mode: **Shift+C**).

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

Nine challenges use a dedicated, read-only SQL Server MCP server to turn Azure
SRE Agent into a database reliability specialist. The track moves from secure
deployment and schema orientation to deterministic performance incidents.

**Capability progression:** MCP trust boundary → Schema discovery → Query Store → Wait interpretation → Blocking → Index analysis → SARGability → Parameter sensitivity → Incident triage

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
