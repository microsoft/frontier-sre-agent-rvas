# Test prompts

In a new chat, type `/agent`, select `aks-waf-live` and send one prompt at a time. Replace `<AKS_NAME>` with a cluster name returned by `list_clusters` and `<SUBSCRIPTION_NAME_OR_ID>` with a subscription display name or ID. Until `TENANT_ID` and `MANAGED_IDENTITY_CLIENT_ID` are set, every call returns `configuration_required` and makes no network call.

## 1. One report for every cluster

```text
Generate the complete read-only AKS configuration review for every cluster in every subscription with operation=report and cluster_names=all. Cover clusters, workloads and associated resources across best practices, security, FinOps and optimization, including all five WAF pillars. Immediately deliver the HTML, complete JSON, findings CSV and inventory CSV, and summarize collected, partial and failed clusters, the main findings and cost per currency. Show coverage, not evaluated and not applicable items and limits; do not change anything.
```

Tool call:

```json
{"operation": "report", "cluster_names": "all"}
```

**Expected:** One report call and four file links. The HTML opens on a fleet overview with Subscription and Cluster filters and one row per cluster; a cluster that could not be read stays an error, never healthy, and borrows no data from another cluster. The local index is always shown beside coverage and the not evaluated and not applicable counts; it is not an official Well-Architected Review.

## 2. Discover the clusters

```text
List every AKS cluster you can see, grouped by subscription, with resource group and region (operation=list_clusters, limit=100, following next_offset until it is null).
```

Tool call:

```json
{"operation": "list_clusters", "limit": 100}
```

**Expected:** The clusters returned by the fixed, read-only Azure Resource Graph discovery query, with resource group, subscription name and ID, region and environment, paged with next_offset. It is inventory, not health; a cluster the identity cannot read is not listed.

## 3. One subscription

```text
Generate the AKS configuration review for all clusters in subscription <SUBSCRIPTION_NAME_OR_ID> (operation=report, subscription=<SUBSCRIPTION_NAME_OR_ID>) and deliver the four files.
```

Tool call:

```json
{"operation": "report", "subscription": "<SUBSCRIPTION_NAME_OR_ID>"}
```

**Expected:** One report for the clusters of that subscription only. An unknown subscription returns unknown_subscription with close matches; more than 100 clusters returns too_many_clusters.

## 4. One cluster

```text
Generate the complete read-only AKS configuration review for <AKS_NAME> with operation=report. Cover cluster, workloads and associated resources across best practices, security, FinOps and optimization, including all five WAF pillars. Immediately deliver the HTML, complete JSON, findings CSV and inventory CSV. Show coverage, sources, not evaluated and not applicable items and limits; do not change anything.
```

Tool call:

```json
{"operation": "report", "cluster_name": "<AKS_NAME>"}
```

**Expected:** One report call and four file links; the HTML opens directly on the detailed review of that cluster.

## 5. Source coverage

```text
Use query/coverage for <AKS_NAME>. Which sources failed or were partial, with what HTTP/error code, and which checks cannot be evaluated? Explain why HTTP 502/429 is not permission denied and why HTTP 403 does not mean zero Kubernetes objects.
```

Tool call:

```json
{"operation": "query", "view": "coverage", "cluster_name": "<AKS_NAME>", "status": "denied", "limit": 10}
```

**Expected:** Per-source receipts with HTTP status; denied sources make their checks not evaluated, never zero objects. While Kubernetes reads are off (the default), the Kubernetes sources are not_configured, not denied.

## 6. Security findings

```text
Use query/findings for <AKS_NAME> with area=security and status=failed. Prioritize only observed risks with their resource, configuration, source, UTC timestamp, qualified impact and Microsoft recommendation. Do not invent critical findings.
```

Tool call:

```json
{"operation": "query", "view": "findings", "cluster_name": "<AKS_NAME>", "area": "security", "status": "failed", "limit": 10}
```

**Expected:** Only failed security checks with their evidence and a Microsoft recommendation.
