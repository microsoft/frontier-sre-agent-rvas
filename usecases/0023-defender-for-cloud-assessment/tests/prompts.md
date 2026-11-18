# Test prompts

In a new chat, type `/agent`, select `defender-cloud-live` and send one prompt at a time. Before the tool is configured, every call returns a configuration error and makes no Azure call.

## 1. Live report

```text
Use defender-cloud-live and only generate-defender-cloud-report. Make one call with operation="report" and all other defaults. Deliver the four actual files through normal sharing, then summarize what to review first from the returned top actions, the coverage and the limits. Do not run follow-up queries or change Azure.
```

Tool call:

```json
{"operation": "report"}
```

**Expected:** One report call and the four file links. The summary uses the returned top actions and coverage; native risk stays separate from technical severity and missing risk is Not evaluated, not low.

## 2. High and critical recommendations

```text
Use query with view=findings and severity=High to list the unhealthy High recommendations with their resources, native risk and source.
```

Tool call:

```json
{"operation": "query", "view": "findings", "severity": "High", "status": "Unhealthy"}
```

**Expected:** Only the matching findings with exact totals and paging fields (total_matched, returned, has_more, next_offset).

## 3. Attack paths

```text
Use query with view=attack_paths. Which attack paths did Defender for Cloud report, with their entry point, target and risk factors?
```

Tool call:

```json
{"operation": "query", "view": "attack_paths"}
```

**Expected:** The native attack paths with their actual nodes and edges; no hop is added and Arc association is only stated when explicit.

## 4. Vulnerabilities

```text
Use query with view=vulnerabilities. Which CVEs were found on machines, how many distinct IDs and resource-CVE pairs, and which are exploitable?
```

Tool call:

```json
{"operation": "query", "view": "vulnerabilities"}
```

**Expected:** CVE occurrences, distinct IDs and resource-CVE pairs kept apart; empty sub-assessments are not reported as zero CVEs.
