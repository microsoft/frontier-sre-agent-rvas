# Azure SRE Demo Manager

A multi-city parking management demo showcasing Azure SRE patterns: containerized services, VM deployments, chaos engineering, and observability integrations.

## Overview

The **Parking Manager** application manages parking facilities across multiple cities (Lisbon, Madrid, Paris, Berlin). Each city runs its own backend API with distinct infrastructure and observability characteristics. A React frontend, served by an Express proxy server, provides a unified management and chaos-control interface.

## Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│           Local development UI  (port 8080)                          │
│         Express Proxy  +  React Parking Manager UI                   │
└──┬──────────┬──────────┬──────────┬──────────┬──────────┬────────────┘
   │          │          │          │          │          │
   ▼          ▼          ▼          ▼          ▼          ▼
/api/      /api/      /api/      /api/    /api/chaos-  /api/vm-
lisbon     madrid     paris      berlin    control    health-control
   │          │          │          │          │          │
   ▼          ▼          ▼          ▼          ▼          ▼
┌──────┐  ┌──────┐  ┌──────┐  ┌──────┐  ┌─────────┐  ┌──────────┐
│Lisbon│  │Madrid│  │Paris │  │Berlin│  │ Chaos   │  │VM Health │
│ API  │  │ API  │  │ API  │  │ API  │  │ Control │  │ Control  │
│Docker│  │ Win  │  │Linux │  │Docker│  │ Docker  │  │  Docker  │
│:3001 │  │ VM   │  │ VM   │  │:3004 │  │ :3090   │  │  :3095   │
│      │  │:3002 │  │:3003 │  │      │  │         │  │          │
└──┬───┘  └──┬───┘  └──┬───┘  └──┬───┘  └─────────┘  └──────────┘
   │          │          │          │
   ▼          ▼          ▼          ▼
Azure Log  Windows    Syslog   OpenTelemetry
Analytics  Event      (Linux)  /metrics
           Viewer
