require('dotenv').config();
const express = require('express');
const cors = require('cors');
const MetricsTracker = require('./metricsTracker');
const createChaosMiddleware = require('../shared/chaosMiddleware');

const app = express();
const PORT = process.env.PORT || 3004;

// Middleware
app.use(cors());
app.use(express.json());

// Initialize Metrics Tracker
const metricsTracker = new MetricsTracker();

// Berlin Parking State
let parkingState = {
  id: 'berlin-parking-001',
  name: process.env.PARKING_NAME || 'Berlin Central Parking',
  city: process.env.PARKING_CITY || 'Berlin',
  location: process.env.PARKING_LOCATION || 'Alexanderplatz, Berlin, Germany',
  numberOfLevels: 4,
  parkingSlotsPerLevel: 80,
  availableSlotsPerLevel: [65, 72, 58, 70], // Available slots per level
  workingHours: {
    open: '06:00',
    close: '23:00'
  },
  availableWC: 4,
  availableElectricChargers: 15,
  lastUpdated: new Date().toISOString()
};

// Request logging and metrics tracking middleware
app.use((req, res, next) => {
  const startTime = Date.now();
  
  // Track request
  metricsTracker.trackRequest(req.method, req.path);
  
  // Log to console
  console.log(`[${new Date().toISOString()}] ${req.method} ${req.path} - IP: ${req.ip}`);
  
  // Track response time and errors
  res.on('finish', () => {
    const responseTime = Date.now() - startTime;
    metricsTracker.trackResponseTime(req.path, responseTime);

    console.log(`[${new Date().toISOString()}] RESPONSE ${req.method} ${req.path} - Status: ${res.statusCode} - responseTimeMs: ${responseTime}`);
    
    if (res.statusCode >= 400) {
      metricsTracker.trackError(res.statusCode);
    }
  });
  
  next();
});

app.use(createChaosMiddleware('berlin', {
  onChaosInject: (details) => {
    console.error('[CHAOS_INJECTED]', JSON.stringify(details));
  }
}));

// Health check endpoint
app.get('/health', (req, res) => {
  res.json({ 
    status: 'healthy', 
    timestamp: new Date().toISOString(),
    service: 'berlin-parking-api',
    city: parkingState.city,
    uptime: metricsTracker.getUptimeSeconds()
  });
});

// Get parking information
app.get('/api/parking', (req, res) => {
  try {
    console.log(`GET_PARKING_INFO - City: ${parkingState.city}`);
    res.json({ success: true, data: parkingState });
  } catch (error) {
    console.error('GET_PARKING_INFO - Error:', error.message);
    res.status(500).json({ success: false, error: 'Failed to retrieve parking information' });
  }
});

// Get parking metrics
app.get('/api/parking/metrics', (req, res) => {
  try {
    const totalSlots = parkingState.numberOfLevels * parkingState.parkingSlotsPerLevel;
    const totalAvailable = parkingState.availableSlotsPerLevel.reduce((sum, slots) => sum + slots, 0);
    const occupancyRate = ((totalSlots - totalAvailable) / totalSlots * 100).toFixed(2);

    const metrics = {
      city: parkingState.city,
      totalSlots,
      totalAvailable,
      totalOccupied: totalSlots - totalAvailable,
      occupancyRate: parseFloat(occupancyRate),
      numberOfLevels: parkingState.numberOfLevels,
      availableWC: parkingState.availableWC,
      availableElectricChargers: parkingState.availableElectricChargers,
      workingHours: parkingState.workingHours,
      lastUpdated: parkingState.lastUpdated
    };

    console.log(`GET_METRICS - Occupancy: ${occupancyRate}%`);
    res.json({ success: true, data: metrics });
  } catch (error) {
    console.error('GET_METRICS - Error:', error.message);
    res.status(500).json({ success: false, error: 'Failed to retrieve metrics' });
  }
});

