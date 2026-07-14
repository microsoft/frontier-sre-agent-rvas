# Berlin Parking API

A containerized NodeJS API for the Berlin parking facility with OpenTelemetry metrics. This API represents a single parking location and provides real-time information about parking availability, levels, and facilities. **Unlike other parking APIs in this project, this API does NOT integrate with Azure Log Analytics** and instead exposes metrics in OpenTelemetry format for external monitoring systems.

## Features

- **Standard Parking Management APIs** - Same REST API as other parking facilities
- **OpenTelemetry Metrics** - Comprehensive metrics exposed in OpenTelemetry format
- **Console Logging Only** - No Azure Log Analytics integration
- **Real-time Simulation** - Parking activity simulation (updates every 5 seconds)
- **Docker Ready** - Containerized for easy deployment
- **Business Metrics** - Track occupancy rates, car movements, and trends
- **Infrastructure Metrics** - Mocked CPU, memory, and disk usage
- **Health Checks** - Built-in health check endpoint

## API Endpoints

### Standard Parking APIs

These endpoints are consumed by the frontend:

#### `GET /health`
Health check endpoint.

**Response:**
```json
{
  "status": "healthy",
  "timestamp": "2024-01-15T10:30:00.000Z",
  "service": "berlin-parking-api",
  "city": "Berlin",
  "uptime": 3600
}
```

#### `GET /api/parking`
Get complete parking information.

**Response:**
```json
{
  "success": true,
  "data": {
    "id": "berlin-parking-001",
    "name": "Berlin Central Parking",
    "city": "Berlin",
    "location": "Alexanderplatz, Berlin, Germany",
    "numberOfLevels": 4,
    "parkingSlotsPerLevel": 80,
    "availableSlotsPerLevel": [65, 72, 58, 70],
    "workingHours": {
      "open": "06:00",
      "close": "23:00"
    },
    "availableWC": 4,
    "availableElectricChargers": 15,
    "lastUpdated": "2024-01-15T10:30:00.000Z"
  }
}
```

#### `GET /api/parking/metrics`
Get parking metrics summary.

**Response:**
```json
{
  "success": true,
  "data": {
    "city": "Berlin",
    "totalSlots": 320,
    "totalAvailable": 265,
    "totalOccupied": 55,
    "occupancyRate": 17.19,
    "numberOfLevels": 4,
    "availableWC": 4,
    "availableElectricChargers": 15,
    "workingHours": {
      "open": "06:00",
      "close": "23:00"
    },
    "lastUpdated": "2024-01-15T10:30:00.000Z"
  }
}
```

#### `GET /api/parking/levels`
Get information for all parking levels.

**Response:**
```json
{
  "success": true,
  "data": [
    {
      "level": 0,
      "totalSlots": 80,
      "availableSlots": 65,
      "occupiedSlots": 15,
      "occupancyRate": "18.75"
    },
    // ... more levels
  ]
}
```

#### `GET /api/parking/levels/:levelNumber`
Get information for a specific parking level.

**Parameters:**
- `levelNumber` (path) - Level number (0-3)

**Response:**
```json
{
  "success": true,
  "data": {
    "level": 0,
    "totalSlots": 80,
    "availableSlots": 65,
    "occupiedSlots": 15,
    "occupancyRate": "18.75"
  }
}
```

#### `PATCH /api/parking/levels/:levelNumber`
Update available slots for a specific level.

**Parameters:**
- `levelNumber` (path) - Level number (0-3)

**Request Body:**
```json
{
  "availableSlots": 50
}
```

**Response:**
```json
{
  "success": true,
  "data": {
    // Updated parking state
  }
}
```

#### `PUT /api/parking/config`
Update parking configuration.

**Request Body:**
```json
{
  "workingHours": {
    "open": "07:00",
    "close": "22:00"
  },
  "availableWC": 5,
  "availableElectricChargers": 18
}
```