```

The **Berlin MCP Server** (`backend/berlin-mcp-server`) is a separate Model Context Protocol
service that exposes the Berlin API to AI tooling and is deployed as its own Terraform-owned
Container App. The React/Express frontend remains a local development UI; live workshop scenarios
exercise the Terraform-deployed APIs and control services through the Makefile targets.

## Project Structure

```
parking-manager/
├── backend/
│   ├── lisbon-parking-api/       # Lisbon parking API (Docker + Azure Log Analytics)
│   ├── berlin-parking-api/       # Berlin parking API (Docker + OpenTelemetry)
│   ├── madrid-parking-api/       # Madrid parking API (Windows Server + Event Viewer)
│   ├── paris-parking-api/        # Paris parking API (Linux + Syslog)
│   ├── chaos-control/            # Chaos engineering control service (Docker, port 3090)
│   ├── vm-health-control/        # VM health monitoring service (Docker, port 3095)
│   └── berlin-mcp-server/        # MCP server for Berlin API (Python, Docker)
├── frontend/
│   └── parking-manager/          # React frontend + Express proxy server
│       ├── src/                  # React application source
│       ├── server.js             # Express proxy server (serves UI + proxies API calls)
│       └── README.md
└── README.md                     # This file
```

## Features

### Backend APIs (City-Specific)
- **Lisbon API** (port 3001): Containerized Node.js with Azure Log Analytics integration
- **Madrid API** (port 3002): Node.js on Windows Server with Windows Event Viewer logging
- **Paris API** (port 3003): Node.js on Linux with Syslog logging
- **Berlin API** (port 3004): Containerized Node.js with OpenTelemetry metrics
- **RESTful API Design** — Standard HTTP methods for all operations
- **Real-time Parking Data** — Track availability across multiple levels

### Support Services
- **Chaos Control** (port 3090): Injects latency/errors into city APIs for SRE demos
- **VM Health Control** (port 3095): Reports simulated VM health state to the frontend
- **Berlin MCP Server**: Exposes the Berlin API over the Model Context Protocol for AI tooling

### Frontend (Parking Manager)
- **Multi-City Dashboard** — View and manage parking across all cities
- **Chaos Backoffice** — Configure chaos scenarios per city API
- **Real-Time Updates** — Auto-refresh every 30 seconds
- **Express Proxy** — `server.js` proxies all `/api/*` routes to backend services; the UI is served on port 8080

## Quick Start

### One-command local startup

Use the local launcher script to start the full demo stack:

```bash
cd scripts
./start-local-stack.sh
```

This script installs missing dependencies, builds the frontend when needed, and starts the backend services plus the frontend proxy.

### Manual local startup

Use the following manual steps to run the full local stack.

Open **http://localhost:8080** in your browser after starting the backend services and frontend proxy. The Chaos Backoffice panel is available in the UI.

> **Requirements**: Node.js 18+. Docker is not required for a local run.

If you prefer to start services individually:

**Prerequisites**: Node.js 18+, Docker (optional for containerised build), Azure account (optional for Log Analytics)

#### Start backend services

```bash
# Chaos Control (port 3090) — start first so city APIs can connect
cd backend/chaos-control && npm install && npm start

# VM Health Control (port 3095)
cd backend/vm-health-control && npm install && npm start

# City APIs
cd backend/lisbon-parking-api && npm install && npm start   # port 3001
cd backend/madrid-parking-api && npm install && npm start   # port 3002
cd backend/paris-parking-api  && npm install && npm start   # port 3003
cd backend/berlin-parking-api && npm install && npm start   # port 3004
```

> **Note**: On Windows, Madrid API logs to Windows Event Viewer; on Linux/macOS it falls back to console. Paris API logs to Syslog on Linux.

#### Build and start the frontend proxy

```bash
cd frontend/parking-manager
npm install
npm run build                   # Build the React app

# Set API URLs, then start the Express proxy server on port 8080
REACT_APP_LISBON_API_URL=http://localhost:3001 \
REACT_APP_MADRID_API_URL=http://localhost:3002 \
REACT_APP_PARIS_API_URL=http://localhost:3003  \
REACT_APP_BERLIN_API_URL=http://localhost:3004 \
REACT_APP_CHAOS_CONTROL_URL=http://localhost:3090 \
REACT_APP_VM_HEALTH_CONTROL_URL=http://localhost:3095 \
PORT=8080 node server.js
```

Open **http://localhost:8080**.

## Docker Deployment

### Build and run a city API container (example: Lisbon)

```bash
cd backend/lisbon-parking-api
docker build -t lisbon-parking-api .
docker run -p 3001:3001 \
  -e PARKING_CITY="Lisbon" \
  lisbon-parking-api
```

Optionally pass Azure Log Analytics credentials:
```bash
docker run -p 3001:3001 \
  -e WORKSPACE_ID=<your-workspace-id> \
  -e SHARED_KEY=<your-shared-key> \
  -e PARKING_CITY="Lisbon" \
  lisbon-parking-api
```

## API Documentation

### City Parking APIs

All four city APIs (`/api/lisbon`, `/api/madrid`, `/api/paris`, `/api/berlin`) expose the same set of endpoints. The frontend proxies requests through these paths via `server.js`.

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Health check |
| `GET` | `/api/parking` | Full parking information |
| `GET` | `/api/parking/metrics` | Metrics summary |
| `GET` | `/api/parking/dependency` | Dependency health check (where supported) |
| `GET` | `/api/parking/levels` | All parking levels |
| `GET` | `/api/parking/levels/:levelNumber` | Single level details |
| `PATCH` | `/api/parking/levels/:levelNumber` | Update available slots |
| `PUT` | `/api/parking/config` | Update parking configuration |

**PATCH `/api/parking/levels/:levelNumber`** body:
```json
{ "availableSlots": 50 }
```

**PUT `/api/parking/config`** body:
```json
{
  "workingHours": { "open": "06:00", "close": "22:00" },
  "availableWC": 4,
  "availableElectricChargers": 25
}
```

### Chaos Control API (`/api/chaos-control` → port 3090)

Manages chaos scenarios (latency injection, error injection) per city API. See `backend/chaos-control/README.md` for endpoint details.

### VM Health Control API (`/api/vm-health-control` → port 3095)

Reports simulated VM health state. See `backend/vm-health-control/README.md` for endpoint details.

### Berlin API — OpenTelemetry Metrics

The Berlin API exposes metrics at `/metrics/opentelemetry`. No Azure Log Analytics integration.

## Azure Log Analytics

The Lisbon, Madrid, and Paris APIs send structured logs to a shared Azure Log Analytics Workspace.

Example query (Lisbon):

```kusto
LisbonParkingLogs_CL
| where TimeGenerated > ago(1h)
| where level_s == "ERROR"
| project TimeGenerated, operation_s, details_s
```

## Development

```bash
# Backend (with auto-reload)
cd backend/lisbon-parking-api
npm run dev

# Frontend dev server (hot reload, port 3000 — no proxy)
cd frontend/parking-manager
npm start

# Tests
cd backend/lisbon-parking-api && npm test
cd frontend/parking-manager && npm test
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes and test thoroughly
4. Submit a pull request

## License

ISC

## Support

For issues and questions, please open an issue in the GitHub repository.
