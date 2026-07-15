# Lisbon Parking API

A containerized NodeJS API for the Lisbon parking facility with Azure Log Analytics integration. This API represents a single parking location and provides real-time information about parking availability, levels, and facilities.

## Features

- **Real-time Parking Information** for Lisbon parking facility
- **Level Management** - Track availability across multiple parking levels
- **Metrics Tracking**:
  - Number of levels
  - Parking slots per level
  - Available slots per level
  - Working hours
  - Available WC facilities
  - Available electric chargers
- **Azure Log Analytics Integration** for custom logging
- **Containerized** with Docker
- **RESTful API** design

## API Endpoints

### Parking Information

- `GET /api/parking` - Get complete parking information
- `GET /api/parking/metrics` - Get parking metrics (occupancy, availability)

### Level Management

- `GET /api/parking/levels` - Get all levels information
- `GET /api/parking/levels/:levelNumber` - Get specific level information
- `PATCH /api/parking/levels/:levelNumber` - Update available slots for a specific level

### Configuration

- `PUT /api/parking/config` - Update parking configuration (working hours, WC, chargers)

### Health Check

- `GET /health` - Health check endpoint

## Setup

### Prerequisites

- Node.js 18+ or Docker
- Azure Log Analytics workspace (optional)

### Environment Variables

Copy `.env.example` to `.env` and configure:

```bash
cp .env.example .env
```

Required variables:

- `WORKSPACE_ID` - Azure Log Analytics Workspace ID (optional, will log to console if not set)
- `SHARED_KEY` - Azure Log Analytics Shared Key (optional)
- `LOG_TYPE` - Log type name in Azure (default: LisbonParkingLogs)
- `PORT` - API port (default: 3001)
- `PARKING_NAME` - Name of the parking facility
- `PARKING_CITY` - City name (Lisbon)
- `PARKING_LOCATION` - Address of the parking facility

### Running Locally

```bash
# Install dependencies
npm install

# Start the server
npm start

# Or use nodemon for development
npm run dev
```

### Running with Docker

```bash
# Build the image
docker build -t lisbon-parking-api .

# Run the container
docker run -p 3001:3001 \
  -e WORKSPACE_ID=your-workspace-id \
  -e SHARED_KEY=your-shared-key \
  -e LOG_TYPE=LisbonParkingLogs \
  -e PARKING_NAME="Lisbon Downtown Parking" \
  -e PARKING_CITY="Lisbon" \
  -e PARKING_LOCATION="Praça do Comércio, Lisbon" \
  lisbon-parking-api
```

## API Usage Examples

### Get Parking Information

```bash
curl http://localhost:3001/api/parking
```

### Get Parking Metrics

```bash
curl http://localhost:3001/api/parking/metrics
```

### Get All Levels

```bash
curl http://localhost:3001/api/parking/levels
```

### Get Specific Level

```bash
curl http://localhost:3001/api/parking/levels/0
```

### Update Level Availability

```bash
curl -X PATCH http://localhost:3001/api/parking/levels/0 \
  -H "Content-Type: application/json" \
  -d '{
    "availableSlots": 25
  }'
```

### Update Parking Configuration

```bash
curl -X PUT http://localhost:3001/api/parking/config \
  -H "Content-Type: application/json" \
  -d '{
    "workingHours": {
      "open": "06:00",
      "close": "22:00"
    },
    "availableWC": 4,
    "availableElectricChargers": 25
  }'
```

## Azure Log Analytics

The API sends custom logs to Azure Log Analytics including:

- API requests (method, path, timestamp, city)
- Parking operations (level updates, config changes)
- Error tracking
- Server lifecycle events

Logs can be queried in Azure using the configured `LOG_TYPE` (default: `LisbonParkingLogs_CL`).

## Data Model

### Parking State Object

```json
{
  "id": "lisbon-parking-001",
  "name": "Lisbon Downtown Parking",
  "city": "Lisbon",
  "location": "Praça do Comércio, Lisbon",
  "numberOfLevels": 5,
  "parkingSlotsPerLevel": 100,
  "availableSlotsPerLevel": [85, 92, 78, 95, 88],
  "workingHours": {
    "open": "00:00",
    "close": "23:59"
  },
  "availableWC": 3,
  "availableElectricChargers": 20,
  "lastUpdated": "ISO timestamp"
}
```

## Architecture Notes

This API represents a single parking location (Lisbon). The Parking Manager frontend will coordinate multiple such APIs for different cities to provide a centralized management interface.

## License

ISC
