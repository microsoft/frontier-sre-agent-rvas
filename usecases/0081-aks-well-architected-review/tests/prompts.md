# Test prompts

In a new chat, type `/agent`, select `aks-waf-live` and send one prompt at a time. Replace `<APPROVED_AKS_NAME>` with an approved cluster. Before the tool is configured, report and query calls return a configuration error and make no network call.

## 1. Full review of one cluster

```text
Generate the complete read-only AKS configuration review for <APPROVED_AKS_NAME> with operation=report. Cover cluster, workloads and associated resources across best practices, security, FinOps and optimization, including all five WAF pillars. Immediately deliver the HTML, complete JSON, findings CSV and inventory CSV. Show coverage, sources, not evaluated and not applicable items and limits; do not change anything.
```

Tool call:

```json
{"operation": "report", "cluster_name": "<APPROVED_AKS_NAME>"}
```

**Expected:** One report call and four file links. The local index is always shown beside coverage and the not evaluated and not applicable counts; it is not an official Well-Architected Review.

## 2. Roster

```text
Use operation=list_clusters to list the fixed configured cluster roster before choosing a scope. Explain why this roster is configuration metadata rather than observed cluster presence or health.
```

Tool call:

```json
{"operation": "list_clusters"}
```

**Expected:** The configured allowlist, without network calls; it is not observed health.

## 3. Source coverage

```text
Use query/coverage for <APPROVED_AKS_NAME>. Which sources failed or were partial, with what HTTP/error code, and which checks cannot be evaluated? Explain why HTTP 502/429 is not permission denied and why HTTP 403 does not mean zero Kubernetes objects.
```

Tool call:

```json
{"operation": "query", "view": "coverage", "cluster_name": "<APPROVED_AKS_NAME>", "status": "denied", "limit": 10}
```

**Expected:** Per-source receipts with HTTP status; denied sources make their checks not evaluated, never zero objects.

## 4. Security findings

```text
Use query/findings with area=security and status=failed. Prioritize only observed risks with their resource, configuration, source, UTC timestamp, qualified impact and Microsoft recommendation. Do not invent critical findings.
```

Tool call:

```json
{"operation": "query", "view": "findings", "area": "security", "status": "failed", "limit": 10}
```

**Expected:** Only failed security checks with their evidence and a Microsoft recommendation.
