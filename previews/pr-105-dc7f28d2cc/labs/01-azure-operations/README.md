# Azure Operations lab

Twenty challenges cover agent fundamentals, autonomous operations, and FinOps.

**Capability progression:** Knowledge → Skills → MCP → Subagents → Response Plans → Telemetry → Investigation → Incidents → GitHub → Code Analysis → Auto-Remediation → Scheduled Tasks → Executive Operations → FinOps

## Challenges

| # | Challenge | Capability |
|---|-----------|------------|
| [00](challenges/00-prerequisites-and-lab-setup.md) | Prerequisites & Lab Setup | Deploy infrastructure, configure agent |
| [01](challenges/01-connect-your-codebase.md) | Connect Your Codebase | GitHub OAuth Connector · Repository Connection |
| [02](challenges/02-explore-the-knowledge-base.md) | Explore the Knowledge Base | Knowledge Bases · Grounded Responses |
| [03](challenges/03-discover-operational-skills.md) | Discover Operational Skills | Skills · Operational Runbooks |
| [04](challenges/04-discover-connected-systems.md) | Discover Connected Systems | MCP · Tool Discovery |
| [05](challenges/05-discover-specialist-agents.md) | Discover Specialist Agents | Subagents · Agent Routing |
| [06](challenges/06-understand-response-plans.md) | Understand Response Plans | Response Plans · Automation · Governance |
| [07](challenges/07-hybrid-ecosystem-telemetry.md) | Hybrid Ecosystem Telemetry | Log Analytics · Syslog · OpenTelemetry |
| [08](challenges/08-application-dependency-mapping.md) | Application Dependency Mapping | Service Dependency Analysis · App Topology |
| [09](challenges/09-daily-application-health-report.md) | Daily Application Health Report | SLI/SLO · Operational Reporting |
| [10](challenges/10-incident-to-github-issue.md) | Incident to GitHub Issue | Incident Lifecycle · GitHub Integration |
| [11](challenges/11-guest-os-failure-investigation.md) | Guest OS Failure Investigation | Azure Monitor Agent · Syslog · VM Troubleshooting |
| [12](challenges/12-network-security-investigation.md) | Network Security Investigation | NSGs · Flow Logs · Network Forensics |
| [13](challenges/13-routing-failure-investigation.md) | Routing Failure Investigation | UDRs · Effective Routes · Next Hop |
| [14](challenges/14-application-root-cause-analysis.md) | Application Root Cause Analysis | Telemetry Correlation · Source Code Analysis |
| [15](challenges/15-autonomous-remediation.md) | Autonomous Remediation | Response Plans · Auto-remediation · Validation |
| [16](challenges/16-daily-network-health-report.md) | Daily Network Health Report | Scheduled Tasks · Proactive Operations |
| [17](challenges/17-observability-freshness-verification.md) | Observability Freshness Verification | Monitoring the Monitoring · Coverage Analysis |
| [18](challenges/18-subscription-cost-optimization-review.md) | Subscription Cost Optimization Review | FinOps · Azure Advisor · Cost Governance |
| [19](challenges/19-build-your-own-production-ready-sre-agent.md) | Build Your Own Production-Ready SRE Agent | Capstone: design, implement & demo |

## Requirements

