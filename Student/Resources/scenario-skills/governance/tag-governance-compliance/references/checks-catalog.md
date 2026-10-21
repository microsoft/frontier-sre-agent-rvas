# Checks catalog

Tag compliance against a required standard, read with Azure Resource Graph and covered by Reader.

For each finding the tool records: resource id, resource type, subscription, resource group, the missing tags, a severity, and the recommended values.

HTTP reads use `shared\tools\azure_http.py` and the bundled governance policy for approved HTTPS hosts, explicit timeouts, disabled redirects and bounded transient retries. Authorization failures are not retried. Deployed bundles must include the shared tools and policy.

## The required standard

The default required tags are owner, environment, and cost center. Override them by passing a comma separated list to the tool, for example:

```
python tools/tag_compliance.py owner,environment,cost-center,application
```

Choose the set your organisation actually enforces. A small, enforced standard beats a long, ignored one.

## Enumerate resources and tags

```
az graph query -q "resources | project name, id, type, resourceGroup, subscriptionId, tags" --first 1000
```

The tool reads the tags bag on each resource. Resource groups carry their own tags and are checked separately from resources where you extend the scan; the default run covers resources.

## Tag name and value matching

Azure tag names are case insensitive. Separators remain significant:

- cost-center is satisfied by Cost-Center, not by CostCenter, cost_center or costcenter.
- owner is satisfied by Owner or OWNER.

No alias expansion is implemented. Null, empty or whitespace values fail the requirement. Nonblank values are not normalized or checked against allowed value lists. Azure tag values are case sensitive.

## Denominator and unsupported types

Not all resource types support tags. Resources with observed tags can be assessed directly. For untagged resources, supply an approved JSON mapping of full resource types to `true` or `false` using `--tag-support <file>`, based on the Microsoft support catalog. Unsupported types are excluded, and unknown support is Not assessed, not noncompliant.

Compliance divides compliant assessed resources by all assessed resources, never by inaccessible or unsupported inventory. Empty results are Not assessed, not 100 percent. Any unknown type support or failed collection makes the overall assessment Partial. The collector checks resources, not resource groups or subscriptions. Naming regexes and policy compliance are outside this analyzer.

## Severity

- High: the owner tag is missing. Without an owner there is no accountable team for the resource, which blocks both incident response and chargeback.
- Medium: any other required tag is missing (for example environment or cost center).

A resource missing more than one required tag appears once, listing them, at the highest severity among them.

## Fixing and enforcing

- Fix: apply the missing tags with the correct values. Set owner to the accountable team, environment to the deployment stage, and cost center to the billing code.
- Enforce durably: use Azure Policy to require the tags and, where appropriate, inherit them from the resource group or subscription. Policy is the lasting fix; a one time tagging pass drifts again without it.

## Sources

Verified against Microsoft Learn during this correction:

- [Azure tag semantics and limitations](https://learn.microsoft.com/azure/azure-resource-manager/management/tag-resources)
- [Tag support for resource types](https://learn.microsoft.com/azure/azure-resource-manager/management/tag-support)