// Get level information
app.get('/api/parking/levels', (req, res) => {
  try {
    const levels = parkingState.availableSlotsPerLevel.map((available, index) => ({
      level: index,
      totalSlots: parkingState.parkingSlotsPerLevel,
      availableSlots: available,
      occupiedSlots: parkingState.parkingSlotsPerLevel - available,
      occupancyRate: ((parkingState.parkingSlotsPerLevel - available) / parkingState.parkingSlotsPerLevel * 100).toFixed(2)
    }));

    console.log(`GET_LEVELS - Levels count: ${levels.length}`);
    res.json({ success: true, data: levels });
  } catch (error) {
    console.error('GET_LEVELS - Error:', error.message);
    res.status(500).json({ success: false, error: 'Failed to retrieve level information' });
  }
});

// Get specific level information
app.get('/api/parking/levels/:levelNumber', (req, res) => {
  try {
    const levelNumber = parseInt(req.params.levelNumber);

    if (isNaN(levelNumber) || levelNumber < 0 || levelNumber >= parkingState.numberOfLevels) {
      return res.status(400).json({ 
        success: false, 
        error: `Invalid level number. Must be between 0 and ${parkingState.numberOfLevels - 1}` 
      });
    }

    const available = parkingState.availableSlotsPerLevel[levelNumber];
    const levelInfo = {
      level: levelNumber,
      totalSlots: parkingState.parkingSlotsPerLevel,
      availableSlots: available,
      occupiedSlots: parkingState.parkingSlotsPerLevel - available,
      occupancyRate: ((parkingState.parkingSlotsPerLevel - available) / parkingState.parkingSlotsPerLevel * 100).toFixed(2)
    };

    console.log(`GET_LEVEL - Level: ${levelNumber}`);
    res.json({ success: true, data: levelInfo });
  } catch (error) {
    console.error('GET_LEVEL - Error:', error.message);
    res.status(500).json({ success: false, error: 'Failed to retrieve level information' });
  }
});

// Update available slots for a specific level
app.patch('/api/parking/levels/:levelNumber', (req, res) => {
  try {
    const levelNumber = parseInt(req.params.levelNumber);
    const { availableSlots } = req.body;

    if (isNaN(levelNumber) || levelNumber < 0 || levelNumber >= parkingState.numberOfLevels) {
      return res.status(400).json({ 
        success: false, 
        error: `Invalid level number. Must be between 0 and ${parkingState.numberOfLevels - 1}` 
      });
    }

    if (availableSlots === undefined || availableSlots < 0 || availableSlots > parkingState.parkingSlotsPerLevel) {
      return res.status(400).json({ 
        success: false, 
        error: `Invalid slot count. Must be between 0 and ${parkingState.parkingSlotsPerLevel}` 
      });
    }

    parkingState.availableSlotsPerLevel[levelNumber] = availableSlots;
    parkingState.lastUpdated = new Date().toISOString();

    console.log(`UPDATE_LEVEL_SLOTS - Level: ${levelNumber}, Available: ${availableSlots}`);
    res.json({ success: true, data: parkingState });
  } catch (error) {
    console.error('UPDATE_LEVEL_SLOTS - Error:', error.message);
    res.status(500).json({ success: false, error: 'Failed to update level slots' });
  }
});

// Update parking configuration
app.put('/api/parking/config', (req, res) => {
  try {
    const { workingHours, availableWC, availableElectricChargers } = req.body;

    if (workingHours) {
      parkingState.workingHours = workingHours;
    }
    if (availableWC !== undefined) {
      parkingState.availableWC = availableWC;
    }
    if (availableElectricChargers !== undefined) {
      parkingState.availableElectricChargers = availableElectricChargers;
    }

    parkingState.lastUpdated = new Date().toISOString();

    console.log(`UPDATE_CONFIG - Changes: ${Object.keys(req.body).join(', ')}`);
    res.json({ success: true, data: parkingState });
  } catch (error) {
    console.error('UPDATE_CONFIG - Error:', error.message);
    res.status(500).json({ success: false, error: 'Failed to update configuration' });
  }
});

