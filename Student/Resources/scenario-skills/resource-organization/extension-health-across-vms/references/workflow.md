# Evidence collection and analysis

## Collection

### 1. VM inventory

Retain VM ID, power state and OS. Include only approved resources and report stopped/deallocated VMs whose guest status cannot be refreshed.

```azurecli
az vm list --subscription "<subscription_id>" --show-details --output json
```

### 2. Extension configuration

Read extension publisher, type, version and provisioning state. Do not expose settings or protected settings in customer reports.

```azurecli
az vm extension list --subscription "<subscription_id>" --resource-group "<resource_group>" --vm-name "<vm_name>" --output json
```

### 3. Extension and agent instance health

Preserve handler statuses/substatuses, level, message and timestamps as returned. Redact sensitive stdout or command content before sharing. Collect the VM agent status to distinguish guest communication problems.

```azurecli
az vm extension show --subscription "<subscription_id>" --resource-group "<resource_group>" --vm-name "<vm_name>" --name "<extension_name>" --instance-view --output json
az vm get-instance-view --subscription "<subscription_id>" --resource-group "<resource_group>" --name "<vm_name>" --output json
```

## Analysis rules

1. Flag model provisioningState Failed and runtime handler/substatus error levels separately. A succeeded model does not override a current handler error.
2. For Transitioning, establish duration only using a provider status timestamp with known meaning or observations of the same uninterrupted transition at least one hour apart. A single snapshot cannot establish duration.
3. Where two snapshots are used, report a lower bound of observed transition duration and possible unobserved state changes rather than assert continuous failure without evidence.
4. Check publisher/type/version pairs against the reviewed incompatibility matrix. Without a documented pair report conflict assessment unknown, not a guessed conflict.
5. Correlate agent readiness and VM power state, identify affected VM and extension, and recommend a specific vendor troubleshooting check. Do not uninstall, reapply, restart or execute guest scripts.

## Known limits

- Status timestamps and transitioning duration are not uniformly supplied, so a point in time snapshot cannot prove a one hour transition.
- Guest output can include sensitive content and stopped VMs can expose stale instance views.

## Expected validation cases

- Healthy: succeeded provisioning, ready agent and no error substatus produce Observed.
- Finding: Failed provisioning with a returned handler error reports the VM, extension and redacted error.
- Denied or missing: a single Transitioning snapshot yields duration null, while denied instance view yields Not assessed.

## Sources

- [Extension and VM agent status troubleshooting](https://learn.microsoft.com/en-us/azure/virtual-machines/extensions/troubleshoot) (consulted 2026-10-21).
- [Extension list, show and instance view syntax](https://learn.microsoft.com/en-us/cli/azure/vm/extension?view=azure-cli-latest) (consulted 2026-10-21).
- [Resource read boundaries](https://learn.microsoft.com/en-us/cli/azure/resource?view=azure-cli-latest) (consulted 2026-10-21).
