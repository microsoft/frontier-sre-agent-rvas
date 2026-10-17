# Azure SRE Agent - Capability Briefing Notes

> COACHES ONLY - Use this as the customer talk track for the SignalOps capability briefing. Open Capabilities from the SignalOps site navigation.

## Briefing Links

| Destination | Link |
|---|---|
| SRE SignalOps missions | [Explore the missions](../Missions/README.md) |
| Environment setup | [SignalOps deployment](../Deployment/README.md) |
| Application and architecture | [Understand Grubify](../Lab-Details.md) |
| Product documentation | [Microsoft Learn - Azure SRE Agent overview](https://learn.microsoft.com/en-us/azure/sre-agent/overview) |

## Opening

### Say

> Azure SRE Agent is an AI-powered operations teammate. It brings together operational evidence, investigates incidents, recommends or performs governed actions, automates routine work, and preserves knowledge.

### Core Message

The goal is to move from scattered signals and reactive firefighting to faster, evidence-led, governed recovery.

## Hero Scenario - From Scattered Signals to Assured Recovery

The opening visual uses a fictional live incident to establish the story before introducing the capabilities.

### What the Page Shows

| Incident detail | Value |
|---|---|
| Incident | `INC-2471 - CHECKOUT API` |
| Status | Live, SEV 1 |
| Time | 14:03 UTC |
| Symptom | Latency breached its SLO |
| Observed latency | 2.8 seconds |
| Relevant change | Deployment at 13:21 |

The illustrative investigation has already:

1. Correlated four telemetry sources in six seconds.
2. Linked deployment `a84f1c` in eleven seconds.
3. Started testing a root-cause hypothesis.

The investigation is illustrative, but the key principle is real: **the evidence remains inspectable**.

### Four Ideas to Establish

1. **See the whole system:** Bring together logs, metrics, traces, and changes.
2. **Reason across evidence:** Test hypotheses before recommending mitigation.
3. **Act inside guardrails:** Use Review or Autonomous mode within configured permissions and policies.
4. **Learn from recovery:** Retain verified context so operational knowledge compounds over time.

### Hero Talk Track

> A latency alert by itself tells us the symptom, not the cause. Here the agent correlates four telemetry sources, links a recent deployment, and tests whether that change explains the SLO breach. The engineer can inspect the evidence before any mitigation is selected. That pattern - observe, reason, act with control, and learn - drives the entire page.

## 1. Monitor and Detect

### What It Does

Correlates alerts, logs, metrics, traces, deployments, and configuration changes into one view of system health.

### Situation

Checkout errors, latency, and dependency failures trigger separate alerts. The on-call engineer sees noise rather than one coherent incident.

### Explain

- Engineers often receive many disconnected alerts for one incident.
- The agent aligns those signals on a common timeline.
- It converts alert noise into a coherent incident picture.
- Its conclusions remain linked to inspectable evidence.

### Example Prompt

> Show me what changed before checkout latency breached its SLO.

### Evidence Flow

| Stage | Evidence | Meaning |
|---|---|---|
| 1 | Alerts | Symptoms |
| 2 | Telemetry | Logs, metrics, and traces |
| 3 | Changes | Deployments and configuration |
| 4 | Correlated signal | Incident context |

Unified telemetry becomes an actionable incident.

### How the Agent Moves

1. Collects permitted telemetry from connected sources.
2. Aligns signals to the incident timeline.
3. Correlates anomalies, dependencies, and changes.
4. Presents a grounded summary with evidence links.

### Engineer Control

The engineer defines the managed scope, connector access, identity permissions, and which evidence sources the agent may query.

### Why It Matters

**Less alert noise. Faster orientation.** The engineer begins with a coherent incident picture instead of manually stitching together dashboards.

## 2. Find Root Cause

### What It Does

Generates possible causes and tests each hypothesis against available evidence.

### Situation

Memory begins climbing before an alert. A release occurred two hours earlier, but dozens of services and changes fall inside the same window.

### Explain

- The agent builds an incident timeline.
- It examines dependencies, deployments, configurations, and previous patterns.
- It finds evidence that supports or disproves each hypothesis.
- It ranks probable causes and clearly exposes uncertainty.

### Example Prompt

> What is the most likely cause, and what evidence disproves the alternatives?

### Evidence Flow

| Stage | Evidence | Meaning |
|---|---|---|
| 1 | Symptom | Memory pressure |
| 2 | Dependency graph | Service relationships |
| 3 | Change history | Commit and deployment |
| 4 | Probable cause | Evidence cited |

Hypotheses are tested, ranked, and cited.

### How the Agent Moves

1. Builds an incident timeline from available signals.
2. Generates plausible failure hypotheses.
3. Queries evidence that supports or rejects each hypothesis.
4. Ranks the probable cause and exposes uncertainty.

### Engineer Control

An engineer can challenge the hypothesis, inspect citations, and request a deeper investigation before action.

### Why It Matters

**Hours of log trawling become a focused investigation.** Hypothesis-driven diagnosis helps lower mean time to recovery while preserving an evidence trail.

## 3. Respond Safely

### What It Does

Recommends and executes mitigations within identity, RBAC, policy, and approval boundaries.

### Situation

The likely fix is a pod restart or scaling adjustment. Speed matters, but an unreviewed write action could increase the impact.

### Explain

- The agent selects the lowest-risk mitigation for the probable cause.
- It validates permissions and prerequisites before acting.
- Review mode pauses actions that require approval.
- Autonomous mode still operates only within assigned permissions and policies.
- After acting, the agent verifies service health and records the result.

### Example Prompt

> Propose the lowest-risk mitigation, validate prerequisites, and wait for approval.

### Evidence Flow

| Stage | Evidence or gate | Meaning |
|---|---|---|
| 1 | Mitigation | Evidence-backed proposal |
| 2 | Identity and RBAC | Permission check |
| 3 | Policy gate | Allow, ask, or deny |
| 4 | Verified recovery | Health rechecked |

Every action crosses a governance boundary.

### How the Agent Moves

1. Selects a mitigation that addresses the probable cause.
2. Checks managed identity, RBAC, and tool policy.
3. Routes write actions through Review or Autonomous mode.
4. Executes, verifies service health, and records the result.

### Engineer Control

Review mode pauses approval-required actions. Autonomous mode still operates only within assigned permissions and policies.

### Why It Matters

**Faster recovery without bypassing ownership.** Governance sits directly in the execution path, with auditable actions and explicit boundaries.

## 4. Automate Toil

### What It Does

Turns repeatable operational work into scheduled or event-driven workflows.

### Situation

Health checks, compliance sweeps, cleanup, and protection reviews lose time to urgent delivery work and inconsistent handoffs.

### Explain

- Work can start from an alert, event, or schedule.
- Teams define the instructions, scope, tools, and expected outcome.
- The agent runs health checks, compliance reviews, cleanup, and other routine operations.
- Results and escalations are published into the team's existing workflow.

### Example Prompt

> Every weekday at 07:00, validate health, backup coverage, and open reliability risks.

### Evidence Flow

| Stage | Component | Meaning |
|---|---|---|
| 1 | Trigger | Alert, event, or schedule |
| 2 | Instructions | Task or response plan |
| 3 | Focused agent | Permitted tools and context |
| 4 | Team workflow | Result and escalation |

Schedules and events trigger focused work.

### How the Agent Moves

1. Uses a defined trigger, scope, and expected outcome.
2. Applies focused instructions and permitted tools.
3. Runs repeatable checks or approved operations.
4. Publishes results to the configured channel.

### Engineer Control

Teams choose the schedule, instructions, custom agent, tools, and action mode. Hooks can add policy checkpoints.

### Why It Matters

**Continuous automation returns engineering capacity.** Routine work becomes consistent and visible instead of depending on someone remembering it.

## 5. Optimize Proactively

### What It Does

Finds reliability, performance, scaling, security, governance, and cost improvements before incidents occur.

### Situation

The service is healthy, yet it is over-provisioned, has a single-region dependency, and carries a slow scaling rule.

### Explain

- The agent examines utilization, topology, configuration, and health.
- It identifies waste, bottlenecks, slow scaling, and single points of failure.
- Recommendations balance reliability, cost, security, and performance.
- Improvements are prioritized by impact, risk, and effort.

### Example Prompt

> Rank the top reliability, performance, and cost improvements by risk and effort.

### Evidence Flow

| Stage | Analysis | Meaning |
|---|---|---|
| 1 | Estate scan | Usage, policy, and topology |
| 2 | Pattern analysis | Risk and inefficiency |
| 3 | Prioritized plan | Impact balanced against effort |
| 4 | Improvement | Implement and measure again |

Evidence becomes prioritized improvement.

### How the Agent Moves

1. Inspects utilization, configuration, topology, and health.
2. Identifies waste, bottlenecks, and failure points.
3. Balances reliability, cost, security, and performance.
4. Recommends prioritized actions with evidence.

### Engineer Control

Teams validate business constraints and the available evidence before implementing recommendations.

### Why It Matters

**Shift from react-and-repair to prevent-and-improve.** Optimization becomes an ongoing reliability discipline rather than periodic cleanup.

## 6. Connect the Ecosystem

### What It Does

Connects operational context across the tools teams already use.

### Situation

The alert is in Azure Monitor, code lives in GitHub, the incident is in ServiceNow, and the team coordinates in Teams.

### Explain

- Telemetry may be in Azure Monitor, Application Insights, and Log Analytics.
- Code and deployments may be in GitHub or Azure DevOps.
- Incidents may be managed through Azure Alerts, ServiceNow, or PagerDuty.
- Collaboration and approvals may happen in Teams or Outlook.
- The agent brings relevant context into one investigation without requiring a tool migration.
- Connectors expose only configured systems and permitted operations.

### Example Prompt

> Investigate across telemetry, source changes, and the active incident ticket.

### Evidence Flow

| Stage | System area | Examples |
|---|---|---|
| 1 | Observe | Azure and partner tools |
| 2 | Change | GitHub and Azure DevOps |
| 3 | Coordinate | Alerts and IT service management |
| 4 | Collaborate | Teams and Outlook |

Context travels across the existing toolchain.

### How the Agent Moves

1. Connects supported systems with scoped authentication.
2. Retrieves context relevant to the investigation.
3. Correlates evidence without forcing a tool migration.
4. Updates the existing incident workflow.

### Engineer Control

Native, managed, and MCP connectors expose only configured systems and permitted operations.

### Why It Matters

**One investigation thread. Fewer context switches.** Connect the tools teams trust instead of asking them to abandon established workflows.

## 7. Retain Knowledge

### What It Does

Converts verified incident findings and resolutions into reusable operational knowledge.

### Situation

A recurring failure was solved at 02:00, but the reasoning is buried in a closed ticket and the next engineer starts from zero.

### Explain

- The agent captures the evidence, decisions, root cause, and observed outcome.
- It distinguishes verified resolutions from untested suggestions.
- Recurring patterns become reusable insights.
- Relevant history is surfaced during future investigations.
- Engineers still validate retained context before applying it.

### Example Prompt

> Have we seen this pattern before, and what resolution was verified?

### Evidence Flow

| Stage | Knowledge | Meaning |
|---|---|---|
| 1 | Investigation | Evidence and decision |
| 2 | Verified lesson | Cause and resolution |
| 3 | Shared context | Pattern retained |
| 4 | Next incident | Better starting point |

Resolved incidents become reusable context.

### How the Agent Moves

1. Captures investigation context and the observed outcome.
2. Separates verified resolution from suggestion.
3. Generates reusable insights from recurring patterns.
4. Surfaces relevant context in future investigations.

### Engineer Control

Teams decide which sources and operational knowledge are connected. Retained context still requires validation.

### Why It Matters

**Institutional knowledge becomes an operational asset.** New and rotating engineers inherit context instead of depending on undocumented memory.

## The Continuous Reliability Loop

### Main Message

> Every recovery improves the next response.

The five stages describe how the capabilities work together during an incident. This is a continuous loop, not a one-time sequence. What the team verifies during one recovery becomes useful context for the next investigation.

### 1. Monitor - Unify Telemetry and Context

- Bring together logs, metrics, traces, alerts, topology, deployments, and configuration changes.
- Establish a current picture of application and infrastructure health.
- Keep the evidence connected to its source so engineers can inspect it.

**How to explain it:** Monitoring tells us what the system is doing and what changed around the same time.

### 2. Detect - Turn Noise into an Incident

- Correlate related symptoms that may arrive as separate alerts.
- Distinguish meaningful service impact from isolated telemetry noise.
- Create one incident context with an affected service, timeline, and severity.

**How to explain it:** Detection turns many individual signals into one operational problem that the team can investigate.

### 3. Diagnose - Test Grounded Hypotheses

- Generate plausible explanations for the observed symptoms.
- Test each explanation against telemetry, dependencies, and recent changes.
- Rank the probable causes, cite supporting evidence, and expose uncertainty.

**How to explain it:** Diagnosis is not simply an AI guess. The agent tests possible causes and shows why one explanation is stronger than the alternatives.

### 4. Remediate - Act Within Policy Boundaries

- Recommend the lowest-risk action that addresses the probable cause.
- Check identity, RBAC, tool permissions, and approval requirements.
- Execute only when policy permits, then verify that service health recovers.
- Record the action and outcome for auditability.

**How to explain it:** Remediation combines speed with control. The agent can assist or act, but only inside the boundaries the organization defines.

### 5. Learn - Retain Verified Context

- Capture the verified cause, successful action, and observed recovery.
- Separate confirmed lessons from suggestions that were never tested.
- Surface relevant history when a similar pattern appears again.

**How to explain it:** Learning prevents the next engineer from starting at zero and turns incident experience into reusable team knowledge.

### Loop Talk Track

> We first see the whole system, then turn related signals into an incident. We diagnose by testing hypotheses against evidence, remediate within policy boundaries, and retain only verified lessons. That retained context gives the next investigation a better starting point.

## Beyond Incident Response

### Main Message

> Optimize the estate and the experience.

Azure SRE Agent is not limited to active incidents. It can analyze the Azure estate and the applications running on it to identify improvements before customers are affected.

### Azure Estate - Govern the Platform as a System

The agent can examine resources across subscriptions and prioritize improvements without trading away reliability.

#### 1. Governance and RBAC

- Identify policy gaps, inconsistent tags, and unclear ownership.
- Review role assignments for excessive or missing permissions.
- Improve compliance, accountability, and auditability.

**How to explain it:** This helps ensure that resources are governed consistently and that people and workloads have the right level of access.

#### 2. Cost and FinOps

- Find idle or underused resources.
- Identify inappropriate sizing and unusual spending patterns.
- Recommend savings while considering availability and performance requirements.

**How to explain it:** The objective is not simply to reduce cost. It is to remove waste without weakening service health.

#### 3. Security Posture

- Identify public exposure, excessive privilege, and risky configuration.
- Relate security findings to the services and customers they could affect.
- Prioritize remediation by operational impact.

**How to explain it:** The agent helps the team focus first on security risks that create the greatest business and reliability exposure.

#### 4. Reliability

- Find single points of failure and weak failure-domain distribution.
- Review backup coverage, recovery readiness, and disaster recovery design.
- Highlight dependencies that could prevent service restoration.

**How to explain it:** This exposes where the architecture may work normally but fail badly during an outage.

### Application Experience - Optimize What Customers Feel

- **Observability:** Follow latency, errors, and traces to understand application health.
- **Performance:** Identify CPU, memory, dependency, and query bottlenecks.
- **Scaling and cost:** Align capacity and autoscale behavior with actual demand.
- **Release reliability:** Review deployments, rollback readiness, and CI/CD practices.

**How to explain it:** Estate analysis improves the platform; application analysis improves the experience delivered to the customer.

## Integration Ecosystem

### Main Message

> Meet the team where work happens.

The agent connects relevant context from existing systems into one investigation. Teams keep their established tools rather than moving every workflow into a new interface.

### Azure SRE Agent - Reason, Act, and Learn

- **Reason:** Correlate evidence and test hypotheses.
- **Act:** Recommend or execute governed operational actions.
- **Learn:** Retain verified outcomes for future investigations.

### Connected Systems

| Area | Examples | What It Contributes |
|---|---|---|
| Observability | Azure Monitor, Application Insights, Log Analytics | Health signals, logs, metrics, traces, and alerts |
| Source and delivery | GitHub, Azure DevOps | Commits, pull requests, pipelines, and deployments |
| Incident response | Azure Alerts, PagerDuty, ServiceNow | Incident status, ownership, escalation, and coordination |
| Data and MCP | Azure Data Explorer, partner tools, custom systems | Specialized operational data and approved tool actions |
| People | Teams, Outlook, approval workflows | Collaboration, notifications, decisions, and approvals |

### How to Explain It

> An alert may begin in Azure Monitor, the related change may be in GitHub, the incident record may be in ServiceNow, and the approval may happen in Teams. Azure SRE Agent connects that permitted context into one investigation thread.

### Control Point

Each connector uses configured authentication and exposes only approved systems, data, and operations. Integration does not mean unrestricted access.

## The Customer Conversation

### Main Message

> Move the operating model, not just the alert queue.

The business value is a change in how the organization operates: faster investigation, less repetitive work, earlier risk discovery, and reusable knowledge.

### Hours to Minutes - Compress Investigation Time

- Automate evidence gathering across multiple systems.
- Use hypothesis-driven diagnosis to focus the investigation.
- Reduce time spent manually searching logs and switching dashboards.

**Customer outcome:** Lower time to understand and recover from incidents.

### Routine to Automated - Return Engineering Capacity

- Schedule repeatable health, compliance, and reliability checks.
- Trigger approved workflows from alerts and operational events.
- Produce consistent results and escalate exceptions to engineers.

**Customer outcome:** Engineers spend more time improving systems and less time performing repetitive checks.

### Reactive to Proactive - Find Risk Before Impact

- Identify reliability weaknesses, scaling constraints, waste, and configuration risk early.
- Prioritize improvements using evidence, impact, and effort.
- Reassess after changes to measure improvement.

**Customer outcome:** Fewer avoidable incidents and better investment decisions.

### Individual to Shared - Preserve Team Knowledge

- Capture verified causes, decisions, and successful resolutions.
- Make operational knowledge available across handoffs and on-call rotations.
- Give new engineers useful context from previous incidents.

**Customer outcome:** The organization becomes less dependent on undocumented knowledge held by individual engineers.

## Closing

### Say

> Azure SRE Agent does more than process alerts. It connects evidence, supports governed recovery, improves the wider Azure environment, works through the tools teams already use, and turns verified experience into shared operational knowledge.

## Business Outcomes

| Shift | Outcome |
|---|---|
| Hours to minutes | Compress investigation time |
| Routine to automated | Return engineering capacity |
| Reactive to proactive | Find risk before impact |
| Individual to shared | Preserve team knowledge |

## One-Line Summary

> Azure SRE Agent helps teams move from reactive firefighting to a governed, evidence-led reliability practice.

## Grounding

The published capability briefing is grounded in Microsoft Learn and the supplied Azure SRE Agent presentation materials. The live incident shown on the page is illustrative; evidence access, actions, and outcomes depend on the systems, identities, permissions, policies, and operating mode configured by the customer.