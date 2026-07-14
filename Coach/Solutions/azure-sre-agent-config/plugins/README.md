# Plugins

Store plugin marketplace and installation manifests here when a plugin is not supported by Terraform or documented AzAPI resource types.

Use `AZ-SRE-Agent-Configuration/plugin-configs/` for `/api/v2/extendedAgent/plugins/{name}` plugin configuration resources.

Expected manifest shape:

```yaml
api_version: azuresre.ai/v1
kind: PluginMarketplace
metadata:
  name: example-marketplace
spec:
  enabled: true
  url: https://example.invalid/plugins
```

Do not commit plugin secrets. Use `${VARIABLE_NAME}` placeholders and inject values through `.env`, CI/CD secrets, or Key Vault-backed release automation.