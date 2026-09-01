[< Previous Challenge](./Challenge-07.md) — **[Home](./README.md)** — [Next Challenge >](./Challenge-09.md)

# Challenge 08 — Improve the Next Heartbeat Response

> **Incident capability exercised in this challenge**: Operational Context · Repeat-Incident Learning · Evidence Precedence

## Introduction

Replay the missing-heartbeat incident after adding verified workload context and one confirmed lesson from the first response. Determine whether the SRE Agent identifies impact, ownership, recovery objectives, and escalation faster without allowing stale knowledge to override current evidence.

Run every command separately from the repository root and inspect its output before continuing. This mission intentionally does not use a PowerShell script.

## Description

### Part 1 — Discover the Deployed Agent

Select the SignalOps environment and retrieve the agent resource ID:

```powershell
$ErrorActionPreference = 'Stop'

Push-Location '.\SRE SignalOps'
azd env select signalops-core
$AGENT_ID = (azd env get-value SRE_AGENT_ID).Trim()
Pop-Location

$API_VERSION = '2026-01-01'
```

Discover the data-plane endpoint through ARM:

```powershell
$AGENT = az rest --method GET --url "https://management.azure.com$AGENT_ID`?api-version=$API_VERSION" | ConvertFrom-Json
$AGENT_ENDPOINT = $AGENT.properties.agentEndpoint.TrimEnd('/')

