# Evidence collection and analysis

## Collection

### 1. Accounts and Foundry endpoint inventory

Page using skipToken and --skip-token. Inventory account deployments plus Foundry/ML serverless and online endpoint families when present. ARG child coverage is not guaranteed; record expected providers and independently reconcile account deployment lists. Creation metadata requires authoritative deployment reads, not an assumed ARG systemData column.

```azurecli
az graph query --subscriptions "<subscription_id>" --first 1000 -q "Resources | where type startswith 'microsoft.cognitiveservices/accounts' or type startswith 'microsoft.machinelearningservices/workspaces' | project id, name, type, kind, resourceGroup, subscriptionId, location, sku, properties" --output json
```

### 2. Cognitive Services deployments

Repeat for each approved OpenAI or Foundry account. Retain properties.model.name, version, format, deployment name, SKU, upgrade policy and creation metadata where actually returned. A missing date remains null.

```azurecli
az cognitiveservices account deployment list --subscription "<subscription_id>" --resource-group "<resource_group>" --name "<account_name>" --output json
```

### 3. Authoritative endpoint or deployment details

Select the type's actual supported API version first. Repeat resource reads for inventoried ML online deployments, serverless endpoints and other supported deployment types. Resolve model references only where metadata supports it; unresolved managed endpoint model versions remain unknown.

```azurecli
az provider show --subscription "<subscription_id>" --namespace Microsoft.MachineLearningServices --output json
az resource show --subscription "<subscription_id>" --ids "<resource_id>" --api-version "<api_version>" --output json
```

## Analysis rules

1. Build one record per deployment, including subscription, group, parent account/workspace, deployment name, model name/version, hosting offering, region and creation date if supplied. Do not infer deployment date from an account's creation time.
2. Refresh and archive the official retirement schedule during execution. Match exact model and version plus documented deployment type/region exceptions; never use name only or invent a replacement for an empty schedule cell.
3. Classify Retired when a confirmed retirement date is before assessment_utc, Retiring soon for dates from assessment through 90 days, and Current for confirmed later dates or explicitly confirmed no announced retirement in the applicable schedule.
4. Unmatched offerings, unresolved versions and unavailable schedules are Not assessed, not Current. Third party and self hosted models require their own authoritative lifecycle source.
5. Compute days_until_retirement from UTC dates, retaining negative values for retired versions. Recommend only the replacement stated in the source, otherwise null, and require compatibility, availability and quota testing before migration.
6. Summarize total deployment counts by lifecycle including unknown, alongside coverage per provider and offering. The catalog source date is not a promise that the schedule will remain current.

## Known limits

- Foundry offerings do not all expose identical ARM metadata or use the OpenAI retirement schedule.
- Retirement dates, replacements and regional exceptions change; rerun official source verification at assessment time.

## Expected validation cases

- Healthy: exact scheduled model/version with retirement 200 days away is Current.
- Finding: exact model/version with a confirmed retirement in 30 days is Retiring soon with the documented replacement or null.
- Denied or missing: inaccessible deployment list, unresolved version or unmatched offering remains Not assessed.

## Sources

- [Cognitive Services deployment inventory](https://learn.microsoft.com/en-us/cli/azure/cognitiveservices/account/deployment?view=azure-cli-latest) (consulted 2026-10-21).
- [Official Foundry model retirement schedule](https://learn.microsoft.com/en-us/azure/foundry-classic/openai/concepts/model-retirement-schedule) (consulted 2026-10-21).
- [Authoritative provider resource reads](https://learn.microsoft.com/en-us/cli/azure/resource?view=azure-cli-latest) (consulted 2026-10-21).
- [Deployment discovery and paging](https://learn.microsoft.com/en-us/cli/azure/graph?view=azure-cli-latest) (consulted 2026-10-21).
