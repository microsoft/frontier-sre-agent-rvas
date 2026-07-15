# Paris Parking API

A NodeJS API for the Paris parking facility designed to run on **Linux** with **Syslog** logging. This API represents a single parking location and provides real-time information about parking availability, levels, and facilities.

## Features

- **Real-time Parking Information** for Paris parking facility
- **Level Management** - Track availability across 6 parking levels
- **Syslog Integration** - All operations logged to syslog using RFC 5424 standards
- **Cross-platform Fallback** - Console logging when syslog is not available
- **RESTful API** design
- **Metrics Tracking**:
  - Number of levels (6)
  - Parking slots per level (80)
  - Available slots per level
  - Working hours
  - Available WC facilities
  - Available electric chargers

## Syslog Integration

This API is specifically designed for Linux systems and logs all operations to syslog for centralized monitoring and diagnostics.

### Syslog Features

- **RFC 5424 Compliance** - Standard syslog protocol
- **Configurable Facility** - Default: local0 (can be changed via environment variable)
- **Multiple Severity Levels** - INFO, NOTICE, WARNING, ERR, CRIT
- **Structured Logging** - JSON-formatted messages with timestamps
- **PID Tagging** - Process ID included in logs for tracking

### Syslog Severity Levels

- **INFO** (6): Normal operations, API requests
- **NOTICE** (5): Significant events, parking operations
- **WARNING** (4): Warning conditions, validation failures
- **ERR** (3): Error conditions, operation failures
- **CRIT** (2): Critical conditions, system failures

### Syslog Facilities

Configurable via `SYSLOG_FACILITY` environment variable:
- `local0` through `local7` - Local use (default: local0)
- `daemon` - System daemon messages
- `user` - User-level messages

## Prerequisites

- **Node.js 16+**
- **Linux system** (for syslog logging)
- **Syslog daemon** (rsyslog, syslog-ng, or systemd-journald)

> **Note**: The API can run on non-Linux systems (macOS, Windows) but will use console logging instead of syslog.

## Setup

### 1. Install Dependencies

```bash
cd backend/paris-parking-api
npm install
```

### 2. Configure Environment Variables

```bash
# Copy the example file
cp .env.example .env

# Edit .env with your configuration
```

Environment variables:
- `SYSLOG_FACILITY` - Syslog facility (default: local0)
- `SYSLOG_TAG` - Syslog tag/identifier (default: ParisParkingAPI)
- `PORT` - API port (default: 3003)
- `PARKING_NAME` - Name of the parking facility
- `PARKING_CITY` - City name (Paris)
- `PARKING_LOCATION` - Address of the parking facility

### 3. Configure Syslog (Optional)

To route Paris Parking API logs to a specific file, create a rsyslog configuration:

```bash
# Create rsyslog configuration
sudo nano /etc/rsyslog.d/paris-parking.conf
```

Add the following content:

```
# Paris Parking API logs
local0.* /var/log/paris-parking.log

# Optional: Stop processing after this rule to prevent duplicate logging
& stop
```

Restart rsyslog:

```bash
sudo systemctl restart rsyslog
```

### 4. Start the API

```bash
# Production
npm start

# Development (with auto-reload)
npm run dev
```

The API will run on `http://localhost:3003`

## Viewing Logs in Syslog

### Using journalctl (systemd)

```bash
# View all Paris Parking API logs
sudo journalctl -t ParisParkingAPI

# Follow logs in real-time
sudo journalctl -t ParisParkingAPI -f

# View logs from the last hour
sudo journalctl -t ParisParkingAPI --since "1 hour ago"

# View only errors
sudo journalctl -t ParisParkingAPI -p err
```

### Using traditional syslog files

```bash
# View logs (if configured to /var/log/paris-parking.log)
tail -f /var/log/paris-parking.log

# Search for specific operations
grep "GET_PARKING_INFO" /var/log/paris-parking.log

# View last 50 lines
tail -n 50 /var/log/paris-parking.log
```

### Using grep on syslog

```bash
# View all Paris Parking API messages
grep ParisParkingAPI /var/log/syslog

# Follow in real-time
tail -f /var/log/syslog | grep ParisParkingAPI

# Filter by severity
grep "ParisParkingAPI.*ERR" /var/log/syslog
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
curl http://localhost:3003/api/parking
```

### Get Parking Metrics

```bash
curl http://localhost:3003/api/parking/metrics
```

### Get All Levels

```bash
curl http://localhost:3003/api/parking/levels
```

### Update Level Availability

```bash
curl -X PATCH http://localhost:3003/api/parking/levels/0 \
  -H "Content-Type: application/json" \
  -d '{"availableSlots": 60}'
```

### Update Parking Configuration

