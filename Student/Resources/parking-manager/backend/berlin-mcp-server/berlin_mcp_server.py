from mcp.server.fastmcp import FastMCP
import httpx
import json
import logging
from datetime import datetime
from opencensus.ext.azure.log_exporter import AzureLogHandler
import os
import uvicorn
import secrets
from fastapi import Request, HTTPException, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp, Scope, Receive, Send

# Configuration
BERLIN_API_URL = os.getenv("BERLIN_API_URL", "https://ca-parking-berlin.braveocean-195c6009.swedencentral.azurecontainerapps.io")
APPINSIGHTS_CONNECTION = os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING")
MCP_AUTH_TOKEN = os.getenv("MCP_AUTH_TOKEN")  # Bearer token for authentication

# Setup Application Insights logging
logger = logging.getLogger(__name__)
if APPINSIGHTS_CONNECTION:
    logger.addHandler(AzureLogHandler(connection_string=APPINSIGHTS_CONNECTION))
    logger.setLevel(logging.INFO)

# Configure FastMCP without transport security settings
# DNS rebinding protection not needed - authentication via MCP_AUTH_TOKEN provides security
# Azure Container Apps provides network-level security (WAF, DDoS protection)
#
# Previous approach using TransportSecuritySettings with enable_dns_rebinding_protection=False
# caused silent startup failures. Since DNS rebinding protection is disabled anyway,
# we don't need TransportSecuritySettings at all.
#
# Security is provided by:
# - Bearer token authentication (MCP_AUTH_TOKEN) enforced by BearerTokenAuthMiddleware
# - Azure Container Apps network-level security (WAF, DDoS protection)
# - This is an internal monitoring tool within Azure infrastructure
# stateless_http=True: each POST is handled independently without requiring
# the mcp-session-id header round-trip. Required for Azure Container Apps which
# strips custom response headers (including mcp-session-id) at the ingress layer,
# preventing session continuity.
app = FastMCP("berlin-monitoring", stateless_http=True)

# Track MCP server metrics
class MCPMetrics:
    def __init__(self):
        self.tool_calls = {}
        self.errors = {}
        self.response_times = {}
    
    def track_call(self, tool_name: str, duration_ms: float, success: bool):
        if tool_name not in self.tool_calls:
            self.tool_calls[tool_name] = 0
            self.errors[tool_name] = 0
            self.response_times[tool_name] = []
        
        self.tool_calls[tool_name] += 1
        if not success:
            self.errors[tool_name] += 1
        self.response_times[tool_name].append(duration_ms)
        
        if APPINSIGHTS_CONNECTION:
            logger.info(f"MCP Tool Call: {tool_name}", extra={
                'custom_dimensions': {
                    'tool': tool_name,
                    'duration_ms': duration_ms,
                    'success': success,
                    'target_api': 'berlin-parking'
                }
            })

metrics = MCPMetrics()

# Authentication Middleware
class BearerTokenAuthMiddleware(BaseHTTPMiddleware):
    """Middleware to validate Bearer token for MCP endpoints"""
    
    def __init__(self, app):
        super().__init__(app)
        # Per-worker warning flag (intentional: each worker logs once)
        self._logged_no_token_warning = False
    
    async def dispatch(self, request: Request, call_next):
        # Skip auth for health endpoint (needed for Container App probes)
        if request.url.path == "/health":
            return await call_next(request)
        
        # Skip auth for startup endpoint (needed for Container App startup probe)
        if request.url.path == "/startup":
            return await call_next(request)
        
        # Skip auth for root endpoint (for discovery)
        if request.url.path == "/":
            return await call_next(request)
        
        # If MCP_AUTH_TOKEN is not set, allow all requests (backward compatibility)
        if not MCP_AUTH_TOKEN:
            if not self._logged_no_token_warning:
                logger.warning("MCP_AUTH_TOKEN not set - authentication disabled")
                self._logged_no_token_warning = True
            return await call_next(request)
        
        # Check Authorization header for protected endpoints
        auth_header = request.headers.get("Authorization")
        
        if not auth_header:
            # Log client IP for security monitoring (retained per Application Insights retention policy)
            logger.warning(f"Missing Authorization header from {request.client.host}")
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"error": "Missing Authorization header"},
                headers={"WWW-Authenticate": "Bearer"}
            )
        
        # Validate Bearer token
        if not auth_header.startswith("Bearer "):
            logger.warning(f"Invalid Authorization header format from {request.client.host}")
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"error": "Invalid Authorization header format. Expected: Bearer <token>"},
                headers={"WWW-Authenticate": "Bearer"}
            )
        
        # Extract token after "Bearer " prefix (Python 3.9+)
        token = auth_header.removeprefix("Bearer ")
        
        # Check if token is empty
        if not token:
            logger.warning(f"Empty token from {request.client.host}")
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"error": "Token cannot be empty"},
                headers={"WWW-Authenticate": "Bearer"}
            )
        
        # Compare tokens using constant-time comparison
        # secrets.compare_digest handles length mismatches gracefully (returns False)
        try:
            if not secrets.compare_digest(token, MCP_AUTH_TOKEN):
                logger.warning(f"Invalid token from {request.client.host}")
                return JSONResponse(
                    status_code=status.HTTP_403_FORBIDDEN,
                    content={"error": "Invalid authentication token"}
                )
        except TypeError:
            # Handle edge case where token types differ
            logger.warning(f"Invalid token type from {request.client.host}")
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={"error": "Invalid authentication token"}
            )
        
        # Token is valid, proceed with request
        if APPINSIGHTS_CONNECTION:
            logger.info(f"Authenticated request to {request.url.path}")
        
        return await call_next(request)