**Response:**
```json
{
  "success": true,
  "data": {
    // Updated parking state
  }
}
```

### OpenTelemetry Metrics API

This endpoint is **NOT** consumed by the frontend. It's designed for external monitoring systems to scrape metrics.

#### `GET /metrics/opentelemetry`
Get comprehensive metrics in OpenTelemetry format.

**Response:** (Abbreviated example)
```json
{
  "resourceMetrics": [{
    "resource": {
      "attributes": [
        { "key": "service.name", "value": { "stringValue": "berlin-parking-api" }},
        { "key": "service.instance.id", "value": { "stringValue": "berlin-parking-001" }},
        { "key": "service.version", "value": { "stringValue": "1.0.0" }}
      ]
    },
    "scopeMetrics": [{
      "scope": {
        "name": "berlin-parking-metrics",
        "version": "1.0.0"
      },
      "metrics": [
        {
          "name": "http.server.duration",
          "description": "HTTP request duration",
          "unit": "ms",
          "histogram": {
            "dataPoints": [{
              "count": "1234",
              "sum": 45678.9,
              "min": 2.5,
              "max": 245.8,
              "quantileValues": [
                { "quantile": 0.5, "value": 35.2 },
                { "quantile": 0.95, "value": 125.5 },
                { "quantile": 0.99, "value": 245.8 }
              ]
            }]
          }
        },
        {
          "name": "http.server.request.count",
          "description": "Total HTTP requests",
          "unit": "1",
          "sum": {
            "dataPoints": [{
              "asInt": "1234"
            }]
          }
        },
        {
          "name": "parking.occupancy.current",
          "description": "Current parking occupancy rate",
          "unit": "%",
          "gauge": {
            "dataPoints": [{
              "asDouble": 67.5
            }]
          }
        }
        // ... many more metrics
      ]
    }]
  }]
}
```

## Metrics Categories

The OpenTelemetry metrics endpoint exposes the following categories of metrics:

### 1. Response Time Metrics
- `http.server.duration` - Histogram of request durations
- `http.server.duration.avg` - Average response time
- `http.server.duration.p95` - 95th percentile response time
- `http.server.duration.p99` - 99th percentile response time

### 2. Request Count/Throughput
- `http.server.request.count` - Total number of requests
- `http.server.requests_per_minute` - Current requests per minute

### 3. Error Rate Metrics
- `http.server.error.count` - Total error count
- `http.server.error.rate` - Error rate percentage
- `http.server.error.4xx` - Count of 4xx errors
- `http.server.error.5xx` - Count of 5xx errors

### 4. Availability/Uptime
- `system.uptime` - Server uptime in seconds
- `system.availability` - Availability percentage
- `system.last_restart` - Last restart timestamp

### 5. Business Metrics (Parking)
- `parking.occupancy.current` - Current occupancy rate
- `parking.occupancy.avg_5min` - Average occupancy (last 5 minutes)
- `parking.occupancy.avg_15min` - Average occupancy (last 15 minutes)
- `parking.occupancy.avg_60min` - Average occupancy (last 60 minutes)
- `parking.occupancy.peak_1hour` - Peak occupancy in last hour
- `parking.cars.entered` - Total cars entered (simulated)
- `parking.cars.exited` - Total cars exited (simulated)

### 6. Infrastructure Metrics (Mocked)
- `system.cpu.usage` - CPU usage percentage
- `system.memory.usage` - Memory usage percentage
- `system.disk.usage` - Disk usage percentage

**Note:** Infrastructure metrics are mocked with realistic random values for demonstration purposes.

## Setup

### Prerequisites

- Node.js 18 or higher
- npm or yarn

### Installation

```bash
cd backend/berlin-parking-api
npm install
```

### Environment Variables

Copy `.env.example` to `.env` and configure:

```bash
cp .env.example .env
```

Edit `.env`:
```
PORT=3004
NODE_ENV=development
PARKING_NAME=Berlin Central Parking
PARKING_CITY=Berlin
PARKING_LOCATION=Alexanderplatz, Berlin, Germany
```

