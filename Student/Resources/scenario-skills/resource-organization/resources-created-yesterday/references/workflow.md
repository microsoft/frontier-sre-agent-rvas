# Evidence collection and analysis

## Collection

### 1. Creation metadata

Use the documented Resources List API expansion, not an unsupported az resource list --expand switch. Follow nextLink on the approved ARM host until all pages are collected. Missing createdTime is unknown; changedTime is not creation time.

```azurecli
az rest --method get --subscription "<subscription_id>" --url "https://management.azure.com/subscriptions/<subscription_id>/resources?api-version=2021-04-01&%24expand=createdTime,changedTime" --output json
```

### 2. Recent management events

Split capped intervals and deduplicate eventDataId. A successful /write event may be an update; retain caller, claims, HTTP status if returned and correlation ID without logging tokens.

```azurecli
az monitor activity-log list --subscription "<subscription_id>" --start-time "<start_utc>" --end-time "<end_utc>" --max-events 10000 --output json
```

### 3. Deployment attribution

Use only selected in window deployments and join target resource IDs to operations. Do not export template parameter values or deployment outputs that could contain secrets.

```azurecli
az deployment group list --subscription "<subscription_id>" --resource-group "<resource_group>" --output json
az deployment operation group list --subscription "<subscription_id>" --resource-group "<resource_group>" --name "<deployment_name>" --output json
```

### 4. Subscription scoped deployment attribution

For the operation read substitute a deployment_name found in this subscription deployment list, not an unrelated group deployment. Select only in window deployments and match target IDs; exclude secret parameters/outputs from evidence sharing.

```azurecli
az deployment sub list --subscription "<subscription_id>" --output json
az deployment operation sub list --subscription "<subscription_id>" --name "<deployment_name>" --output json
```

## Analysis rules

1. Select resources with a trustworthy createdTime or systemData.createdAt inside [start_utc,end_utc). If only a write exists, label creation candidate unless a Created result and supporting provider evidence establish a new resource.
2. Correlate resource ID, timestamp and correlation ID with successful Activity Log records; report the creator from systemData or event claims with its source. Missing attribution remains null.
3. Classify ARM deployment only when deployment operation evidence targets the resource. Service principal callers suggest automation but do not prove a pipeline; portal/manual origin remains unknown without client or pipeline evidence.
4. Apply the type specific approved naming rules, including case and allowed exceptions. Without a supplied rule mark naming Not assessed rather than invent a convention.
5. Report resource name, type, group, subscription, creation time, creator, deployment evidence, classification and naming finding. Preserve resources created and deleted within the interval as event only candidates rather than current inventory.

## Known limits

- A write event is not sufficient proof of creation, and creation timestamps are not supported uniformly.
- Activity Log caller and deployment history rarely prove portal versus pipeline origin without additional evidence.

## Expected validation cases

- Healthy: resource created inside the interval matches its naming rule and a successful deployment operation.
- Finding: a confirmed new resource violates its supplied naming convention.
- Denied or missing: a write event with no creation timestamp is only a candidate and unknown origin remains null.

## Sources

- [Resources List API with createdTime and changedTime expansion](https://learn.microsoft.com/en-us/rest/api/resources/resources/list?view=rest-resources-2021-04-01) (consulted 2026-10-21).
- [Control plane events and creation evidence](https://learn.microsoft.com/en-us/azure/azure-monitor/fundamentals/activity-log) (consulted 2026-10-21).
- [Subscription deployment operation evidence](https://learn.microsoft.com/en-us/cli/azure/deployment/operation/sub?view=azure-cli-latest) (consulted 2026-10-21).