@app.tool()
async def check_health() -> str:
    """Check if the Berlin parking API is healthy and responding"""
    start = datetime.now()
    success = False
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{BERLIN_API_URL}/health")
            data = response.json()
            success = response.status_code == 200
            
            status_emoji = "✅" if data['status'] == 'healthy' else "❌"
            result = f"""
{status_emoji} Berlin API Health Status:
- Status: {data['status']}
- Service: {data['service']}
- City: {data['city']}
- Uptime: {data['uptime']} seconds
- Last checked: {data['timestamp']}
- Response time: {(datetime.now() - start).total_seconds() * 1000:.0f}ms
"""
            return result
    except Exception as e:
        if APPINSIGHTS_CONNECTION:
            logger.error(f"Health check failed: {e}")
        return f"❌ Berlin API is UNREACHABLE: {str(e)}"
    finally:
        duration_ms = (datetime.now() - start).total_seconds() * 1000
        metrics.track_call("check_health", duration_ms, success)

@app.tool()
async def get_metrics_summary() -> str:
    """Get current parking and performance metrics summary"""
    start = datetime.now()
    success = False
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{BERLIN_API_URL}/api/parking/metrics")
            data = response.json()['data']
            success = response.status_code == 200
            
            return f"""
Berlin Parking Metrics:
- Total Slots: {data['totalSlots']}
- Available: {data['totalAvailable']}
- Occupied: {data['totalOccupied']}
- Occupancy Rate: {data['occupancyRate']}%
- Electric Chargers: {data['availableElectricChargers']}
- Last Updated: {data['lastUpdated']}
"""
    except Exception as e:
        if APPINSIGHTS_CONNECTION:
            logger.error(f"Metrics fetch failed: {e}")
        return f"❌ Failed to fetch metrics: {str(e)}"
    finally:
        duration_ms = (datetime.now() - start).total_seconds() * 1000
        metrics.track_call("get_metrics_summary", duration_ms, success)

@app.tool()
async def get_performance_metrics() -> str:
    """Get detailed OpenTelemetry performance metrics for SRE analysis"""
    start = datetime.now()
    success = False
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{BERLIN_API_URL}/metrics/opentelemetry")
            otel_data = response.json()
            success = response.status_code == 200
            
            # Extract key metrics
            metrics_data = {}
            for scope_metric in otel_data['resourceMetrics'][0]['scopeMetrics']:
                for metric in scope_metric['metrics']:
                    metrics_data[metric['name']] = metric
            
            # Parse critical SRE metrics
            response_time = metrics_data.get('http.server.duration.avg', {}).get('gauge', {}).get('dataPoints', [{}])[0].get('asDouble', 0)
            p95 = metrics_data.get('http.server.duration.p95', {}).get('gauge', {}).get('dataPoints', [{}])[0].get('asDouble', 0)
            p99 = metrics_data.get('http.server.duration.p99', {}).get('gauge', {}).get('dataPoints', [{}])[0].get('asDouble', 0)
            request_count = metrics_data.get('http.server.request.count', {}).get('sum', {}).get('dataPoints', [{}])[0].get('asInt', 0)
            error_rate = metrics_data.get('http.server.error.rate', {}).get('gauge', {}).get('dataPoints', [{}])[0].get('asDouble', 0)
            requests_per_min = metrics_data.get('http.server.requests_per_minute', {}).get('gauge', {}).get('dataPoints', [{}])[0].get('asInt', 0)
            
            return f"""
Berlin API Performance Metrics:
📊 Response Time:
- Average: {response_time:.2f}ms
- P95: {p95:.2f}ms
- P99: {p99:.2f}ms

📈 Throughput:
- Total Requests: {request_count}
- Requests/min: {requests_per_min}

❌ Errors:
- Error Rate: {error_rate:.2f}%
"""
    except Exception as e:
        if APPINSIGHTS_CONNECTION:
            logger.error(f"Performance metrics fetch failed: {e}")
        return f"❌ Failed to fetch performance metrics: {str(e)}"
    finally:
        duration_ms = (datetime.now() - start).total_seconds() * 1000
        metrics.track_call("get_performance_metrics", duration_ms, success)