### Running Locally

```bash
npm start
```

For development with auto-reload:
```bash
npm run dev
```

The API will be available at `http://localhost:3004`.

### Running with Docker

#### Build the image

```bash
docker build -t berlin-parking-api .
```

#### Run the container

```bash
docker run -p 3004:3004 \
  -e PARKING_NAME="Berlin Central Parking" \
  -e PARKING_CITY="Berlin" \
  -e PARKING_LOCATION="Alexanderplatz, Berlin, Germany" \
  berlin-parking-api
```

## API Usage Examples

### Get Parking Information

```bash
curl http://localhost:3004/api/parking
```

### Get Parking Metrics

```bash
curl http://localhost:3004/api/parking/metrics
```

### Get All Levels

```bash
curl http://localhost:3004/api/parking/levels
```

### Get Specific Level

```bash
curl http://localhost:3004/api/parking/levels/0
```

### Update Level Availability

```bash
curl -X PATCH http://localhost:3004/api/parking/levels/0 \
  -H "Content-Type: application/json" \
  -d '{
    "availableSlots": 45
  }'
```

### Update Parking Configuration

```bash
curl -X PUT http://localhost:3004/api/parking/config \
  -H "Content-Type: application/json" \
  -d '{
    "workingHours": {
      "open": "07:00",
      "close": "22:00"
    },
    "availableWC": 5,
    "availableElectricChargers": 18
  }'
```

### Get OpenTelemetry Metrics

```bash
curl http://localhost:3004/metrics/opentelemetry
```

## Logging

This API uses **console logging only**. All logs are written to stdout/stderr and can be viewed with:

```bash
# Docker logs
docker logs <container-id>

# Local development
# Logs appear in the terminal
```

**No Azure Log Analytics integration** - This is intentional. The API is designed to work independently of Azure monitoring services.

## Parking Simulation

The API includes an automatic parking simulation that:
- Updates available slots every 5 seconds
- Simulates cars entering and leaving (random changes of -3 to +3 slots per level)
- Tracks car movements for business metrics
- Maintains occupancy history for trend analysis

## Data Model

### Parking Configuration
- **Levels**: 4
- **Slots per level**: 80
- **Total capacity**: 320 slots
- **Initial availability**: [65, 72, 58, 70] (varies per level)
- **Working hours**: 06:00 - 23:00
- **Electric chargers**: 15
- **Restrooms (WC)**: 4

## Architecture Notes

### Metrics Tracking
- Metrics are tracked in-memory using the `MetricsTracker` class
- Response times are sampled (last 1000 requests) for percentile calculations
- Occupancy history is maintained for 5min, 15min, and 60min windows
- Infrastructure metrics are mocked with realistic random variations

### OpenTelemetry Format
- Follows OpenTelemetry metrics data model
- Uses standard metric types: Histogram, Sum, Gauge
- Includes resource attributes for service identification
- Suitable for consumption by Prometheus, Grafana, or other monitoring tools

### No External Dependencies
- No Azure Log Analytics client libraries
- No OpenTelemetry SDK dependencies (metrics are manually formatted)
- Lightweight and portable

## Deployment

This API is designed to run as an Azure Container App without Log Analytics integration. See the infrastructure module at `infrastructure/modules/berlin-api.bicep` for deployment details.

## Differences from Other Parking APIs

| Feature | Berlin | Lisbon | Madrid | Paris |
|---------|--------|--------|--------|-------|
| Platform | Container App | Container App | Windows VM | Linux VM |
| Logging | Console only | Azure Log Analytics | Windows Event Viewer | Syslog |
| Metrics | OpenTelemetry | Log Analytics Queries | Event Log Queries | Syslog Analysis |
| Port | 3004 | 3001 | 3002 | 3003 |
| HTTPS | No | No | Yes | Yes |

## License

ISC
