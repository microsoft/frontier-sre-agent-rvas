# Checks catalog

Web tier reliability and security checks from Azure Resource Graph. Missing configuration is explicitly Not assessed, not skipped as a pass. Read the service API where Resource Graph does not expose the required fields.

For each finding the tool records: resource, category, subscription, resource group, the check, a severity, and the recommended change.

## App Service sites (category: App Service)

```
az graph query -q "resources | where type =~ 'microsoft.web/sites' | project name, id, subscriptionId, resourceGroup, kind, properties" --first 1000
```

- HTTPS not enforced (Medium): httpsOnly is false. Fix: set HTTPS Only so HTTP is redirected.
- Minimum TLS below 1.2 (Medium): siteConfig.minTlsVersion is 1.0 or 1.1. Fix: set the minimum TLS version to 1.2.
- Always On disabled (Low, non function apps): siteConfig.alwaysOn is false, so the app cold starts. Fix: enable Always On for a warm app.
- No health check path (Low): the explicit siteConfig.healthCheckPath field is empty. A missing field is Unknown. Review plan support and instance count before configuring a path; a path alone does not prove successful health checks or redundancy.

## App Service plans (category: App Service plan)

```
az graph query -q "resources | where type =~ 'microsoft.web/serverfarms' | project name, id, subscriptionId, resourceGroup, sku, properties" --first 1000
```

- Free or Shared tier (Medium): no SLA and no scale out. Fix: move production workloads to Standard or higher.
- Plan not zone redundant (Low): properties.zoneRedundant is explicitly false. Verify eligible Premium tier, regional support and capacity first. Do not suggest a zone redundancy toggle for every Standard plan.

## Container Apps (category: Container Apps)

```
az graph query -q "resources | where type =~ 'microsoft.app/containerapps' | project name, id, subscriptionId, resourceGroup, properties" --first 1000
```

- Insecure ingress allowed (Medium): configuration.ingress.allowInsecure is true. Fix: disallow insecure ingress so HTTP is not accepted.
- No scale out (Low): template.scale.maxReplicas is 1, so the app cannot scale under load. Fix: raise maxReplicas and set a scale rule.
- Probe types are evaluated per container. One healthy main container does not establish sidecar readiness. Absent explicit Startup, Liveness or Readiness is Unknown until effective revision configuration is read.
- With ingress, the portal adds default probes to the main container when each type is missing, except GPU workload profiles. It does not add these defaults to sidecars. Do not assume portal behavior applies to every API deployment.
- Default TCP probes verify that a port accepts connections, not that application dependencies or business transactions work.

## Verify by hand

```
az webapp show --resource-group <rg> --name <site> --subscription <id> -o jsonc
az webapp config show --resource-group <rg> --name <site> --subscription <id> --query "{alwaysOn:alwaysOn,minTls:minTlsVersion,health:healthCheckPath}"
az containerapp show --resource-group <rg> --name <app> --subscription <id> -o jsonc
```

## Severity

Blast radius and likelihood drive severity. No automatic downgrade based only on names.

## Sources and validation

- [Container Apps probe types and defaults](https://learn.microsoft.com/en-us/azure/container-apps/health-probes), checked 2026-10-21.
- [App Service Health Check](https://learn.microsoft.com/en-us/azure/app-service/monitor-instances-health-check).

Offline regression tests verify per container coverage and missing data behavior. Runtime health, failover and actual platform defaults were not tested on a deployed app.
