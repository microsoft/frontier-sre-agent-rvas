# Madrid Parking API

A NodeJS API for the Madrid parking facility designed to run on **Windows Server** with **Windows Event Viewer** logging. This API represents a single parking location and provides real-time information about parking availability, levels, and facilities.

## Features

- **Real-time Parking Information** for Madrid parking facility
- **Level Management** - Track availability across multiple parking levels
- **Windows Event Viewer Logging** - All operations logged to Windows Event Viewer
- **Cross-Platform Fallback** - Console logging when not running on Windows
- **RESTful API** design
- **Metrics Tracking**:
  - Number of levels (4)
  - Parking slots per level (120)
  - Available slots per level
  - Working hours
  - Available WC facilities
  - Available electric chargers

## Windows Event Viewer Integration

This API is specifically designed for Windows Server and logs all operations to the Windows Event Viewer for centralized monitoring and diagnostics.

### Event Types Logged

- **Information Events**: HTTP requests, parking operations, server lifecycle
- **Warning Events**: Invalid requests, validation failures
- **Error Events**: Server errors, operation failures

### Event Log Structure

```json
{
  "timestamp": "2025-12-31T10:00:00.000Z",
  "level": "INFO|WARNING|ERROR",
  "message": "Operation description",
  "details": {
    "operation": "GET_PARKING_INFO",
    "parkId": "madrid-parking-001",
    "city": "Madrid"
  },
  "source": "MadridParkingAPI"
}
```

## Prerequisites

- **Node.js 16+**
- **Windows Server** (for Windows Event Viewer logging)
- **Administrator privileges** (for initial Event Source registration)

> **Note**: The API can run on non-Windows systems (Linux, macOS) but will use console logging instead of Windows Event Viewer.

## Setup

### 1. Install Dependencies

```bash
cd backend/madrid-parking-api
npm install
```

### 2. Configure Environment Variables

```bash
# Copy the example file
copy .env.example .env

# Edit .env with your configuration
```

Environment variables:
- `EVENT_LOG_SOURCE` - Event source name (default: MadridParkingAPI)
- `EVENT_LOG_NAME` - Event log name (default: Application)
- `PORT` - API port (default: 3002)
- `PARKING_NAME` - Name of the parking facility
- `PARKING_CITY` - City name (Madrid)
- `PARKING_LOCATION` - Address of the parking facility

### 3. Register Windows Event Source (Windows Only)

**⚠️ This step requires administrator privileges on Windows**

```bash
# Run as Administrator
npm run install-windows
```

This registers the event source in Windows Registry and allows the API to write to Event Viewer.

### 4. Start the API

```bash
# Production
npm start

# Development (with auto-reload)
npm run dev
```

The API will run on `http://localhost:3002`

## Viewing Logs in Windows Event Viewer

1. Open **Event Viewer** (press `Win + R`, type `eventvwr.msc`, press Enter)
2. Navigate to: **Windows Logs** > **Application**
3. Filter by Source: **MadridParkingAPI**

You can also use PowerShell:

```powershell
# View recent MadridParkingAPI events
Get-EventLog -LogName Application -Source MadridParkingAPI -Newest 20

# View all events from today
Get-EventLog -LogName Application -Source MadridParkingAPI -After (Get-Date).Date

# Filter by event type
Get-EventLog -LogName Application -Source MadridParkingAPI -EntryType Error
```

## API Endpoints

### Parking Information

- `GET /api/parking` - Get complete parking information
- `GET /api/parking/metrics` - Get parking metrics summary

### Level Management

- `GET /api/parking/levels` - Get all levels information
- `GET /api/parking/levels/:levelNumber` - Get specific level information
- `PATCH /api/parking/levels/:levelNumber` - Update available slots for a level

### Configuration

- `PUT /api/parking/config` - Update parking configuration (working hours, WC, chargers)

### Health Check

- `GET /health` - Health check endpoint with platform information

## API Usage Examples

### Get Parking Information

```bash
curl http://localhost:3002/api/parking
```

### Get Parking Metrics

```bash
curl http://localhost:3002/api/parking/metrics
```

### Get All Levels

```bash
curl http://localhost:3002/api/parking/levels
```

### Update Level Availability

```bash
curl -X PATCH http://localhost:3002/api/parking/levels/0 \
  -H "Content-Type: application/json" \
  -d "{\"availableSlots\": 80}"
```

### Update Parking Configuration

```bash
curl -X PUT http://localhost:3002/api/parking/config \
  -H "Content-Type: application/json" \
  -d "{\"workingHours\": {\"open\": \"07:00\", \"close\": \"22:00\"}, \"availableWC\": 5}"
```

## Running on Windows Server

### As a Windows Service (Optional)

You can run the API as a Windows Service for automatic startup:

1. Install `node-windows-service` globally:
```bash
npm install -g node-windows-service
```

