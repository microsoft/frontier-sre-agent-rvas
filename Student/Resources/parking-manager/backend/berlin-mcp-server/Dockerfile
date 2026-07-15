FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy server code
COPY berlin_mcp_server.py .

# Expose MCP server port
EXPOSE 8080

# Note: Health checks are handled by Container App probes (Startup, Liveness, Readiness)
# Docker HEALTHCHECK is not used to avoid conflicts with platform probes

# Run the MCP server
CMD ["python", "berlin_mcp_server.py"]
