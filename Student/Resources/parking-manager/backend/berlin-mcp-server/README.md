# Berlin MCP Monitoring Server

A Model Context Protocol (MCP) server that provides monitoring and observability tools for the Berlin Parking API. This server acts as an integration layer between Azure SRE agents and the Berlin API.

## Purpose

The Berlin API represents a simulated **external/third-party service** that you don't directly control or monitor. This MCP server:
- Runs in the workshop resource group `rg-sre-parking-berlin`
- Provides tools for SRE agents to query the Berlin API
- Exports its performance logs to Application Insights when a connection string is configured
- Allows SRE to monitor YOUR integration infrastructure, not the external API

## Architecture

```
Azure SRE Agent → MCP Server (ca-berlin-mcp) → Berlin API (simulated external dependency)
                  [YOU MONITOR THIS]          [OBSERVED THROUGH THE MCP SERVER]
```

## Endpoints

The MCP server exposes the following HTTP endpoints:

### `GET /health`
Health check endpoint for Container App probes and monitoring.

**Response:**
```json
{
  "status": "healthy",
  "service": "berlin-mcp-server",
  "timestamp": "2026-02-16T15:50:00.000Z",
  "mcp_tools": 6,
  "target_api": "https://ca-parking-berlin..."
}
```

### `GET /`
Root endpoint with server information and available tools.

**Response:**
```json
{
  "service": "Berlin MCP Monitoring Server",
  "version": "1.0.0",
  "protocol": "MCP",
  "endpoints": {
    "health": "/health",
    "mcp_endpoint": "/mcp"
  },
  "tools": ["check_health", "get_metrics_summary", ...]
}
```

### `POST /mcp`
MCP protocol endpoint using Streamable-HTTP transport (MCP spec 2025-03-26).
Accepts JSON-RPC messages for initialize, tools/list, and tool calls.
Used by MCP clients to communicate with the server.

## MCP Connector Configuration

Configure your Azure SRE Agent MCP connector with the following settings:

| Field | Value |
|-------|-------|
| **Name** | `berlin-monitoring` |
| **Connection Type** | `Streamable-HTTP` |
| **URL** | `https://ca-berlin-mcp.ashyriver-65b8d9ff.swedencentral.azurecontainerapps.io/mcp` |
| **Authentication Method** | `None` for the default lab; `Bearer Token` when the Terraform secret input is configured |
| **Token** | Supplied through the approved Terraform secret input; never from a repository secret |

### Testing the MCP Endpoint

Test the endpoint with a JSON-RPC initialize request:

```bash
TOKEN="your-token-here"

# Test the MCP endpoint with initialize request
curl -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
      "protocolVersion": "2024-11-05",
      "capabilities": {},
      "clientInfo": {
        "name": "test-client",
        "version": "1.0.0"
      }
    }
  }' \
  https://ca-berlin-mcp.ashyriver-65b8d9ff.swedencentral.azurecontainerapps.io/mcp

# Test tools/list request
curl -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 2,
    "method": "tools/list",
    "params": {}
  }' \
  https://ca-berlin-mcp.ashyriver-65b8d9ff.swedencentral.azurecontainerapps.io/mcp
```

## Available Tools

The MCP server exposes these tools that SRE agents can call:

### 1. `check_health`
Check if the Berlin parking API is healthy and responding.

### 2. `get_metrics_summary`
Get current parking and performance metrics summary (occupancy, slots, etc.).

### 3. `get_performance_metrics`
Get detailed OpenTelemetry performance metrics (response times, throughput, errors).

### 4. `check_slo_compliance`
Check if the Berlin API meets SLO thresholds.
- Parameters:
  - `p95_threshold_ms` (float): P95 response time threshold in milliseconds (default: 100.0)
  - `error_rate_threshold` (float): Error rate threshold percentage (default: 1.0)

### 5. `get_level_status`
Get parking occupancy status by level.

### 6. `get_mcp_server_stats`
Get statistics about the MCP server itself (meta-monitoring).

## Environment Variables

- `BERLIN_API_URL` - URL of the Berlin Parking API
- `APPLICATIONINSIGHTS_CONNECTION_STRING` - Application Insights connection string for logging
- `MCP_AUTH_TOKEN` - Bearer token for authentication (optional, but recommended for production)

## Authentication

The MCP server supports **Bearer Token authentication** to secure the MCP endpoints.

### Environment Variable

Set the `MCP_AUTH_TOKEN` environment variable to enable authentication:

```bash
export MCP_AUTH_TOKEN="your-secret-token-here"
```

### Protected Endpoints

- ✅ `/mcp` - MCP protocol endpoint (requires authentication)
- ❌ `/health` - Health check (public, no auth required)
- ❌ `/` - Server info (public, for discovery)

### MCP Client Configuration

Configure your MCP client with Bearer Token authentication:

```json
{
  "mcpServers": {
    "berlin-monitoring": {
      "url": "https://ca-berlin-mcp.ashyriver-65b8d9ff.swedencentral.azurecontainerapps.io/mcp",
      "transport": "streamable-http",
      "headers": {
        "Authorization": "Bearer your-secret-token-here"
      }
    }
  }
}
```

### Testing Authentication

