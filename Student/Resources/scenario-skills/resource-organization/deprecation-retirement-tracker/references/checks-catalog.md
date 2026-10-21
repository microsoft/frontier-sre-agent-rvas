# Checks catalog

Deprecation and retirement signals detected with Azure Resource Graph, covered by Reader. The scan tool applies these; retirement dates move, so corroborate specifics against Azure Service Health planned retirements and the Azure roadmap.

For each finding the tool records: resource id, resource type, category, subscription, resource group, the deprecated element, a severity, and the recommended target.

## 1. End of life App Service runtimes (category: App Service runtime)

```
az graph query -q "resources | where type =~ 'microsoft.web/sites' | extend fx = tostring(properties.siteConfig.linuxFxVersion) | where isnotempty(fx) | project name, id, subscriptionId, resourceGroup, fx" --first 1000
```

The tool matches the exact normalized linuxFxVersion against current operator verified metadata. High requires a verified end date that has passed. Unknown means metadata, date or stack information is unavailable, not that the stack is supported. Java 8 is not blanket end of life on App Service. Verify distribution, hosting stack and service support policy. Windows and custom stacks need separate evidence.

## 2. Retired database single servers (category: Retired service)

Legacy Single Server resources are migration review candidates. Current retirement status requires dated service metadata, not just the resource type.

```
az graph query -q "resources | where type in~ ('microsoft.dbforpostgresql/servers','microsoft.dbformysql/servers') | project name, id, type, subscriptionId, resourceGroup" --first 1000
```

Severity High only with a verified expired lifecycle date. Otherwise Unknown. Verify the service specific notice and migration path to Flexible Server.

## 3. Classic resources (category: Classic)

Classic resource types require service specific retirement and migration review. They do not all share one inferred retirement date.

```
az graph query -q "resources | where type startswith 'microsoft.classiccompute' or type startswith 'microsoft.classicstorage' or type startswith 'microsoft.classicnetwork' | project name, id, type, subscriptionId, resourceGroup" --first 1000
```

Severity High with verified expired metadata, otherwise Unknown. Verify migration to the Resource Manager equivalent.

## 4. Old Kubernetes versions (category: AKS version)

```
az graph query -q "resources | where type =~ 'microsoft.containerservice/managedclusters' | project name, id, subscriptionId, resourceGroup, kubernetesVersion=tostring(properties.kubernetesVersion)" --first 1000
```

There is no permanent supported minor floor. Match the cluster minor against the current lifecycle snapshot and its standard or LTS support plan. LTS requires explicit AKSLongTermSupport plus Premium tier. Missing dates, stale evidence or unknown enrollment is Unknown. Minor lifecycle evidence does not establish current regional patch availability or upgrade paths.

## 5. End of life operating system images (category: VM OS)

```
az graph query -q "resources | where type =~ 'microsoft.compute/virtualmachines' | extend img = properties.storageProfile.imageReference | project name, id, subscriptionId, resourceGroup, publisher=tostring(img.publisher), offer=tostring(img.offer), sku=tostring(img.sku)" --first 1000
```

Match exact offer and SKU plus verified support entitlement. Base lifecycle, extended support and ESU differ. Image metadata does not establish installed OS patch state. Missing or custom image information is Unknown, not silently skipped as supported.

## Beyond Resource Graph

- Deprecated API versions used by deployments are not stored on the resource; scan your infrastructure as code and pipeline logs for those, and watch Azure Service Health health advisories.
- Basic tier public IP and Basic Load Balancer retirements are reported by the reliability-posture-review skill; they are not duplicated here.

## Severity

- High: already retired or out of support.
- Unknown: no current verified date, unmatched metadata, unparsed version or unconfirmed entitlement. Never counted as a pass.
- Low: reserved for a soft deprecation with a long runway.

## Configurable lifecycle snapshot

Point `SRE_LIFECYCLE_EVIDENCE` at operator verified JSON:

```json
{
  "schema_version": 1,
  "checked_at": "<YYYY-MM-DD>",
  "entries": [
    {
      "service": "app-service",
      "version": "<exact uppercase linuxFxVersion>",
      "support_plan": "app-service",
      "support_end": "<YYYY-MM-DD>",
      "source": "https://learn.microsoft.com/en-us/azure/app-service/language-support-policy"
    }
  ]
}
```

Other keys: `service=aks`, `version=major.minor`, `support_plan=standard` or `lts`; `service=azure-service`, `version=<lowercase resource type>`, `support_plan=service`; `service=vm-os`, `version=<lowercase offer:sku>`, and an explicitly verified support plan. The VM scanner has no entitlement collector, so normal inventory alone leaves it Unknown.

Snapshots older than 30 days, future checked dates, invalid dates and nonofficial source URLs are rejected as Unknown. The helper checks metadata shape and source host, not the truth of the remote page. Verify it before supplying the snapshot. Do not invent an exact day from a month only schedule.

Unknown findings preserve the lifecycle reason, including VM OS image findings. The helper distinguishes unconfigured evidence from a configured missing file, an unreadable file, malformed JSON, invalid schema or metadata, stale evidence and an unmatched entry. Diagnostics omit raw exception text, private paths and file contents. Repair the snapshot and rerun; these errors cannot establish support or trigger a verified retirement finding.

## Sources and validation

Checked 2026-10-21:

- [App Service language support, including Java 8](https://learn.microsoft.com/en-us/azure/app-service/language-support-policy).
- [AKS lifecycle](https://learn.microsoft.com/en-us/azure/aks/supported-kubernetes-versions).
- [AKS support plans and LTS](https://learn.microsoft.com/en-us/azure/aks/long-term-support).

Offline fixtures verify exact matching, evidence expiry and Unknown behavior. No service retirement feed, live resource or deployment was validated.
