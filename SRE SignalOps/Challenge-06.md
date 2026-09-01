[< Previous Challenge](./Challenge-05.md) — **[Home](./README.md)** — [Next Challenge >](./Challenge-07.md)

# Challenge 06 — Route a Cross-Domain Incident

> **Incident capability exercised in this challenge**: Domain Routing · Coordinated Investigation · Least Privilege

## Introduction

A Grubify HTTP failure may originate in the application, telemetry path, network, or Azure platform. Missions 03–05 established the incident, approved knowledge, and evidence boundaries; this mission uses that context to route an ambiguous incident by evidence domain while preserving one accountable incident narrative.

Run every command separately from the repository root and inspect its output before continuing. This mission intentionally does not use a PowerShell script.

## Description

### Part 1 — Reuse the SignalOps Agent

Select the same isolated azd environment used in Missions 03–05 and resolve the deployed SRE Agent:

```powershell
$ErrorActionPreference = 'Stop'

Push-Location '.\SRE SignalOps'
azd env select signalops-core
$AGENT_ID = (azd env get-value SRE_AGENT_ID).Trim()
Pop-Location

$API_VERSION = '2026-01-01'
```

Confirm the active subscription and agent ID before requesting data-plane access:

```powershell
az account show --query '{Subscription:name,SubscriptionId:id,Tenant:tenantId}' -o table
$AGENT_ID
```

Discover the current endpoint from ARM:

