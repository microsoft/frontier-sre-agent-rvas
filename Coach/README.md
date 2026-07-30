**[Home](../README.md)**

> **COACHES ONLY — Do not share with participants.**

# Coach Index — Azure SRE Agent Workshop

Coach and facilitator guides for all 20 workshop challenges.

## Solution Index

| Challenge | Title | Solution File |
|---|---|---|
| 00 | Prerequisites: Deploy the Lab & Create Your SRE Agent | [Solution-00.md](./Solution-00.md) |
| 01 | Connect Your Codebase | [Solution-01.md](./Solution-01.md) |
| 02 | Explore the Knowledge Base | [Solution-02.md](./Solution-02.md) |
| 03 | Discover Operational Skills | [Solution-03.md](./Solution-03.md) |
| 04 | Discover Connected Systems | [Solution-04.md](./Solution-04.md) |
| 05 | Discover Specialist Agents | [Solution-05.md](./Solution-05.md) |
| 06 | Understand Response Plans | [Solution-06.md](./Solution-06.md) |
| 07 | Hybrid Ecosystem Telemetry | [Solution-07.md](./Solution-07.md) |
| 08 | Application Dependency Mapping | [Solution-08.md](./Solution-08.md) |
| 09 | Daily Application Health Report | [Solution-09.md](./Solution-09.md) |
| 10 | Incident to GitHub Issue | [Solution-10.md](./Solution-10.md) |
| 11 | Guest OS Failure Investigation | [Solution-11.md](./Solution-11.md) |
| 12 | Network Security Investigation | [Solution-12.md](./Solution-12.md) |
| 13 | Routing Failure Investigation | [Solution-13.md](./Solution-13.md) |
| 14 | Application Root Cause Analysis | [Solution-14.md](./Solution-14.md) |
| 15 | Autonomous Remediation | [Solution-15.md](./Solution-15.md) |
| 16 | Daily Network Health Report | [Solution-16.md](./Solution-16.md) |
| 17 | Observability Freshness Verification | [Solution-17.md](./Solution-17.md) |
| 18 | Subscription Cost Optimization Review | [Solution-18.md](./Solution-18.md) |
| 19 | Build Your Own Production-Ready SRE Agent | [Solution-19.md](./Solution-19.md) |

## Deployment Notes

- Student challenge files live in `../Student/Challenge-XX.md`.
- Coach guides live beside this index in `Solution-00.md` through `Solution-19.md`.
- Core config bundle is under `../Student/Resources/azure-sre-agent-config/`.
- The Berlin MCP connector used in Challenges 07 and 08 is deployed via Terraform and ships in the default config bundle.
- Some Parking Manager scenarios (especially Challenge 15) depend on the vm-health-control and chaos-control APIs. Use `make trigger-parking-down` / `make restore-parking` — see `Resources/scenarios/scripts/`.

## Azure Requirements

| Resource | Requirement |
|---|---|
| Azure subscription | Contributor access; resource providers: Microsoft.App, Microsoft.Network, Microsoft.Compute, Microsoft.OperationalInsights |
| Region | Any region that supports Azure Container Apps and Azure SRE Agent (Sweden Central recommended) |
| Quota | At least 8 vCPUs available in the target region (Standard_D2s_v3 or equivalent) |
| Terraform | v1.5+ with AzAPI provider |
| GitHub | Organization or personal account with OAuth app creation rights |

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

## Coaching Philosophy

1. **Don't give the answer — give the next question.** When a team is stuck, ask what the agent's last tool call returned, not what command they should run.
2. **Let the agent surprise them.** The most effective learning moments happen when the agent does something unexpected. Don't pre-warn teams about every capability.
3. **Enforce the coach discussion questions.** Every challenge has an "Explain to your coach" criterion. Hold teams to it — the conceptual discussion is as important as the working demo.
4. **Time-box fault scenarios.** Challenges 11–13 depend on alert propagation (2–15 min). Start the fault injection early and move to the next challenge's mini-lecture while waiting.
5. **The lab is the safety net.** All fault scenarios have a `make restore-*` command. If a team breaks something unexpected, `make restore-*` or `make validate` will return the lab to a known good state.
6. **Contributor permission is required.** Teams that set Reader permission in Challenge 00 will hit permission errors in Challenges 11–15. Catch this early.

## Per-Challenge Coach Guide

