[< Previous Challenge](./Challenge-03.md) — **[Home](./README.md)** — [Next Challenge >](./Challenge-05.md)

# Challenge 04 — Build Grubify Knowledge and Incident Memory

> **Capabilities added in this challenge**: Agent Memory · Knowledge Indexing · Contextual Incident Learning

## Introduction

Traditional monitoring raises an alert and forgets it. Azure SRE Agent can retain approved architecture, runbooks, report templates, and operational lessons so later investigations begin with relevant context. In this mission you will populate the currently empty SignalOps Agent Memory with the four Grubify knowledge documents, verify indexing, and inspect the specialist instructions that require memory-first investigation.

Run every command separately from the repository root. Inspect each result before continuing. Never paste or print the access token, and do not upload secrets, personal data, or unverified incident claims.

## Description

### Part 1 — Resolve the Lab Files

Set the exact knowledge and subagent paths used by this repository:

```powershell
$ErrorActionPreference = 'Stop'
$CONFIG_ROOT = (Resolve-Path '.\Student\Resources\azure-sre-agent-config').Path
$KNOWLEDGE_ROOT = Join-Path $CONFIG_ROOT 'knowledge\files\sample-food'
$ARCHITECTURE_FILE = Join-Path $KNOWLEDGE_ROOT 'sample-food-architecture.md'
$HTTP_RUNBOOK_FILE = Join-Path $KNOWLEDGE_ROOT 'http-500-errors.md'
$INCIDENT_TEMPLATE_FILE = Join-Path $KNOWLEDGE_ROOT 'incident-report-template.md'
$ISSUE_TRIAGE_FILE = Join-Path $KNOWLEDGE_ROOT 'github-issue-triage.md'
$HANDLER_FILE = Join-Path $CONFIG_ROOT 'subagents\aca-app-incident-handler.yaml'
```

Verify all five files before making any data-plane call:

```powershell
Get-Item $ARCHITECTURE_FILE, $HTTP_RUNBOOK_FILE, $INCIDENT_TEMPLATE_FILE, $ISSUE_TRIAGE_FILE, $HANDLER_FILE |
  Select-Object Name, Length, FullName |
  Format-Table -AutoSize
```

The source scenario used `knowledge-base/grubify-architecture.md` and `sre-config/agents/incident-handler-core.yaml`. Those paths do not exist in this lab. The correct files are `sample-food-architecture.md` and `subagents/aca-app-incident-handler.yaml` beneath `$CONFIG_ROOT`.

### Part 2 — Inspect the Four Knowledge Documents

Read the Grubify architecture and locate its component, traffic, and operational-entry-point sections:

```powershell
Get-Content $ARCHITECTURE_FILE
```

```powershell
Select-String -Path $ARCHITECTURE_FILE -Pattern '^## Components','^## Traffic And Telemetry','^## Operational Entry Points'
```

Read the HTTP 5xx runbook and locate its trigger questions, metrics/log queries, and validation guidance:

```powershell
Get-Content $HTTP_RUNBOOK_FILE
```

```powershell
Select-String -Path $HTTP_RUNBOOK_FILE -Pattern '^## Triage Questions','^## KQL Queries','^## Validation After Remediation'
```

Read the structured incident report template:

```powershell
Get-Content $INCIDENT_TEMPLATE_FILE
```

Read the GitHub issue triage runbook and its guardrails:

```powershell
Get-Content $ISSUE_TRIAGE_FILE
```

### Part 3 — Discover the Deployed Agent Securely

Select the same azd environment used in Missions 00–03 and retrieve its agent resource ID:

```powershell
Push-Location '.\SRE SignalOps'
azd env select signalops-core
$AGENT_ID = (azd env get-value SRE_AGENT_ID).Trim()
Pop-Location
```

Confirm the resource ID belongs to the isolated SignalOps agent:

```powershell
$AGENT_ID
```

Discover the data-plane endpoint from Azure Resource Manager. Do not hard-code the generated endpoint:

