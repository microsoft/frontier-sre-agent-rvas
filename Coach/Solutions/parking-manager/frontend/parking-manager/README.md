# Parking Manager Frontend

React-based frontend application for managing multiple parking facilities across different cities. Served by an Express proxy server on port 8080.

## Features

- **Multi-City Management**: View and manage parking facilities for Lisbon, Madrid, Paris, and Berlin
- **Chaos Backoffice**: Configure and trigger chaos scenarios (latency/error injection) per city
- **Real-Time Updates**: Auto-refresh every 30 seconds
- **Interactive Dashboard**: Occupancy rates, available slots, and facility details
- **Level Management**: Update availability for individual parking levels
- **Responsive Design**: Works on desktop and mobile devices

## Architecture

The frontend consists of two parts:

1. **React application** (`src/`) — Builds to the `build/` directory
2. **Express proxy server** (`server.js`) — Serves the React static files and proxies all `/api/*` routes to the backend services

### Proxy routes

| Frontend path | Backend service | Default port |
|---------------|-----------------|--------------|
| `/api/lisbon` | Lisbon Parking API | 3001 |
| `/api/madrid` | Madrid Parking API | 3002 |
| `/api/paris` | Paris Parking API | 3003 |
| `/api/berlin` | Berlin Parking API | 3004 |
| `/api/chaos-control` | Chaos Control | 3090 |
| `/api/vm-health-control` | VM Health Control | 3095 |

Backend URLs are configured via environment variables (see below). The proxy handles timeouts and surfaces meaningful errors when a backend service is unreachable.

## Quick Start (Local)

The easiest way to run the full local stack is:

```bash
# From the repository root
./scripts/start-chaos-stack.sh
```

This starts all backend services and the frontend proxy. Open **http://localhost:8080**.
Logs are written to `.runtime-logs/` in the repository root. Press `Ctrl+C` to stop everything.

## Manual Setup for Local Development

### Prerequisites

- Node.js 18+
- Backend services running (see root [README.md](../../README.md))

### Installation

```bash
npm install
```

### Environment Variables

Configure backend API URLs in `.env` (copy from `.env.example`):

```bash
REACT_APP_LISBON_API_URL=http://localhost:3001
REACT_APP_MADRID_API_URL=http://localhost:3002
REACT_APP_PARIS_API_URL=http://localhost:3003
REACT_APP_BERLIN_API_URL=http://localhost:3004
REACT_APP_CHAOS_CONTROL_URL=http://localhost:3090
REACT_APP_VM_HEALTH_CONTROL_URL=http://localhost:3095
```

### Running in development mode

```bash
npm start    # Hot-reload dev server on http://localhost:3000 (no proxy server)
```

### Running via the proxy server (production-like)

```bash
npm run build          # Build the React app
PORT=8080 node server.js   # Start Express proxy + static server
```

Open **http://localhost:8080**.

### Run tests

```bash
npm test
```

## Azure App Service Deployment

The frontend is deployed as a Node.js App Service running `server.js`. The workflow in `.github/workflows/deploy-frontend.yml` handles CI/CD automatically on push to `main`.

### Manual deployment

```bash
npm install && npm run build

az webapp up \
  --name <app-service-name> \
  --resource-group <resource-group> \
  --runtime "NODE:18-lts" \
  --src-path .
```

### Application Settings in Azure

Set the following Application Settings in the Azure App Service to configure backend URLs:

```
REACT_APP_LISBON_API_URL=https://<lisbon-api-fqdn>
REACT_APP_MADRID_API_URL=https://<madrid-api-fqdn>
REACT_APP_PARIS_API_URL=https://<paris-api-fqdn>
REACT_APP_BERLIN_API_URL=https://<berlin-api-fqdn>
REACT_APP_CHAOS_CONTROL_URL=https://<chaos-control-fqdn>
REACT_APP_VM_HEALTH_CONTROL_URL=https://<vm-health-control-fqdn>
```

For CI/CD setup, see [.github/workflows/README.md](../../.github/workflows/README.md).

## Project Structure

```
frontend/parking-manager/
├── src/
│   ├── components/          # React components
│   │   ├── ParkingCard.tsx  # Card for each parking facility
│   │   ├── ParkingDetails.tsx  # Detailed level view modal
│   │   └── *.css
│   ├── services/
│   │   └── parkingService.ts   # API client
│   ├── types.ts             # TypeScript interfaces
│   ├── App.tsx              # Main application component
│   └── index.tsx            # Entry point
├── server.js                # Express proxy server
├── public/                  # Static assets
├── build/                   # React production build (generated)
├── .env.example             # Environment variable template
└── package.json
```

## API Integration

The frontend expects each parking API to expose:

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Health check |
| `GET` | `/api/parking` | Full parking information |
| `GET` | `/api/parking/metrics` | Metrics summary |
| `GET` | `/api/parking/dependency` | Dependency health (where supported) |
| `GET` | `/api/parking/levels` | All parking levels |
| `PATCH` | `/api/parking/levels/:levelNumber` | Update level availability |
| `PUT` | `/api/parking/config` | Update parking configuration |

## Browser Support

Chrome, Firefox, Safari, and Edge (latest stable versions).

## License

ISC