2. Create a service:
```javascript
// service.js
const Service = require('node-windows').Service;

const svc = new Service({
  name: 'Madrid Parking API',
  description: 'Madrid Parking Management API',
  script: require('path').join(__dirname, 'server.js'),
  nodeOptions: [
    '--harmony',
    '--max_old_space_size=4096'
  ]
});

svc.on('install', () => {
  svc.start();
});

svc.install();
```

3. Run as Administrator:
```bash
node service.js
```

### IIS Configuration (Alternative)

To run behind IIS using iisnode:

1. Install [iisnode](https://github.com/azure/iisnode)
2. Create `web.config`:

```xml
<?xml version="1.0" encoding="utf-8"?>
<configuration>
  <system.webServer>
    <handlers>
      <add name="iisnode" path="server.js" verb="*" modules="iisnode"/>
    </handlers>
    <rewrite>
      <rules>
        <rule name="NodeInspector" patternSyntax="ECMAScript" stopProcessing="true">
          <match url="^server.js\/debug[\/]?" />
        </rule>
        <rule name="StaticContent">
          <action type="Rewrite" url="public{REQUEST_URI}"/>
        </rule>
        <rule name="DynamicContent">
          <conditions>
            <add input="{REQUEST_FILENAME}" matchType="IsFile" negate="True"/>
          </conditions>
          <action type="Rewrite" url="server.js"/>
        </rule>
      </rules>
    </rewrite>
  </system.webServer>
</configuration>
```

## Data Model

### Parking State Object

```json
{
  "id": "madrid-parking-001",
  "name": "Madrid Centro Parking",
  "city": "Madrid",
  "location": "Plaza Mayor, Madrid",
  "numberOfLevels": 4,
  "parkingSlotsPerLevel": 120,
  "availableSlotsPerLevel": [95, 110, 88, 105],
  "workingHours": {
    "open": "06:00",
    "close": "23:00"
  },
  "availableWC": 4,
  "availableElectricChargers": 30,
  "lastUpdated": "ISO timestamp"
}
```

## Architecture Notes

This API represents a single parking location (Madrid). The Parking Manager frontend will coordinate multiple such APIs for different cities to provide a centralized management interface.

**Key Differences from Lisbon API:**
- Uses Windows Event Viewer instead of Azure Log Analytics
- Optimized for Windows Server deployment
- Different parking configuration (4 levels, 120 slots/level)
- Event-driven logging architecture

## Troubleshooting

### Event Source Not Registered

If you see permission errors when starting the API:

1. Run PowerShell as Administrator
2. Execute: `npm run install-windows`
3. Restart the API

### Events Not Appearing in Event Viewer

1. Check Event Viewer is running: `services.msc` → Windows Event Log
2. Verify source registration: `Get-EventLog -List`
3. Check API has write permissions
4. Review console output for fallback messages

### Running on Non-Windows Systems

The API automatically detects the platform and falls back to console logging on Linux/macOS:

```bash
[Event Logger] Windows Event Viewer not available (not running on Windows)
[Event Logger] Falling back to console logging
```

This is normal and the API will function correctly with console logs.

## Integration with Frontend

To add Madrid to the Parking Manager frontend:

1. Update `frontend/parking-manager/src/services/parkingService.ts`:

```typescript
private apis: ParkingAPI[] = [
  {
    id: 'lisbon',
    city: 'Lisbon',
    apiUrl: process.env.REACT_APP_LISBON_API_URL || 'http://localhost:3001',
    enabled: true
  },
  {
    id: 'madrid',
    city: 'Madrid',
    apiUrl: process.env.REACT_APP_MADRID_API_URL || 'http://localhost:3002',
    enabled: true
  }
];
```

2. Add to `.env`:
```
REACT_APP_MADRID_API_URL=http://your-windows-server:3002
```

3. Rebuild and redeploy the frontend

## Monitoring

### PowerShell Monitoring Script

```powershell
# Monitor Madrid Parking API events in real-time
while ($true) {
    Clear-Host
    Write-Host "Madrid Parking API - Recent Events" -ForegroundColor Green
    Write-Host "=================================" -ForegroundColor Green
    Get-EventLog -LogName Application -Source MadridParkingAPI -Newest 10 | 
        Format-Table TimeGenerated, EntryType, Message -AutoSize
    Start-Sleep -Seconds 5
}
```

### Event Queries

```powershell
# Count events by type
Get-EventLog -LogName Application -Source MadridParkingAPI | 
    Group-Object EntryType | 
    Select-Object Name, Count

# Export events to CSV
Get-EventLog -LogName Application -Source MadridParkingAPI | 
    Export-Csv -Path "madrid-parking-logs.csv" -NoTypeInformation
```

## Security Considerations

- Event Viewer logs are stored locally and require Windows authentication
- Consider Event Forwarding for centralized logging across multiple servers
- Logs may contain operational data - ensure proper access controls
- Regular log rotation is handled automatically by Windows

## License

ISC