Run every command in Linux Bash. Check the shared [requirements and environment setup](../../README.md#requirements) first, then work through challenge 00 to deploy and run the pre-flight checks.

## Deployment notes

- Core config bundle is under `../labs/01-azure-operations/resources/azure-sre-agent-config/`.
- The Berlin MCP connector used in Challenges 07 and 08 is deployed via Terraform and ships in the default config bundle.
- Challenge 10 uses `make trigger-parking-report` / `make restore-parking-report` to emit and clear synthetic `VMHealthStatus_CL` evidence. Challenge 15 uses `make trigger-parking-service-down` / `make restore-parking-service` for a real Paris API service outage.

## Before You Start: Environment Readiness

The shared [Requirements](../../README.md#requirements) are the source of truth
for tools and supported environments. Use **Codespaces on your own
fork**. Before you start, confirm policy, entitlement/billing, and a WSL2/Ubuntu
fallback. Run all Make commands in Linux Bash.

- Own your fork, enable Issues, and make sure you can authorize the
  GitHub connector. GitHub login is separate from Azure login.
- With the subscription owner, prepare provider registrations, regional Network
  Watcher, role-assignment permissions, and available family/regional quota.
- Isolate team deployments by subscription or by deliberately distinct
  resource names. Separate Terraform state does not prevent default-name collisions.
- Rebuild and verify the Dev Container before using it.
- Deploy only with zero pre-flight failures and after reviewing every warning.
  Pre-flight does not certify effective RBAC/Policy or live service capacity.
- Keep your private Terraform state and `.env` through the lab and cleanup.
  Never delete a Codespace while it holds the only copy of active state.

From the repository root in Linux Bash:

```bash
cd labs/01-azure-operations
make preflight PREFLIGHT_ARGS=--local
# Authenticate here and select the intended subscription.
az account show --query "{name:name,id:id,state:state}" -o table
make preflight
make infra
```

`make deploy` provisions workloads **only**. You create the agent manually in
Challenge 00 and configure it with the `make` targets from Challenge 01 onwards.
The `infra` target stops before Terraform init/apply on confirmed pre-flight
blockers. Use the same `TF_VARS` for pre-flight and deployment overrides.

To run the read-only pre-flight test suite, use this command from the repository root:
`bash labs/01-azure-operations/resources/infra/scripts/tests/preflight.test.sh`.
It uses fake Azure/Terraform responses and does not deploy the lab.

## Lab resources and access

| Resource | Requirement |
|---|---|
| Azure subscription | Resource creation plus role-assignment rights: Owner, or Contributor with appropriate RBAC administration rights. See shared Requirements for all providers. |
| Region | Any region that supports Azure Container Apps and Azure SRE Agent (Sweden Central recommended) |
| Quota | Default: 8 Standard_B2s_v2 VMs / 16 additional vCPUs, in both the applicable family and regional quotas; Madrid/Paris opt-outs remove 2 vCPUs each |
| Network Watcher | Existing NetworkWatcher_&lt;region&gt; in NetworkWatcherRG, for the actual Terraform region |
| Terraform | v1.5+ with AzAPI provider |
| GitHub | Your own fork, Issues enabled, and permission to authorize the lab's GitHub connector |

## Suggested Agenda

### Half-day format (4 hours)
| Time | Activity |
|---|---|
| 0:00–0:30 | Intro + Challenge 00 (deploy lab, create agent) |
| 0:30–1:00 | Challenges 01–03 (codebase, knowledge, skills) |
| 1:00–1:30 | Challenges 04–06 (connectors, subagents, response plans) |
| 1:30–2:30 | Challenges 07–10 (operational scenarios: telemetry, dependency, health, incident) |
| 2:30–3:30 | Challenges 11–14 (fault injection: VM, NSG, routing, root cause) |
| 3:30–4:00 | Challenge 15 + wrap-up (autonomous remediation + debrief) |

### Full-day format (8 hours)
| Time | Activity |
|---|---|
| 0:00–0:45 | Intro + Challenge 00 |
| 0:45–2:00 | Challenges 01–06 (agent configuration track) |
| 2:00–2:15 | Break |
| 2:15–4:00 | Challenges 07–10 (observability and incident track) |
| 4:00–4:45 | Lunch |
| 4:45–6:30 | Challenges 11–15 (fault injection and remediation track) |
| 6:30–7:00 | Challenges 16–18 (proactive operations track) |
| 7:00–8:00 | Challenge 19 (capstone: build your own) |

## Working principles

1. **Ask yourself guiding questions.** When you're stuck, check what the agent's last tool call returned before looking for the next command.
2. **Explore.** Don't try to learn every capability in advance. Treat unexpected agent behavior as something to investigate.
3. **Explain what you built.** Every challenge has an "Explain in your own words" criterion. Check your understanding as well as the working demo.
4. **Time-box fault scenarios.** Challenges 11–13 depend on alert propagation (2–15 min). Start the fault injection early and read the next challenge's background notes while waiting.
5. **Restore and verify after faults.** All fault scenarios have a `make restore-*` command. Use the matching command to reverse an injected fault, then run `make validate` to check health. An unexpected failure may need separate diagnosis.
6. **Separate approval from authorization.** Contributor is the simplest baseline for the whole lab because NSG and UDR challenges require broader writes. If only VM Run Command or restart is denied, an Owner or Role Based Access Control Administrator can run `make grant-agent-vm-remediation` to add the narrow VM role without replacing existing assignments.

## Per-challenge guide

| Ch | Title | Key Concepts | Known Blockers | Est. Time | Get Unstuck If |
|---|---|---|---|---|---|
| 00 | Prerequisites | Linux environment, pre-flight, Terraform deploy, SRE Agent creation, resource group association | Missing tools; wrong shell/subscription; Network Watcher/provider/quota blockers | **30–45 min** | Before deployment if pre-flight fails or warnings have not been reviewed |
| 01 | Connect Your Codebase | GitHub OAuth connector, repository link, governance boundary | OAuth authorization step missed in portal; connector applied but not authorized | **15 min** | If agent still can't read code after OAuth |
| 02 | Explore the Knowledge Base | RAG retrieval, knowledge grounding, hallucination baseline | Knowledge ingestion delay (~30 s); vague docs produce vague answers | **15–20 min** | If agent gives identical answer before/after knowledge upload |
| 03 | Discover Operational Skills | Skill YAMLs, tool grants, safety policies, boundary testing | `make skills` succeeds but skills not showing in portal (propagation delay) | **20 min** | If boundary test (delete rule) succeeds unexpectedly |
| 04 | Discover Connected Systems | MCP connectors, Microsoft Learn MCP, focused deployment | Learn connector missing after setup; `make connectors` used instead of `make connectors-learn` | **10–15 min** | If Microsoft Learn tools are unavailable after deployment |
| 05 | Discover Specialist Agents | Subagent routing, /agent syntax, delegation chain | Subagent not found after `make subagents` (propagation); wrong agent name in prompt | **20 min** | If `/agent` routing returns main agent |
| 06 | Understand Response Plans | Azure Monitor incident platform, incident filters, autonomous vs review mode, scheduled tasks | `make incident-platforms` skipped; quickstart filter conflict | **25–30 min** | If Azure Monitor is connected but an alert still has no routing after 5 min |
| 07 | Hybrid Ecosystem Telemetry | Log Analytics, Syslog, OpenTelemetry MCP, cross-platform | Madrid data window too narrow; Berlin MCP connector not re-applied after Ch04 | **20–25 min** | If Berlin MCP returns empty results |
| 08 | Application Dependency Mapping | Application map, OpenTelemetry traces, service topology | App Insights data lag; skipping the "before" comparison | **25 min** | If topology shows only 1 node |
| 09 | Daily Application Health Report | SLI/SLO concepts, fleet reporting, scheduled tasks | Insufficient data window; stopping at one API instead of the full fleet | **20 min** | If report covers fewer than 3 APIs |
| 10 | Incident to GitHub Issue | Incident lifecycle, GitHub MCP, issue template | GitHub connector not re-authorized; incident template not in knowledge base | **20 min** | If GitHub issue is created with no telemetry data |
| 11 | Guest OS Failure Investigation | Azure Monitor Agent, Syslog, VM run-command, blast radius | Alert takes 3–5 min; missing the second VM (partial blast radius) | **20–25 min** | If agent only restarts one VM |
| 12 | Network Security Investigation | NSG flow logs, Traffic Analytics (10 min lag), NSG rule delete | Flow log aggregation lag (10–15 min); triggering the manual prompt too early | **20–25 min** | If agent names wrong NSG rule |
| 13 | Routing Failure Investigation | UDRs, effective routes, next-hop, asymmetric routing | Confusing IP forwarding with route pointing; agent finds NVA red herring | **25–30 min** | If agent deletes the wrong route |
| 14 | Application Root Cause Analysis | OOM crash, App Insights, source code correlation, GitHub issue | Food app not healthy before fault injection; GitHub connector not authorized | **25–30 min** | If agent stops at telemetry without reaching source code |
| 15 | Autonomous Remediation | Validated remediation, validation loop, retry, escalation | parking-api-service-down filter not applied; permission error on az vm restart | **20–25 min** | If agent remediates without showing validation step |
| 16 | Daily Network Health Report | Scheduled tasks, proactive ops, Traffic Analytics reporting | < 24 h of flow log data; scheduled task not applied in Ch06 | **20 min** | If report shows no denied flows despite NSG test in Ch12 |
| 17 | Observability Freshness Verification | Telemetry pipeline health, ingestion lag, coverage gaps | DCR not collecting all facilities; mistaking stale data for healthy data | **20 min** | If freshness check returns all green with no analysis |
| 18 | Subscription Cost Optimization Review | FinOps, Azure Advisor, Resource Graph, workload cost profiles | Cost Management access missing; skipping the knowledge-base grounding step | **25–30 min** | If recommendations ignore workload criticality |
| 19 | Build Your Own | Custom subagent, skill authoring, end-to-end test, presentation | Scope too broad; YAML syntax errors; missing knowledge doc | **45–60 min** | If you have no working demo after 40 min |