**Without token (should fail):**
```bash
curl -X POST \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
      "protocolVersion": "2024-11-05",
      "capabilities": {},
      "clientInfo": {
        "name": "test-client",
        "version": "1.0.0"
      }
    }
  }' \
  https://ca-berlin-mcp.ashyriver-65b8d9ff.swedencentral.azurecontainerapps.io/mcp
# Expected: 401 Unauthorized
```

**With valid token (should succeed):**
```bash
curl -X POST \
  -H "Authorization: Bearer your-secret-token-here" \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
      "protocolVersion": "2024-11-05",
      "capabilities": {},
      "clientInfo": {
        "name": "test-client",
        "version": "1.0.0"
      }
    }
  }' \
  https://ca-berlin-mcp.ashyriver-65b8d9ff.swedencentral.azurecontainerapps.io/mcp
# Expected: 200 OK with JSON-RPC response
```

**Health endpoint (always public):**
```bash
curl https://ca-berlin-mcp.ashyriver-65b8d9ff.swedencentral.azurecontainerapps.io/health
# Expected: 200 OK (no auth required)
```

### Generating a Secure Token

Generate a cryptographically secure token:

**PowerShell:**
```powershell
# Generate a cryptographically secure random token
$bytes = New-Object Byte[] 32
[Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
$token = [Convert]::ToBase64String($bytes)
Write-Host "MCP_AUTH_TOKEN=$token"
```

**Bash:**
```bash
# Generate a secure random token
openssl rand -base64 32
```

### Configuring the Token in the Workshop

The workshop Terraform resource owns the Container App secret and environment variable. The lab
leaves `berlin_mcp_auth_token` empty by default, which disables authentication for this isolated
exercise. For a secured deployment, inject the token through the approved Terraform secret input
and apply the reviewed Terraform state. Do not update the Container App out of band.

### Security Notes

- ✅ Use a cryptographically secure random token (at least 32 bytes)
- ✅ Store the token securely (Azure Key Vault recommended)
- ✅ Rotate the token periodically
- ⚠️ Never commit the token to source control
- ⚠️ Use HTTPS only (Container App enforces this)

### Backward Compatibility

If `MCP_AUTH_TOKEN` is not set, the server will:
- ⚠️ Log a warning
- ⚠️ Allow all requests (authentication disabled)
- This is for development/testing only - not recommended for production

## Security Configuration

### DNS Rebinding Protection - DISABLED

**Note:** DNS rebinding protection is **disabled** in this deployment because the MCP library's strict Host header validation is incompatible with Azure Container Apps ingress handling.

This is acceptable for this isolated workshop because:
- ✅ **Bearer authentication is available** through `MCP_AUTH_TOKEN` when the Terraform input is configured
- ✅ This is an **internal monitoring tool** within Azure infrastructure
- ✅ Azure Container Apps provides **network-level security** (WAF, DDoS protection)
- ✅ The ingress is already behind Azure's security infrastructure

### Why DNS Rebinding Protection is Disabled

The MCP library validates the ASGI scope's Host header for DNS rebinding protection. However, Azure Container Apps' ingress handling modifies the ASGI scope in ways that fail the MCP library's strict validation, causing "Request validation failed" errors at the MCP endpoint.

Since the server already has multiple layers of security (Bearer token authentication, Azure network security), disabling this specific protection is an acceptable trade-off for Azure Container Apps compatibility.

## Testing

### Test Health Endpoint
```bash
curl https://ca-berlin-mcp.ashyriver-65b8d9ff.swedencentral.azurecontainerapps.io/health
```

### Test Server Info
```bash
curl https://ca-berlin-mcp.ashyriver-65b8d9ff.swedencentral.azurecontainerapps.io/
```

### Connect MCP Client
Configure your MCP client to use the Streamable-HTTP transport:
```json
{
  "mcpServers": {
    "berlin-monitoring": {
      "url": "https://ca-berlin-mcp.ashyriver-65b8d9ff.swedencentral.azurecontainerapps.io/mcp",
      "transport": "streamable-http"
    }
  }
}
```

## Workshop Deployment Ownership

The MCP server runs as the Terraform-owned Azure Container App `ca-berlin-mcp` in resource group
`rg-sre-parking-berlin`. It shares the workshop Container Apps environment and uses the public
image `ghcr.io/microsoft/frontier-sre-agent-rvas/berlin-mcp-server:latest`.

The Parking image workflow builds and publishes this image only when manually dispatched. It does
not sign in to Azure and does not deploy or update the Container App. Terraform remains the single
owner of the image reference, `BERLIN_API_URL`, optional authentication secret, replica settings,
and ingress configuration. Runtime changes must be reviewed and applied through that Terraform
state; no repository-level Azure credentials are required by the image workflow.

## Monitoring

The MCP server logs all tool calls to Application Insights with:
- Tool name
- Duration
- Success/failure status
- Custom dimensions for filtering

Query example in Log Analytics:
```kusto
traces
| where customDimensions.tool != ""
| project timestamp, tool=customDimensions.tool, duration_ms=customDimensions.duration_ms, success=customDimensions.success
| summarize avg(todouble(duration_ms)), count() by tostring(tool)
```