| Ch | Title | Key Concepts | Known Blockers | Est. Time | When to Intervene |
|---|---|---|---|---|---|
| 00 | Prerequisites | Terraform deploy, SRE Agent creation, resource group association | Slow Container Apps provisioning (~20 min); missing resource provider registration | **30–45 min** | If `make deploy` fails after 25 min |
| 01 | Connect Your Codebase | GitHub OAuth connector, repository link, governance boundary | OAuth authorization step missed in portal; connector applied but not authorized | **15 min** | If agent still can't read code after OAuth |
| 02 | Explore the Knowledge Base | RAG retrieval, knowledge grounding, hallucination baseline | Knowledge ingestion delay (~30 s); vague docs produce vague answers | **15–20 min** | If agent gives identical answer before/after knowledge upload |
| 03 | Discover Operational Skills | Skill YAMLs, tool grants, safety policies, boundary testing | `make skills` succeeds but skills not showing in portal (propagation delay) | **20 min** | If boundary test (delete rule) succeeds unexpectedly |
| 04 | Discover Connected Systems | MCP connectors, berlin-mcp, idempotent apply | Connector registered but not authorized; `make connectors` idempotency confusion | **10–15 min** | If Berlin MCP connector shows error in portal |
| 05 | Discover Specialist Agents | Subagent routing, /agent syntax, delegation chain | Subagent not found after `make subagents` (propagation); wrong agent name in prompt | **20 min** | If `/agent` routing returns main agent |
| 06 | Understand Response Plans | Incident filters, autonomous vs review mode, scheduled tasks | Quickstart filter conflict; incident platform not connected before filters applied | **25–30 min** | If alert fires but no routing after 5 min |
| 07 | Hybrid Ecosystem Telemetry | Log Analytics, Syslog, OpenTelemetry MCP, cross-platform | Madrid data window too narrow; Berlin MCP connector not re-applied after Ch04 | **20–25 min** | If Berlin MCP returns empty results |
| 08 | Application Dependency Mapping | Application map, OpenTelemetry traces, service topology | App Insights data lag; teams skip the "before" comparison | **25 min** | If topology shows only 1 node |
| 09 | Daily Application Health Report | SLI/SLO concepts, fleet reporting, scheduled tasks | Insufficient data window; teams stop at one API instead of the full fleet | **20 min** | If report covers fewer than 3 APIs |
| 10 | Incident to GitHub Issue | Incident lifecycle, GitHub MCP, issue template | GitHub connector not re-authorized; incident template not in knowledge base | **20 min** | If GitHub issue is created with no telemetry data |
| 11 | Guest OS Failure Investigation | Azure Monitor Agent, Syslog, VM run-command, blast radius | Alert takes 3–5 min; teams miss the second VM (partial blast radius) | **20–25 min** | If agent only restarts one VM |
| 12 | Network Security Investigation | NSG flow logs, Traffic Analytics (10 min lag), NSG rule delete | Flow log aggregation lag (10–15 min); teams trigger manual prompt too early | **20–25 min** | If agent names wrong NSG rule |
| 13 | Routing Failure Investigation | UDRs, effective routes, next-hop, asymmetric routing | Teams confuse IP forwarding with route pointing; agent finds NVA red herring | **25–30 min** | If agent deletes the wrong route |
| 14 | Application Root Cause Analysis | OOM crash, App Insights, source code correlation, GitHub issue | Food app not healthy before fault injection; GitHub connector not authorized | **25–30 min** | If agent stops at telemetry without reaching source code |
| 15 | Autonomous Remediation | Validated remediation, validation loop, retry, escalation | parking-vm-unhealthy filter not applied; permission error on az vm restart | **20–25 min** | If agent remediates without showing validation step |
| 16 | Daily Network Health Report | Scheduled tasks, proactive ops, Traffic Analytics reporting | < 24 h of flow log data; scheduled task not applied in Ch06 | **20 min** | If report shows no denied flows despite NSG test in Ch12 |
| 17 | Observability Freshness Verification | Telemetry pipeline health, ingestion lag, coverage gaps | DCR not collecting all facilities; teams mistake stale data for healthy data | **20 min** | If freshness check returns all green with no analysis |
| 18 | Subscription Cost Optimization Review | FinOps, Azure Advisor, Resource Graph, workload cost profiles | Cost Management access missing; teams skip knowledge-base grounding step | **25–30 min** | If recommendations ignore workload criticality |
| 19 | Build Your Own | Custom subagent, skill authoring, end-to-end test, presentation | Scope too broad; YAML syntax errors; missing knowledge doc | **45–60 min** | If team has no working demo after 40 min |
