# VM Health Control

Simulates VM health state changes by sending fake unhealthy/healthy log entries to a custom Log Analytics table. No actual VM changes are made — this is purely a log-generation tool for SRE observability demos.

## Configuration

| Variable | Default | Description |
|---|---|---|
| `PORT` | `3095` | HTTP listen port |
| `LOG_ANALYTICS_WORKSPACE_ID` | _(empty)_ | Log Analytics workspace ID |
| `LOG_ANALYTICS_SHARED_KEY` | _(empty)_ | Log Analytics primary/secondary key |
| `LOG_TYPE` | `VMHealthStatus` | Custom log table name (appears as `VMHealthStatus_CL`) |
| `AZURE_SUBSCRIPTION_ID` | `demo-subscription` | Included in log entries |

If `LOG_ANALYTICS_WORKSPACE_ID` is not set the service still works but logs are printed to stdout (dry-run mode).

## API

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Health check |
| `GET` | `/api/vm-health/state` | Current state of all VMs |
| `PATCH` | `/api/vm-health/:vmName` | Set VM healthy/unhealthy (`{ "healthy": false }`) |

Valid VM names: `madrid`, `paris`.

## Local development

```bash
npm install
npm start
```