```powershell
$AGENT = az rest --method GET --url "https://management.azure.com$AGENT_ID`?api-version=$API_VERSION" | ConvertFrom-Json
$AGENT_ENDPOINT = $AGENT.properties.agentEndpoint.TrimEnd('/')
$AGENT_ENDPOINT
```

Request a short-lived data-plane token and keep it only in the current PowerShell process:

```powershell
$TOKEN = (az account get-access-token --resource https://azuresre.dev --query accessToken -o tsv).Trim()
$HEADERS = @{ Authorization = "Bearer $TOKEN" }
```

Do not display `$TOKEN`, write it to disk, or save it in the azd environment.

### Part 2 — Inventory the Live Specialist Roster

Read the registered specialists from the SRE Agent data plane:

```powershell
$AGENT_RESPONSE = Invoke-RestMethod `
  -Uri "$AGENT_ENDPOINT/api/v2/extendedAgent/agents" `
  -Headers $HEADERS `
  -Method Get

$LIVE_AGENTS = if ($AGENT_RESPONSE.PSObject.Properties.Name -contains 'agents') {
  $AGENT_RESPONSE.agents
} elseif ($AGENT_RESPONSE.PSObject.Properties.Name -contains 'value') {
  $AGENT_RESPONSE.value
} else {
  @($AGENT_RESPONSE)
}

$LIVE_AGENTS = @($LIVE_AGENTS)

$LIVE_AGENT_ROSTER = @($LIVE_AGENTS | ForEach-Object {
  $AGENT_RECORD = $_
  $AGENT_PROPERTIES = $AGENT_RECORD.properties

  $LIVE_AGENT_TYPE = if ($AGENT_RECORD.PSObject.Properties.Name -contains 'agentType') {
    $AGENT_RECORD.agentType
  } elseif ($null -ne $AGENT_PROPERTIES -and $AGENT_PROPERTIES.PSObject.Properties.Name -contains 'agentType') {
    $AGENT_PROPERTIES.agentType
  } else {
    $null
  }

  $LIVE_HANDOFF_DESCRIPTION = if ($AGENT_RECORD.PSObject.Properties.Name -contains 'handoffDescription') {
    $AGENT_RECORD.handoffDescription
  } elseif ($null -ne $AGENT_PROPERTIES -and $AGENT_PROPERTIES.PSObject.Properties.Name -contains 'handoffDescription') {
    $AGENT_PROPERTIES.handoffDescription
  } else {
    $null
  }

  [pscustomobject]@{
    Name               = $AGENT_RECORD.name
    ResourceType       = $AGENT_RECORD.type
    AgentType          = $LIVE_AGENT_TYPE
    HandoffDescription = $LIVE_HANDOFF_DESCRIPTION
  }
})
```

Display the fields used by the primary agent to decide a route:

```powershell
$LIVE_AGENT_ROSTER |
  Select-Object Name, ResourceType, AgentType, HandoffDescription |
  Sort-Object Name |
  Format-Table -Wrap -AutoSize
```

The current API may return an ARM-style record with `type: ExtendedAgent` and routing metadata beneath `properties`. `ResourceType` identifies the API resource shape; it is not a substitute for the manifest's `agent_type`. If `AgentType` is not returned, record it as a live registration evidence gap. Do not fill it from the repository manifest.

Check for the three specialists used in this exercise:

```powershell
$EXPECTED_SPECIALISTS = @(
  'aca-app-incident-handler'
  'network-traffic-analyst'
  'cost-optimization-agent'
)

$EXPECTED_SPECIALISTS | ForEach-Object {
  $SPECIALIST_NAME = $_
  $MATCH = @($LIVE_AGENT_ROSTER | Where-Object { $_.Name -eq $SPECIALIST_NAME })
  [pscustomobject]@{
    Name       = $SPECIALIST_NAME
    Registered = $MATCH.Count -gt 0
    AgentType  = if ($MATCH.Count -eq 0) { '<not registered>' } elseif ($null -eq $MATCH[0].AgentType) { '<not returned>' } else { $MATCH[0].AgentType }
    Route      = if ($MATCH.Count -gt 0) { 'available' } else { 'unavailable' }
  }
} | Format-Table -AutoSize
```

In the prepared SignalOps environment, all three specialists should report `Registered = True` and `Route = available`. Treat any other result as live configuration drift and record the affected route as unavailable.

If a specialist is absent, mark that route `unavailable`. An empty live roster is a valid observed registration gap. A missing `AgentType` on a registered specialist is a metadata evidence gap, not proof that the specialist is absent. A repository manifest proves desired configuration, not live registration.

### Part 3 — Inspect Each Relevant Manifest

Inspect the Grubify application specialist separately:

```powershell
$APP_MANIFEST = '.\Student\Resources\azure-sre-agent-config\subagents\aca-app-incident-handler.yaml'

Get-Content $APP_MANIFEST |
  Select-String -Pattern '^  (description|agent_type|handoff_description):','^    - (SearchMemory|RunAzCliReadCommands|RunAzCliWriteCommands|QueryLogAnalyticsByWorkspaceId|QueryAppInsightsByResourceId|ExecutePythonCode|GetAzCliHelp)$'
```

Inspect the network specialist separately:

```powershell
$NETWORK_MANIFEST = '.\Student\Resources\azure-sre-agent-config\subagents\network-traffic-analyst.yaml'

Get-Content $NETWORK_MANIFEST |
  Select-String -Pattern '^  (description|agent_type|handoff_description):','^    - (RunAzCliReadCommands|RunAzCliWriteCommands|QueryLogAnalyticsByWorkspaceId|GetAzCliHelp)$'
```

Inspect the cost specialist separately as the negative control:

```powershell
$COST_MANIFEST = '.\Student\Resources\azure-sre-agent-config\subagents\cost-optimization-agent.yaml'

Get-Content $COST_MANIFEST |
  Select-String -Pattern '^  (description|agent_type|handoff_description):','^    - (RunAzCliReadCommands|QueryLogAnalyticsByWorkspaceId|QueryAppInsightsByResourceId|ExecutePythonCode|GetAzCliHelp)$'
```

Compare the declared write posture directly. This is an inspection command only; do not invoke any write tool:

```powershell
[pscustomobject]@{
  ApplicationWriteTool = [bool](Select-String -Path $APP_MANIFEST -Pattern '^    - RunAzCliWriteCommands$' -Quiet)
  NetworkWriteTool     = [bool](Select-String -Path $NETWORK_MANIFEST -Pattern '^    - RunAzCliWriteCommands$' -Quiet)
  CostWriteTool        = [bool](Select-String -Path $COST_MANIFEST -Pattern '^    - RunAzCliWriteCommands$' -Quiet)
} | Format-List
```

The application and network manifests are autonomous and write-capable in this isolated demo configuration. Keep this mission read-only: a routing decision does not authorize remediation.

### Part 4 — Start One Accountable Incident Record

Open the deployed SRE Agent:

```powershell
Start-Process $AGENT_ENDPOINT
```

Submit the initial exercise report. If the live roster is empty, tell the SRE Agent that this is a labeled routing exercise based on local desired-state manifests and that no live specialist handoff may be claimed:

> **EXERCISE:** Grubify clients receive intermittent HTTP 5xx responses, and one backend dependency shows connection failures. Determine which operational domains must investigate and in what order.

Then submit this routing instruction:

> Create one incident record with a single owner, timeline, current hypothesis, evidence needed next, unresolved questions, and confidence. Use the live specialist roster to choose the first specialist. Before routing, state the exact evidence that specialist must return and the condition that would justify a second-domain handoff. This is a read-only exercise: do not remediate, restart, roll back, change network configuration, or create an issue.

Record the first routing decision:

| Decision | Required record |
|---|---|
| Primary owner | One accountable owner for the complete incident |
| First specialist | Name from the live inventory, or `unavailable` |
| Evidence requested | Specific query, metric, log, or configuration observation |
| Return condition | Evidence or bounded uncertainty that returns to the primary record |
| Handoff condition | Observation that makes another domain necessary |
| Write posture | Declared capability, with no write authorized in this mission |

### Part 5 — Introduce Network Evidence

Add this evidence to the same conversation:

> **NEW EVIDENCE:** Application telemetry confirms failed dependency calls. A read-only network observation reports denied flows for the same destination and port during the failure window. Update the existing incident record. Decide whether a network-specialist handoff is now justified, state exactly what evidence it must return, and keep the original primary owner. Do not perform remediation.

The response must append to the existing timeline rather than create a second incident narrative. Record the returned network evidence, confidence change, and any remaining application question. When the specialist is not registered, the correct route result is `unavailable — registration required`, followed by the evidence that would have been requested.

### Part 6 — Test an Unrelated Cost Route

Submit a negative-control prompt in the same incident:

> **NEGATIVE CONTROL:** A cost dashboard also shows a month-to-date spending increase. Decide whether the cost specialist belongs in the active availability investigation. Reject the route unless current evidence makes cost causally relevant to the HTTP 5xx or denied-flow path. Explain the decision without starting a separate investigation.

The cost specialist should not displace the application or network investigation merely because it is registered.

### Part 7 — Compare the Final Routing Record

Complete this matrix from observed responses:

| Evidence state | Selected domain | Evidence requested | Evidence returned | Confidence change | Incident owner | Route result |
|---|---|---|---|---|---|---|
| Initial HTTP 5xx |  |  |  |  |  |  |
| Denied network flow |  |  |  |  |  |  |
| Cost increase |  |  |  |  |  | Rejected or causally justified |

Compare the matrix with the live inventory and local manifests. Report any mismatch between live `agentType` or `handoffDescription` and desired configuration as a registration gap, not as proven specialist capability.

Remove the short-lived token when the exercise is complete:

```powershell
Remove-Variable TOKEN
$HEADERS = $null
```

## Success Criteria

- [ ] The live specialist inventory is retrieved directly from the data plane without a wrapper script
- [ ] The application, network, and cost manifests are inspected separately and compared with live registration
- [ ] The initial incident hypothesis identifies the evidence needed before choosing a specialist
- [ ] Application and network handoffs are justified by returned evidence rather than keywords
- [ ] The primary SRE Agent preserves one timeline, owner, and unresolved-question list across handoffs
- [ ] Tool scope, write posture, overlap, and no-owner gaps are visible without authorizing a write
- [ ] The unrelated cost prompt does not divert the availability investigation without causal evidence
- [ ] **Explain to your coach** — when should an SRE keep an investigation in one domain, and when is a specialist handoff justified?

## Learning Resources

- [Azure SRE Agent subagents](https://learn.microsoft.com/en-us/azure/sre-agent/subagents)
- [Azure SRE Agent tools](https://learn.microsoft.com/en-us/azure/sre-agent/tools)
- [Zero Trust least-privilege principle](https://learn.microsoft.com/en-us/security/zero-trust/deploy/identity)

## Tips

- Route according to the next evidence required, not the loudest keyword.
- A handoff must return evidence or a bounded uncertainty to the primary incident record.
- Do not let multiple specialists create competing timelines or owners.
- Live registration and repository manifests are separate evidence sources; compare them explicitly.