```bash
curl -X PUT http://localhost:3003/api/parking/config \
  -H "Content-Type: application/json" \
  -d '{"workingHours": {"open": "06:00", "close": "23:00"}, "availableWC": 6}'
```

## Running as a Linux Service (systemd)

Create a systemd service file for automatic startup:

```bash
sudo nano /etc/systemd/system/paris-parking.service
```

Add the following content:

```ini
[Unit]
Description=Paris Parking API
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/path/to/backend/paris-parking-api
Environment="NODE_ENV=production"
Environment="PORT=3003"
ExecStart=/usr/bin/node server.js
Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=ParisParkingAPI

[Install]
WantedBy=multi-user.target
```

Enable and start the service:

```bash
# Reload systemd
sudo systemctl daemon-reload

# Enable service to start on boot
sudo systemctl enable paris-parking

# Start the service
sudo systemctl start paris-parking

# Check status
sudo systemctl status paris-parking

# View logs
sudo journalctl -u paris-parking -f
```

## Data Model

### Parking State Object

```json
{
  "id": "paris-parking-001",
  "name": "Paris Centre Parking",
  "city": "Paris",
  "location": "Champs-Élysées, Paris",
  "numberOfLevels": 6,
  "parkingSlotsPerLevel": 80,
  "availableSlotsPerLevel": [65, 72, 58, 75, 68, 70],
  "workingHours": {
    "open": "05:00",
    "close": "24:00"
  },
  "availableWC": 5,
  "availableElectricChargers": 25,
  "lastUpdated": "ISO timestamp"
}
```

## Architecture Notes

This API represents a single parking location (Paris). The Parking Manager frontend will coordinate multiple such APIs for different cities to provide a centralized management interface.

**Key Differences from Other APIs:**
- Uses Linux syslog instead of Azure Log Analytics or Windows Event Viewer
- Optimized for Linux server deployment
- Different parking configuration (6 levels, 80 slots/level)
- Extended working hours (05:00-24:00)
- Syslog facility and tag configuration

## Troubleshooting

### Syslog Not Working

If logs don't appear in syslog:

1. **Check if posix module is installed:**
```bash
npm list posix
# If not installed: npm install posix
```

2. **Check syslog daemon is running:**
```bash
# For rsyslog
sudo systemctl status rsyslog

# For syslog-ng
sudo systemctl status syslog-ng
```

3. **Check syslog configuration:**
```bash
# Verify facility is not filtered
cat /etc/rsyslog.conf | grep local0
```

4. **Check file permissions:**
```bash
# Ensure log file is writable
ls -la /var/log/paris-parking.log
```

### Running on Non-Linux Systems

The API automatically detects the platform and falls back to console logging on Windows/macOS:

```bash
[Syslog Logger] Syslog not available (posix module not installed or not on Linux)
[Syslog Logger] Falling back to console logging
```

This is normal and the API will function correctly with console logs.

### Logs Not in Custom File

If logs appear in `/var/log/syslog` but not in custom file:

1. Check rsyslog configuration is loaded
2. Restart rsyslog after config changes
3. Verify file path and permissions
4. Check for conflicting rules in other config files

## Integration with Frontend

To add Paris to the Parking Manager frontend:

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
  },
  {
    id: 'paris',
    city: 'Paris',
    apiUrl: process.env.REACT_APP_PARIS_API_URL || 'http://localhost:3003',
    enabled: true
  }
];
```

2. Add to `.env`:
```
REACT_APP_PARIS_API_URL=http://your-linux-server:3003
```

3. Rebuild and redeploy the frontend

## Monitoring

### Real-time Monitoring Script

```bash
#!/bin/bash
# monitor-paris-parking.sh

echo "Paris Parking API - Real-time Logs"
echo "=================================="
sudo journalctl -t ParisParkingAPI -f --since "5 minutes ago"
```

### Log Analysis Examples

```bash
# Count operations by type
grep ParisParkingAPI /var/log/syslog | \
  grep -o '"operation":"[^"]*"' | \
  sort | uniq -c

# Find errors in last 24 hours
sudo journalctl -t ParisParkingAPI --since yesterday -p err

# Export logs to file
sudo journalctl -t ParisParkingAPI --since today > paris-parking-logs.txt
```

## Security Considerations

- Syslog logs are stored locally with system-level permissions
- Consider log rotation to manage disk space
- Use rsyslog TLS for remote logging to centralized servers
- Logs may contain operational data - ensure proper access controls
- Regular monitoring for unusual patterns or errors

## Performance

- Syslog is lightweight and has minimal performance impact
- Asynchronous logging prevents blocking API operations
- Structured JSON format enables efficient parsing and analysis
- Compatible with log aggregation tools (ELK, Splunk, Graylog)

## License

ISC