// OpenTelemetry Metrics Endpoint
app.get('/metrics/opentelemetry', (req, res) => {
  try {
    // Calculate current occupancy rate
    const totalSlots = parkingState.numberOfLevels * parkingState.parkingSlotsPerLevel;
    const totalAvailable = parkingState.availableSlotsPerLevel.reduce((sum, slots) => sum + slots, 0);
    const currentOccupancyRate = ((totalSlots - totalAvailable) / totalSlots * 100);

    const metrics = metricsTracker.getOpenTelemetryMetrics(currentOccupancyRate);
    
    console.log('METRICS - OpenTelemetry metrics requested');
    res.json(metrics);
  } catch (error) {
    console.error('METRICS - Error:', error.message);
    res.status(500).json({ success: false, error: 'Failed to retrieve metrics' });
  }
});

// Simulate parking activity (cars entering/leaving)
const simulateParkingActivity = () => {
  // Randomly change availability for each level (simulate 1-3 cars per level)
  parkingState.availableSlotsPerLevel = parkingState.availableSlotsPerLevel.map((current, index) => {
    const change = Math.floor(Math.random() * 7) - 3; // Random change between -3 and +3
    let newValue = current + change;
    
    // Keep within valid range [0, parkingSlotsPerLevel]
    newValue = Math.max(0, Math.min(parkingState.parkingSlotsPerLevel, newValue));
    
    // Track car movements for metrics
    if (change < 0) {
      // Cars entered (slots decreased)
      metricsTracker.simulateCarEntry();
    } else if (change > 0) {
      // Cars exited (slots increased)
      metricsTracker.simulateCarExit();
    }
    
    return newValue;
  });
  
  parkingState.lastUpdated = new Date().toISOString();
  
  // Track occupancy for business metrics
  const totalSlots = parkingState.numberOfLevels * parkingState.parkingSlotsPerLevel;
  const totalAvailable = parkingState.availableSlotsPerLevel.reduce((sum, slots) => sum + slots, 0);
  const occupancyRate = ((totalSlots - totalAvailable) / totalSlots * 100);
  metricsTracker.trackOccupancy(occupancyRate);
};

// Start parking simulation (update every 5 seconds)
setInterval(simulateParkingActivity, 5000);

app.use((err, req, res, next) => {
  console.error('Unhandled API error:', err.message);
  if (res.headersSent) {
    return next(err);
  }

  const isChaosException = Boolean(err?.isChaosException || err?.chaosFaultType === 'exception');
  return res.status(500).json({
    success: false,
    error: 'Internal server error',
    chaos: isChaosException,
    stackTrace: isChaosException ? err.stack : undefined
  });
});

// Start server
app.listen(PORT, () => {
  console.log(`🚗 ${parkingState.city} Parking API running on port ${PORT}`);
  console.log(`📍 Location: ${parkingState.location}`);
  console.log(`📊 Logging: Console only (no Azure Log Analytics)`);
  console.log(`📈 OpenTelemetry Metrics: Available at /metrics/opentelemetry`);
  console.log(`🎲 Parking activity simulation: Enabled (updates every 5 seconds)`);
  console.log(`🏗️  Levels: ${parkingState.numberOfLevels}, Slots per level: ${parkingState.parkingSlotsPerLevel}`);
  console.log(`🔌 Electric Chargers: ${parkingState.availableElectricChargers}, WC: ${parkingState.availableWC}`);
});

// Graceful shutdown
process.on('SIGTERM', () => {
  console.log('SIGTERM signal received: closing HTTP server');
  console.log(`Final stats - Total requests: ${metricsTracker.totalRequests}, Uptime: ${metricsTracker.getUptimeSeconds()}s`);
  process.exit(0);
});