[pscustomobject]@{
	Endpoint          = $AGENT_ENDPOINT
	ProvisioningState = $AGENT.properties.provisioningState
} | Format-List
```

Request a short-lived token and retain it only in the current process:

```powershell
$TOKEN = (az account get-access-token --resource https://azuresre.dev --query accessToken -o tsv).Trim()
$HEADERS = @{ Authorization = "Bearer $TOKEN" }
```

Do not print or persist `$TOKEN`.

### Part 2 — Record the Before State

List current Agent Memory documents before adding context:

```powershell
$MEMORY_BEFORE = Invoke-RestMethod `
	-Uri "$AGENT_ENDPOINT/api/v1/AgentMemory/files" `
	-Headers $HEADERS `
	-Method Get

$MEMORY_BEFORE | ConvertTo-Json -Depth 10
```

Check indexer state separately:

```powershell
Invoke-RestMethod `
	-Uri "$AGENT_ENDPOINT/api/v1/agentmemory/indexer-status" `
	-Headers $HEADERS `
	-Method Get |
	ConvertTo-Json -Depth 10
```

Open the agent:

```powershell
Start-Process $AGENT_ENDPOINT
```

Submit this exact baseline prompt and save the response in your mission notes:

> **EXERCISE — HEARTBEAT REPLAY:** The selected lab VM has missed heartbeats. Assess impact, likely causes, ownership, recovery objectives, and escalation. Attribute every claim to live Azure evidence, existing Agent Memory, or an explicit assumption. Do not execute a write.

### Part 3 — Create One Reviewed Context Document

Set a temporary file path that will not be committed:

```powershell
$CONTEXT_FILE = Join-Path $env:TEMP 'signalops-workload-reliability-context.md'
$CONTEXT_FILE
```

Create the document with customer-approved values. Replace every angle-bracket placeholder before upload:

```powershell
@'
# Workload Reliability Context

- Workload purpose: <approved-purpose>
- Architecture and dependencies: <approved-architecture-summary>
- Service owner: <approved-team-or-role>
- Escalation path: <approved-non-personal-channel-or-role>
- Criticality: <approved-criticality>
- Heartbeat expectation: <approved-interval>
- Maintenance window: <approved-window>
- Recovery time objective (RTO): <approved-rto>
- Recovery point objective (RPO): <approved-rpo>
- Approved investigation boundaries: <approved-read-only-boundaries>
- Prohibited actions: VM or monitoring changes without explicit authorization
- Review owner: <approved-review-role>
- Review date: <yyyy-mm-dd>
'@ | Set-Content -Path $CONTEXT_FILE -Encoding utf8
```

Read the exact artifact that would be uploaded:

```powershell
Get-Content $CONTEXT_FILE
```

Reject the document if placeholders remain:

```powershell
$UNRESOLVED_PLACEHOLDERS = Select-String -Path $CONTEXT_FILE -Pattern '<[^>]+>'
$UNRESOLVED_PLACEHOLDERS

if ($UNRESOLVED_PLACEHOLDERS) {
	throw 'Replace every placeholder with reviewed context before upload.'
}
```

### Part 4 — Upload and Verify the Context

Upload the single reviewed document:

```powershell
curl.exe -fsS -X POST `
	-H "Authorization: Bearer $TOKEN" `
	-F "files=@$CONTEXT_FILE" `
	"$AGENT_ENDPOINT/api/v1/agentmemory/upload"
```

List memory again and verify the basename appears:

```powershell
$MEMORY_AFTER_CONTEXT = Invoke-RestMethod `
	-Uri "$AGENT_ENDPOINT/api/v1/AgentMemory/files" `
	-Headers $HEADERS `
	-Method Get

$MEMORY_AFTER_CONTEXT | ConvertTo-Json -Depth 10
```

Check indexer state after upload:

```powershell
Invoke-RestMethod `
	-Uri "$AGENT_ENDPOINT/api/v1/agentmemory/indexer-status" `
	-Headers $HEADERS `
	-Method Get |
	ConvertTo-Json -Depth 10
```

Indexing is asynchronous. Re-run the file and indexer reads later if processing is incomplete; do not upload repeated copies to force progress.

### Part 5 — Replay the Identical Question

Submit the baseline prompt again without changing a word:

> **EXERCISE — HEARTBEAT REPLAY:** The selected lab VM has missed heartbeats. Assess impact, likely causes, ownership, recovery objectives, and escalation. Attribute every claim to live Azure evidence, existing Agent Memory, or an explicit assumption. Do not execute a write.

Compare both responses using this matrix:

| Decision area | Before context | After context | Source attribution | Material improvement? |
|---|---|---|---|---|
| Workload impact |  |  |  |  |
| Ownership |  |  |  |  |
| RTO and RPO |  |  |  |  |
| Maintenance interpretation |  |  |  |  |
| Investigation boundary |  |  |  |  |
| Escalation |  |  |  |  |

Current Azure evidence must override conflicting or stale knowledge.

### Part 6 — Add One Verified Incident Lesson

Set only evidence-confirmed values from the previous heartbeat exercise:

```powershell
$VERIFIED_CAUSE = '<confirmed-cause>'
$DECISIVE_EVIDENCE = '<evidence-that-confirmed-the-cause>'
$PREVENTION_GUIDANCE = '<reviewed-prevention-guidance>'
$LESSON_REVIEW_DATE = '<yyyy-mm-dd>'
```

Stop if any value is still a placeholder:

```powershell
$LESSON_VALUES = @($VERIFIED_CAUSE, $DECISIVE_EVIDENCE, $PREVENTION_GUIDANCE, $LESSON_REVIEW_DATE)

if ($LESSON_VALUES | Where-Object { $_ -match '^<.+>$' }) {
	throw 'Do not store an unverified or incomplete incident lesson.'
}
```

Append the reviewed lesson visibly:

```powershell
@"

## Verified Incident Lesson

- Confirmed cause: $VERIFIED_CAUSE
- Decisive evidence: $DECISIVE_EVIDENCE
- Prevention guidance: $PREVENTION_GUIDANCE
- Review date: $LESSON_REVIEW_DATE
"@ | Add-Content -Path $CONTEXT_FILE -Encoding utf8

Get-Content $CONTEXT_FILE
```

Upload the updated document using the same filename:

```powershell
curl.exe -fsS -X POST `
	-H "Authorization: Bearer $TOKEN" `
	-F "files=@$CONTEXT_FILE" `
	"$AGENT_ENDPOINT/api/v1/agentmemory/upload"
```

Verify file and indexer state again with separate reads:

```powershell
Invoke-RestMethod -Uri "$AGENT_ENDPOINT/api/v1/AgentMemory/files" -Headers $HEADERS -Method Get |
	ConvertTo-Json -Depth 10
```

```powershell
Invoke-RestMethod -Uri "$AGENT_ENDPOINT/api/v1/agentmemory/indexer-status" -Headers $HEADERS -Method Get |
	ConvertTo-Json -Depth 10
```

### Part 7 — Test Evidence Precedence

Submit this final replay:

> **EXERCISE — VERIFIED LESSON REPLAY:** Assess the selected VM heartbeat risk using current Azure evidence, the workload context, and the verified incident lesson. State whether the current evidence supports the historical cause. Attribute every claim, flag stale or conflicting context, and investigate alternatives when current evidence differs. Do not execute a write.

Accept the result only if the agent uses the lesson as context rather than assuming every heartbeat loss has the same cause.

### Part 8 — Remove Temporary Sensitive Material

Remove the short-lived token and temporary local document:

```powershell
Remove-Variable TOKEN
$HEADERS = $null
Remove-Item $CONTEXT_FILE -Force
```

Do not store credentials, access tokens, personal contact details, transient resource state, or unverified incident assumptions in Agent Memory. Context can guide interpretation, but current evidence remains authoritative.

## Success Criteria

- [ ] A before-and-after incident replay shows that the knowledge document materially improves impact, ownership, recovery, or escalation reasoning
- [ ] The document contains operational context, ownership, recovery objectives, and investigation boundaries
- [ ] The grounded response cites or clearly attributes the custom knowledge it used
- [ ] The response distinguishes live evidence from organizational context and identifies any conflict between them
- [ ] One verified incident lesson is added and appears in a later grounded response
- [ ] **Explain to your coach** — how can a verified incident lesson speed future response without becoming a shortcut that biases the diagnosis?

## Learning Resources

- [Connect knowledge sources to Azure SRE Agent](https://learn.microsoft.com/en-us/azure/sre-agent/connect-knowledge)
- [Knowledge source concepts in Azure AI Search](https://learn.microsoft.com/en-us/azure/search/search-knowledge-source-overview)
- [Reliability guidance in the Azure Well-Architected Framework](https://learn.microsoft.com/en-us/azure/well-architected/reliability/)
- [Azure Monitor data platform](https://learn.microsoft.com/en-us/azure/azure-monitor/data-platform)

## Tips

- Use the exact same question before and after adding knowledge; otherwise the comparison is weak.
- Keep durable policy and architecture in knowledge. Keep transient resource state in Azure Monitor and Resource Graph.
- Record only a verified lesson. A plausible but unconfirmed RCA should remain a hypothesis, not become institutional knowledge.