@app.tool()
async def check_slo_compliance(p95_threshold_ms: float = 100.0, error_rate_threshold: float = 1.0) -> str:
    """Check if the Berlin API meets SLO thresholds"""
    start = datetime.now()
    success = False
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{BERLIN_API_URL}/metrics/opentelemetry")
            otel_data = response.json()
            success = response.status_code == 200
            
            # Extract metrics
            metrics_data = {}
            for scope_metric in otel_data['resourceMetrics'][0]['scopeMetrics']:
                for metric in scope_metric['metrics']:
                    metrics_data[metric['name']] = metric
            
            p95 = metrics_data.get('http.server.duration.p95', {}).get('gauge', {}).get('dataPoints', [{}])[0].get('asDouble', 0)
            error_rate = metrics_data.get('http.server.error.rate', {}).get('gauge', {}).get('dataPoints', [{}])[0].get('asDouble', 0)
            availability = metrics_data.get('system.availability', {}).get('gauge', {}).get('dataPoints', [{}])[0].get('asDouble', 100)
            
            # Check SLOs
            p95_ok = p95 <= p95_threshold_ms
            error_ok = error_rate <= error_rate_threshold
            avail_ok = availability >= 99.9
            
            status = "✅ PASSING" if (p95_ok and error_ok and avail_ok) else "❌ FAILING"
            
            # Log SLO check result
            if APPINSIGHTS_CONNECTION:
                logger.warning(f"SLO Check: {status}", extra={
                    'custom_dimensions': {
                        'slo_status': status,
                        'p95': p95,
                        'error_rate': error_rate,
                        'availability': availability
                    }
                })
            
            return f"""
SLO Compliance Check - {status}

Performance SLO:
- P95 Response Time: {p95:.2f}ms (threshold: {p95_threshold_ms}ms) {'✅' if p95_ok else '❌'}
- Error Rate: {error_rate:.2f}% (threshold: {error_rate_threshold}%) {'✅' if error_ok else '❌'}
- Availability: {availability:.2f}% (threshold: 99.9%) {'✅' if avail_ok else '❌'}

{'⚠️ Action Required: SLOs are not being met!' if not (p95_ok and error_ok and avail_ok) else '✅ All SLOs are being met'}
"""
    except Exception as e:
        if APPINSIGHTS_CONNECTION:
            logger.error(f"SLO check failed: {e}")
        return f"❌ Failed to check SLO compliance: {str(e)}"
    finally:
        duration_ms = (datetime.now() - start).total_seconds() * 1000
        metrics.track_call("check_slo_compliance", duration_ms, success)

@app.tool()
async def get_level_status() -> str:
    """Get parking occupancy status by level"""
    start = datetime.now()
    success = False
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{BERLIN_API_URL}/api/parking/levels")
            levels = response.json()['data']
            success = response.status_code == 200
            
            result = "Berlin Parking Levels:\n"
            for level in levels:
                result += f"\n- Level {level['level']}: {level['availableSlots']}/{level['totalSlots']} available ({level['occupancyRate']}% occupied)"
            
            return result
    except Exception as e:
        if APPINSIGHTS_CONNECTION:
            logger.error(f"Level status fetch failed: {e}")
        return f"❌ Failed to fetch level status: {str(e)}"
    finally:
        duration_ms = (datetime.now() - start).total_seconds() * 1000
        metrics.track_call("get_level_status", duration_ms, success)

@app.tool()
async def get_mcp_server_stats() -> str:
    """Get statistics about the MCP server itself (meta-monitoring)"""
    result = "MCP Server Statistics:\n\n"
    for tool_name, count in metrics.tool_calls.items():
        errors = metrics.errors.get(tool_name, 0)
        avg_time = sum(metrics.response_times[tool_name]) / len(metrics.response_times[tool_name]) if metrics.response_times[tool_name] else 0
        result += f"- {tool_name}: {count} calls, {errors} errors, avg {avg_time:.0f}ms\n"
    return result