```powershell
$API_VERSION = '2026-01-01'
$AGENT = az rest --method GET --url "https://management.azure.com$AGENT_ID`?api-version=$API_VERSION" | ConvertFrom-Json
$AGENT_ENDPOINT = $AGENT.properties.agentEndpoint.TrimEnd('/')
$AGENT_ENDPOINT
```

Request a short-lived token for the SRE Agent data plane and retain it only in this PowerShell process:

```powershell
$TOKEN = (az account get-access-token --resource https://azuresre.dev --query accessToken -o tsv).Trim()
$HEADERS = @{ Authorization = "Bearer $TOKEN" }
```

Do not display `$TOKEN`, write it to disk, or save it in the azd environment.

### Part 4 — Record the Memory Baseline

Check whether Agent Memory and document retrieval are enabled:

```powershell
Invoke-RestMethod -Uri "$AGENT_ENDPOINT/api/v1/agentmemory/status" -Headers $HEADERS -Method Get |
  ConvertTo-Json -Depth 10
```

Check the indexer state independently:

```powershell
Invoke-RestMethod -Uri "$AGENT_ENDPOINT/api/v1/agentmemory/indexer-status" -Headers $HEADERS -Method Get |
  ConvertTo-Json -Depth 10
```

List the documents currently stored in memory:

```powershell
Invoke-RestMethod -Uri "$AGENT_ENDPOINT/api/v1/AgentMemory/files" -Headers $HEADERS -Method Get |
  ConvertTo-Json -Depth 10
```

An empty `files` array is the expected starting state after Mission 02. It means the memory service is available but no custom knowledge has been loaded.

### Part 5 — Upload Each Approved Knowledge File

Upload the architecture document:

```powershell
curl.exe -fsS -X POST -H "Authorization: Bearer $TOKEN" -F "files=@$ARCHITECTURE_FILE" "$AGENT_ENDPOINT/api/v1/agentmemory/upload"
```

Upload the HTTP 5xx investigation runbook:

```powershell
curl.exe -fsS -X POST -H "Authorization: Bearer $TOKEN" -F "files=@$HTTP_RUNBOOK_FILE" "$AGENT_ENDPOINT/api/v1/agentmemory/upload"
```

Upload the incident report template:

```powershell
curl.exe -fsS -X POST -H "Authorization: Bearer $TOKEN" -F "files=@$INCIDENT_TEMPLATE_FILE" "$AGENT_ENDPOINT/api/v1/agentmemory/upload"
```

Upload the GitHub issue triage runbook:

```powershell
curl.exe -fsS -X POST -H "Authorization: Bearer $TOKEN" -F "files=@$ISSUE_TRIAGE_FILE" "$AGENT_ENDPOINT/api/v1/agentmemory/upload"
```

Each command is intentionally separate so you can identify the exact file if an upload fails. Re-uploading the same filename updates that document; it does not require a second copy.

### Part 6 — Verify Stored and Indexed Knowledge

List Agent Memory files again:

```powershell
Invoke-RestMethod -Uri "$AGENT_ENDPOINT/api/v1/AgentMemory/files" -Headers $HEADERS -Method Get |
  ConvertTo-Json -Depth 10
```

Confirm these four basenames appear:

```text
sample-food-architecture.md
http-500-errors.md
incident-report-template.md
github-issue-triage.md
```

Check indexing after the uploads:

```powershell
Invoke-RestMethod -Uri "$AGENT_ENDPOINT/api/v1/agentmemory/indexer-status" -Headers $HEADERS -Method Get |
  ConvertTo-Json -Depth 10
```

Indexing is asynchronous. If the newest execution has not processed the files yet, wait for the service to run and execute the same indexer-status and file-list commands again. Do not re-upload repeatedly just to force indexing.

### Part 7 — Inspect the Memory-Aware Specialist

Read the lab's Azure Container Apps incident-handler manifest:

```powershell
Get-Content $HANDLER_FILE
```

Show only the instructions and tool entries related to memory:

```powershell
Select-String -Path $HANDLER_FILE -Pattern 'Always search memory','incident report template','SearchMemory'
```

The manifest instructs `aca-app-incident-handler` to search memory for similar incidents first, use the incident report template, and keep live evidence in the investigation. A local manifest proves desired configuration, not live registration. List live subagents separately:

```powershell
Invoke-RestMethod -Uri "$AGENT_ENDPOINT/api/v2/extendedAgent/agents" -Headers $HEADERS -Method Get |
  ConvertTo-Json -Depth 10
```

If `aca-app-incident-handler` is absent, record a configuration gap. Do not claim that the live agent used the local manifest.

### Part 8 — Demonstrate Contextual Retrieval

Open the deployed SRE Agent:

```powershell
Start-Process $AGENT_ENDPOINT
```

Ask a bounded question that can be answered from the uploaded documents:

> Using Agent Memory, summarize the Grubify API routes, the HTTP 5xx triage sequence, and the required incident-report sections. Name the knowledge documents you used. Do not query or change live Azure resources.

Accept the result only when it identifies the uploaded sources and does not invent routes, telemetry, or incident facts. Knowledge provides durable context; it does not prove current service state.

Remove the token from the current shell when the exercise is complete:

```powershell
Remove-Variable TOKEN
$HEADERS = $null
```

## Success Criteria

- [ ] The four actual Grubify knowledge files and the ACA incident-handler manifest are resolved from repository-relative paths
- [ ] Agent endpoint discovery uses `SRE_AGENT_ID` and ARM rather than a copied endpoint
- [ ] The short-lived token uses the `https://azuresre.dev` audience and is neither printed nor persisted
- [ ] Memory status, indexer status, and file inventory are recorded separately before upload
- [ ] All four approved documents are uploaded with individual, visible commands
- [ ] The post-upload inventory contains all four expected basenames and indexing state is recorded honestly
- [ ] Local desired configuration is distinguished from live subagent registration
- [ ] A memory-only prompt attributes its answer to the uploaded documents and makes no claim about current Azure health
- [ ] **Explain to your coach** — how can durable knowledge accelerate a future incident while live telemetry remains the authority for current state?

## Learning Resources

- [Azure SRE Agent memory](https://learn.microsoft.com/en-us/azure/sre-agent/memory)
- [Connect knowledge to Azure SRE Agent](https://learn.microsoft.com/en-us/azure/sre-agent/connect-knowledge)
- [Azure SRE Agent API reference](https://learn.microsoft.com/en-us/azure/sre-agent/api-reference)
- [Azure SRE Agent subagents](https://learn.microsoft.com/en-us/azure/sre-agent/sub-agents)

## Tips

- Verify file basenames before upload because Agent Memory identifies uploaded documents by filename.
- Treat `status`, `indexer-status`, and `files` as separate checks; one successful response does not imply all documents are searchable.
- Keep architecture and approved runbooks in memory. Keep access tokens, transient metrics, and unverified hypotheses out.
- If a local manifest is not returned by the live subagent API, report the gap instead of presenting desired state as deployed state.
