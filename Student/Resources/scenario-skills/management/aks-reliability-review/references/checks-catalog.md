# Checks catalog

AKS reliability and operational checks, read from the managed cluster configuration with Azure Resource Graph and covered by Reader. The scan tool evaluates each cluster; this catalog is the source of truth for each check and its fix.

For each finding the tool records: cluster, subscription, resource group, the check, a severity, and the recommended change.

## Enumerate clusters

```
az graph query -q "resources | where type =~ 'microsoft.containerservice/managedclusters' | project name, id, subscriptionId, resourceGroup, sku, properties" --first 1000
```

The tool reads the properties object for each cluster.

## Checks

1. Kubernetes minor lifecycle outside verified support dates (High). Dates come from a current operator verified snapshot, not a permanent minor floor. Missing metadata or an unconfirmed support plan is Unknown.
2. Node pool not spread across zones (Medium only with confirmed regional applicability). Unknown region or VM SKU support is Unknown, not a failure. Verify actual scheduling across supported zones before planning replacement.
3. System pool below three production nodes (Medium), including an autoscaler minimum below three. Two is a platform minimum, not the production recommendation. Missing counts are Unknown. User pool count alone is not scored as a production system pool.
4. No dedicated system node pool (Low). System pods share user workloads. Fix: add a system mode node pool so control components are isolated.
5. Control plane open to the internet (Medium). Neither a private cluster nor API server authorized IP ranges. Fix: enable a private cluster, or set authorized IP ranges.
6. No auto upgrade channel (Medium). Patches are not applied automatically. Fix: set an upgrade channel (for example patch or stable) with a maintenance window.
7. Container Insights not enabled (Medium). No cluster monitoring add on. Fix: enable Azure Monitor Container Insights.
8. No policy engine identified (Low). Azure, Calico and Azure CNI Powered by Cilium are recognized. Engine presence does not prove policy objects exist or traffic is restricted. Audit actual policy resources separately.
9. Entra ID and Kubernetes RBAC not enabled (Medium). Fix: enable Entra ID integration and Kubernetes RBAC for authenticated, authorised access.
10. Free tier with no uptime SLA (Low, Medium for production). Fix: move to the Standard tier for the control plane uptime SLA on production clusters.

## Verify a cluster by hand

```
az aks show --resource-group <rg> --name <cluster> --subscription <id> -o jsonc
az aks nodepool list --resource-group <rg> --cluster-name <cluster> --subscription <id> --query "[].{name:name,count:count,zones:availabilityZones,mode:mode}"
```

## Severity

Blast radius and likelihood drive severity. Do not change severity based only on resource names. Missing lifecycle or configuration evidence is Unknown and never a pass.

## Lifecycle evidence

`SRE_LIFECYCLE_EVIDENCE` points to a local JSON snapshot verified by the operator. The helper validates shape, dates and an official HTTPS source URL, not the contents of the source page. It does not fetch the lifecycle calendar.

```json
{
  "schema_version": 1,
  "checked_at": "<YYYY-MM-DD>",
  "entries": [
    {
      "service": "aks",
      "version": "<major.minor>",
      "support_plan": "standard",
      "support_end": "<YYYY-MM-DD>",
      "source": "https://learn.microsoft.com/en-us/azure/aks/supported-kubernetes-versions"
    }
  ]
}
```

Replace placeholders with verified dates. Evidence expires after 30 days; future checked dates, missing dates and unmatched entries yield Unknown. Do not invent an exact date from a month only planning table. Use separate `standard` and `lts` entries. LTS applies only with `supportPlan=AKSLongTermSupport` and Premium tier; `KubernetesOfficial` selects standard. Missing or inconsistent plan fields are Unknown.

Unknown results retain `reason` and `evidence_error`. Diagnostics distinguish an unconfigured snapshot (`SnapshotUnconfigured`), a configured missing file (`SnapshotNotFound`), an unreadable file (`SnapshotUnreadable`), malformed JSON (`SnapshotMalformed`), invalid schema or metadata, stale evidence and no matching entry. File contents and private paths are not included. These reasons are assessment evidence, not passing lifecycle results.

Only minor lifecycle dates are assessed. Regional rollout, supported patch versions, actual upgrade paths and entitlement require live verification. Zone applicability can be passed to the Python evaluator as a reviewed region to boolean mapping; the CLI leaves it Unknown rather than assuming every region and VM SKU supports zones.

## Sources and validation

Checked 2026-10-21:

- [AKS support](https://learn.microsoft.com/en-us/azure/aks/supported-kubernetes-versions).
- [LTS requirements and patch limits](https://learn.microsoft.com/en-us/azure/aks/long-term-support).
- [System pool recommendations](https://learn.microsoft.com/en-us/azure/aks/use-system-pools).
- [Cilium policy enforcement](https://learn.microsoft.com/en-us/azure/aks/azure-cni-powered-by-cilium).

Offline tests exercise metadata and configuration evaluation. No actual cluster, region capability or API response was validated.
