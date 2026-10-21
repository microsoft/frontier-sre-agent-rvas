# Checks catalog

Quota and limit signals read from the Azure usage endpoints. The scan tool reads these across the regions each subscription uses. All are covered by Reader. Run any by hand with the RunAzCliReadCommands tool to verify a finding.

For each finding the tool records: subscription, region, quota name, used value, limit, utilization percent, and a severity from the utilization.

## Where to look

First find the regions each subscription actually uses, so the scan does not read every region in Azure:

```
az graph query -q "resources | where isnotempty(location) | summarize by subscriptionId, location" --first 1000
```

Then read the usage counters in those regions.

## 1. Compute quotas (per region)

```
az rest --method GET --url "https://management.azure.com/subscriptions/<id>/providers/Microsoft.Compute/locations/<region>/usages?api-version=2023-07-01"
```

Watch the total regional vCPUs, the per family vCPUs (for example Standard DSv5 Family vCPUs), availability sets, and virtual machine scale sets. A family at its limit blocks new machines of that size even when the regional total has room.

## 2. Network quotas (per region)

```
az rest --method GET --url "https://management.azure.com/subscriptions/<id>/providers/Microsoft.Network/locations/<region>/usages?api-version=2023-09-01"
```

Watch public IP addresses, static public IPs, network interfaces, load balancers, network security groups, virtual networks, and public IP prefixes. Public IP exhaustion is a common cause of a failed scale out.

## 3. Storage quota (per subscription and region)

```
az rest --method GET --url "https://management.azure.com/subscriptions/<id>/providers/Microsoft.Storage/locations/<region>/usages?api-version=2023-05-01"
```

Watch the storage account count against the per subscription per region limit.

## Severity from utilization

- Critical: utilization at or above 95 percent. Compare planned demand with remaining headroom; utilization alone does not predict every deployment outcome.
- High: at or above 90 percent.
- Medium: at or above the threshold (80 percent by default) and below 90 percent.
- Below the threshold: not reported.

Recommendation for any finding: request a quota increase for that counter in that region before it blocks work, through Azure portal Quotas, the Microsoft.Quota API, or a support request. The skill never requests the increase itself.

## Tuning

The threshold must be greater than zero and at most 100. Lower it (for example 70) ahead of a launch for an earlier warning. Invalid, zero, unknown or unlimited limits are not healthy headroom. Such counters make coverage incomplete even though no percentage finding can be computed.

Each endpoint records Complete, Partial or Not assessed. Failed reads, empty responses and unknown counters prevent an overall Complete. Empty region discovery is Not assessed. Discovery uses only regions present in visible inventory, not all intended deployment regions, and these usage APIs do not cover every Azure service limit or guarantee physical capacity.

## Sources and validation

- [Storage regional usages API](https://learn.microsoft.com/en-us/rest/api/storagerp/usages/list-by-location?view=rest-storagerp-2023-05-01), checked 2026-10-21.
- [View quotas](https://learn.microsoft.com/en-us/azure/quotas/view-quotas).

Regression tests mock all reads. Endpoint response shape, live quotas and deployment success were not validated.
