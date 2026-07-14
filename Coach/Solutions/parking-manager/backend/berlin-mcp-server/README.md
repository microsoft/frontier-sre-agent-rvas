# Berlin MCP Monitoring Server

A Model Context Protocol (MCP) server that provides monitoring and observability tools for the Berlin Parking API. This server acts as an integration layer between Azure SRE agents and the Berlin API.

## Purpose

The Berlin API represents an **external/third-party service** that you don't directly control or monitor. This MCP server:
- Lives in its own resource group (`rg-parking-berlin-mcp-dev`) 
- Provides tools for SRE agents to query the Berlin API
- Logs its own performance to Application Insights
- Allows SRE to monitor YOUR integration infrastructure, not the external API

## Architecture

```
Azure SRE Agent → MCP Server (rg-parking-berlin-mcp-dev) → Berlin API (rg-parking-berlin-dev)
                  [YOU MONITOR THIS]                       [EXTERNAL - NO MONITORING]
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
| **Authentication Method** | `Bearer Token` |
| **Token** | `your-token-from-github-secret` |

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

### Setting the Token in Azure Container App

```bash
# Update Container App with the token
az containerapp update \
  --name ca-berlin-mcp \
  --resource-group rg-parking-berlin-mcp-dev \
  --set-env-vars "MCP_AUTH_TOKEN=your-generated-token-here"
```

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

This is acceptable because:
- ✅ **Authentication is enabled** via `MCP_AUTH_TOKEN` (Bearer token)
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

## Deployment

The MCP server is deployed as an **Azure Container App**.

### Resource Names
- **Resource Group**: `rg-parking-berlin-mcp-dev`
- **Container App Environment**: `cae-berlin-mcp`
- **Container App**: `ca-berlin-mcp`
- **Log Analytics**: `law-berlin-mcp`
- **Application Insights**: `appi-parking-berlin-mcp`

### GitHub Actions Deployment

The MCP server is automatically deployed via GitHub Actions when code is pushed to the `main` branch.

#### Required GitHub Secrets

1. **`AZURE_CREDENTIALS`** - Azure service principal credentials
   ```json
   {
     "clientId": "...",
     "clientSecret": "...",
     "subscriptionId": "...",
     "tenantId": "..."
   }
   ```

2. **`MCP_AUTH_TOKEN`** - Bearer token for authentication (recommended)
   ```bash
   # Generate a secure token
   openssl rand -base64 32
   ```

#### Setting GitHub Secrets

1. Go to your repository → **Settings** → **Secrets and variables** → **Actions**
2. Click **New repository secret**
3. Name: `MCP_AUTH_TOKEN`
4. Value: Your generated token (from the command above)
5. Click **Add secret**

#### Required GitHub Variables

1. **`AZURE_CONTAINER_REGISTRY`** - Name of your Azure Container Registry
   - Example: `acrparkingdev`
   - Set in: Repository → Settings → Variables → Actions

#### Verifying Deployment

After deployment, check that authentication is enabled:

```powershell
# Check health endpoint
Invoke-RestMethod "https://ca-berlin-mcp.ashyriver-65b8d9ff.swedencentral.azurecontainerapps.io/health"

# Should return:
# {
#   "status": "healthy",
#   "auth_enabled": true  ← Should be true
# }
```

#### Security Best Practices

- ✅ Always use GitHub **Secrets** (not Variables) for tokens
- ✅ Rotate the `MCP_AUTH_TOKEN` periodically
- ✅ Use a cryptographically secure random token (at least 32 bytes)
- ✅ Never commit tokens to source control
- ✅ Use different tokens for different environments (dev/prod)

### Manual Deployment

If you need to deploy manually (outside of GitHub Actions):

```bash
# Set environment variables
export RESOURCE_GROUP="rg-parking-berlin-mcp-dev"
export CONTAINER_APP_NAME="ca-berlin-mcp"
export IMAGE_TAG="your-registry.azurecr.io/berlin-mcp-server:latest"
export BERLIN_API_URL="https://ca-parking-berlin..."
export APPINSIGHTS_CONNECTION="InstrumentationKey=..."
export MCP_AUTH_TOKEN="your-generated-token"

# Update Container App
az containerapp update \
  --name $CONTAINER_APP_NAME \
  --resource-group $RESOURCE_GROUP \
  --image $IMAGE_TAG \
  --set-env-vars \
    "BERLIN_API_URL=$BERLIN_API_URL" \
    "APPLICATIONINSIGHTS_CONNECTION_STRING=$APPINSIGHTS_CONNECTION" \
    "MCP_AUTH_TOKEN=$MCP_AUTH_TOKEN"
```

### Infrastructure Deployment

```bash
# Deploy infrastructure
az deployment group create \
  --resource-group rg-parking-berlin-mcp-dev \
  --template-file infrastructure/modules/berlin-mcp-server.bicep \
  --parameters \
    location=swedencentral \
    environment=dev \
    berlinApiUrl=https://ca-parking-berlin.braveocean-195c6009.swedencentral.azurecontainerapps.io \
    containerImage=<your-image>
```

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