if __name__ == "__main__":
    from contextlib import asynccontextmanager
    from fastapi import FastAPI
    from fastapi.responses import JSONResponse
    
    if APPINSIGHTS_CONNECTION:
        logger.info("MCP Server starting", extra={'custom_dimensions': {'service': 'berlin-mcp-server'}})
    
    # Log authentication status
    if MCP_AUTH_TOKEN:
        print("✅ Starting Berlin MCP Monitoring Server on port 8080 with authentication enabled")
        logger.info("Authentication enabled", extra={'custom_dimensions': {'auth': 'bearer-token'}})
    else:
        print("⚠️  WARNING: Starting Berlin MCP Monitoring Server on port 8080 WITHOUT authentication")
        logger.warning("Authentication disabled - MCP_AUTH_TOKEN not set")
    
    # Get the MCP Streamable-HTTP ASGI app in stateless mode.
    # stateless_http=True is set on the FastMCP constructor above.
    mcp_http_app = app.streamable_http_app()

    # Flag to track whether the MCP session manager has been initialized
    _server_ready = False

    # Lifespan: start/stop the MCP session manager alongside FastAPI
    @asynccontextmanager
    async def lifespan(fastapi_app: FastAPI):
        global _server_ready
        async with mcp_http_app.router.lifespan_context(fastapi_app):
            _server_ready = True
            yield
        _server_ready = False

    # Create main FastAPI app with the lifespan that starts MCP session manager
    main_app = FastAPI(title="Berlin MCP Monitoring Server", lifespan=lifespan)
    
    # Add authentication middleware
    main_app.add_middleware(BearerTokenAuthMiddleware)
    
    # Define tool names for consistent reporting
    TOOL_NAMES = [
        "check_health",
        "get_metrics_summary",
        "get_performance_metrics",
        "check_slo_compliance",
        "get_level_status",
        "get_mcp_server_stats"
    ]
    
    # Add health endpoint
    @main_app.get("/health")
    async def health():
        """Health check endpoint for Container App probes.
        Returns 503 until MCP session manager is initialized."""
        if not _server_ready:
            return JSONResponse(
                status_code=503,
                content={
                    "status": "starting",
                    "service": "berlin-mcp-server",
                    "mcp_ready": False,
                    "timestamp": datetime.now().isoformat(),
                }
            )
        return JSONResponse({
            "status": "healthy",
            "service": "berlin-mcp-server",
            "timestamp": datetime.now().isoformat(),
            "mcp_tools": len(TOOL_NAMES),
            "mcp_ready": _server_ready,
            "target_api": BERLIN_API_URL,
            "auth_enabled": bool(MCP_AUTH_TOKEN)
        })
    
    # Add startup endpoint
    @main_app.get("/startup")
    async def startup_check():
        """Startup check endpoint - returns 200 as soon as uvicorn is running.
        Used by Container App startup probe only."""
        return JSONResponse({
            "status": "starting",
            "service": "berlin-mcp-server",
            "timestamp": datetime.now().isoformat()
        })
    
    # Add root endpoint with info (public - for discovery)
    @main_app.get("/")
    async def root():
        """Root endpoint with server information"""
        return JSONResponse({
            "service": "Berlin MCP Monitoring Server",
            "version": "1.0.0",
            "protocol": "MCP",
            "auth_enabled": bool(MCP_AUTH_TOKEN),
            "endpoints": {
                "health": "/health",
                "startup": "/startup",
                "mcp_endpoint": "/mcp"
            },
            "tools": TOOL_NAMES,
            "note": "MCP endpoint at /mcp using Streamable-HTTP transport"
        })
    
    # Create a routing ASGI middleware that intercepts /mcp requests
    # and passes them directly to MCP app with clean scope
    class MCPRoutingMiddleware:
        """Middleware that routes /mcp requests to MCP app bypassing FastAPI routing"""
        def __init__(self, app: ASGIApp, mcp_app: ASGIApp):
            self.app = app
            self.mcp_app = mcp_app
        
        async def check_auth(self, scope: Scope) -> tuple[bool, dict]:
            """Check authentication for /mcp requests. Returns (is_authed, error_response)"""
            # If MCP_AUTH_TOKEN is not set, allow all requests
            if not MCP_AUTH_TOKEN:
                return True, {}
            
            # Get Authorization header - use strict decoding to detect malformed headers
            try:
                headers_dict = {k.decode('utf-8'): v.decode('utf-8') 
                               for k, v in scope.get("headers", [])}
                auth_header = headers_dict.get("authorization", "")
            except UnicodeDecodeError:
                logger.warning("Malformed UTF-8 in request headers")
                return False, {
                    "status": 400,
                    "headers": [[b"content-type", b"application/json"]],
                    "body": b'{"error": "Malformed request headers"}'
                }
            
            # Check if Authorization header exists
            if not auth_header:
                client_host = scope.get("client", ("unknown",))[0]
                logger.warning(f"Missing Authorization header from {client_host}")
                return False, {
                    "status": 401,
                    "headers": [[b"content-type", b"application/json"], [b"www-authenticate", b"Bearer"]],
                    "body": b'{"error": "Missing Authorization header"}'
                }
            
            # Validate Bearer token format
            if not auth_header.startswith("Bearer "):
                return False, {
                    "status": 401,
                    "headers": [[b"content-type", b"application/json"], [b"www-authenticate", b"Bearer"]],
                    "body": b'{"error": "Invalid Authorization header format. Expected: Bearer <token>"}'
                }
            
            # Extract and validate token
            token = auth_header[7:]  # Remove "Bearer " prefix
            if not token:
                return False, {
                    "status": 403,
                    "headers": [[b"content-type", b"application/json"]],
                    "body": b'{"error": "Invalid authentication token"}'
                }
            
            # Compare tokens using constant-time comparison
            # Both token and MCP_AUTH_TOKEN are strings at this point
            if not secrets.compare_digest(token, MCP_AUTH_TOKEN):
                return False, {
                    "status": 403,
                    "headers": [[b"content-type", b"application/json"]],
                    "body": b'{"error": "Invalid authentication token"}'
                }
            
            # Token is valid
            if APPINSIGHTS_CONNECTION:
                logger.info(f"Authenticated request to {scope['path']}")
            return True, {}
        
        async def send_error(self, send: Send, error_response: dict):
            """Send error response"""
            await send({
                "type": "http.response.start",
                "status": error_response["status"],
                "headers": error_response["headers"],
            })
            await send({
                "type": "http.response.body",
                "body": error_response["body"],
            })
        
        async def __call__(self, scope: Scope, receive: Receive, send: Send):
            # Forward lifespan events to FastAPI app so that the MCP session manager
            # task group is properly initialized on startup
            if scope["type"] == "lifespan":
                return await self.app(scope, receive, send)

            # Only intercept HTTP requests to /mcp
            if scope["type"] == "http" and scope["path"] == "/mcp":
                # Check authentication first
                is_authed, error_response = await self.check_auth(scope)
                if not is_authed:
                    return await self.send_error(send, error_response)
                
                # Create clean scope for MCP app
                # Streamable-HTTP uses POST natively, keep original method
                # Rewrite host header to localhost:8080 to satisfy FastMCP's DNS rebinding
                # protection, which validates that Host is localhost/loopback.
                # The external FQDN would cause FastMCP to return 421 Misdirected Request.
                rewritten_headers = [
                    (k, b"localhost:8080") if k.lower() == b"host" else (k, v)
                    for k, v in scope["headers"]
                ]
                clean_scope = {
                    "type": scope["type"],
                    "asgi": scope["asgi"],
                    "http_version": scope["http_version"],
                    "method": scope["method"],  # Keep original method (POST for Streamable-HTTP)
                    "scheme": scope["scheme"],
                    "path": "/mcp",
                    "query_string": scope["query_string"],
                    "root_path": scope.get("root_path", ""),
                    "headers": rewritten_headers,  # Host rewritten to localhost:8080
                    "server": scope.get("server"),
                    "client": scope.get("client"),
                    "extensions": scope.get("extensions", {}),
                }
                
                # Log the request for debugging
                if APPINSIGHTS_CONNECTION and logger.isEnabledFor(logging.INFO):
                    logger.info(f"Routing {scope['method']} request to /mcp endpoint")
                
                # Pass to MCP app with clean scope
                return await self.mcp_app(clean_scope, receive, send)
            
            # Pass other requests to FastAPI
            return await self.app(scope, receive, send)
    
    # Create the routing middleware wrapping the MCP app
    main_app_with_mcp = MCPRoutingMiddleware(main_app, mcp_http_app)
    
    # Run the combined app (with MCP routing middleware)
    uvicorn.run(main_app_with_mcp, host="0.0.0.0", port=8080, log_level="info")
