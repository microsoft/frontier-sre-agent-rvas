require('dotenv').config();
const express = require('express');
const cors = require('cors');
const https = require('https');
const fs = require('fs');
const path = require('path');
const WindowsEventLogger = require('./windowsEventLogger');
const createChaosMiddleware = require('../shared/chaosMiddleware');

const app = express();
const PORT = process.env.PORT || 3002;

// HTTPS Configuration
let server;
const certPath = process.env.CERT_PATH || path.join(__dirname, 'madrid.crt');
const keyPath = process.env.KEY_PATH || path.join(__dirname, 'madrid.key');

// Check if HTTPS certificates exist
const useHttps = fs.existsSync(certPath) && fs.existsSync(keyPath);

// Middleware
app.use(cors());
app.use(express.json());

// Initialize Windows Event Logger
const logger = new WindowsEventLogger(
  process.env.EVENT_LOG_SOURCE || 'MadridParkingAPI',
  process.env.EVENT_LOG_NAME || 'Application'
);

// Madrid Parking State
let parkingState = {
  id: 'madrid-parking-001',
  name: process.env.PARKING_NAME || 'Madrid Centro Parking',
  city: process.env.PARKING_CITY || 'Madrid',
  location: process.env.PARKING_LOCATION || 'Plaza Mayor, Madrid',
  numberOfLevels: 4,
  parkingSlotsPerLevel: 120,
  availableSlotsPerLevel: [95, 110, 88, 105], // Available slots per level
  workingHours: {
    open: '06:00',
    close: '23:00'
  },
  availableWC: 4,
  availableElectricChargers: 30,
  lastUpdated: new Date().toISOString()
};

// Request logging middleware
app.use((req, res, next) => {
  const startTime = Date.now();

  logger.logInfo('HTTP Request', {
    method: req.method,
    path: req.path,
    ip: req.ip,
    city: parkingState.city
  });

  res.on('finish', () => {
    const responseTimeMs = Date.now() - startTime;
    logger.logInfo('HTTP Response', {
      method: req.method,
      path: req.path,
      statusCode: res.statusCode,
      responseTimeMs,
      city: parkingState.city
    });
  });

  next();
});

app.use(createChaosMiddleware('madrid', {
  onChaosInject: (details) => {
    logger.logWarning('CHAOS_INJECTED', details);
  }
}));

// Health check endpoint
app.get('/health', (req, res) => {
  res.json({ 
    status: 'healthy', 
    timestamp: new Date().toISOString(),
    service: 'madrid-parking-api',
    city: parkingState.city,
    platform: process.platform,
    windowsEventLogging: logger.isAvailable(),
    loggingBackend: logger.getBackend()
  });
});

app.get('/health/logging', (req, res) => {
  res.json({
    loggingBackend: logger.getBackend(),
    windowsEventLogging: logger.isAvailable(),
    platform: process.platform,
    timestamp: new Date().toISOString()
  });
});

// Get parking information
app.get('/api/parking', async (req, res) => {
  try {
    logger.logOperation('GET_PARKING_INFO', parkingState.id, { city: parkingState.city });
    res.json({ success: true, data: parkingState });
  } catch (error) {
    logger.logError('GET_PARKING_INFO', error);
    res.status(500).json({ success: false, error: 'Failed to retrieve parking information' });
  }
});

// Get parking metrics
app.get('/api/parking/metrics', async (req, res) => {
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

    logger.logOperation('GET_METRICS', parkingState.id, metrics);
    res.json({ success: true, data: metrics });
  } catch (error) {
    logger.logError('GET_METRICS', error);
    res.status(500).json({ success: false, error: 'Failed to retrieve metrics' });
  }
});

// Get level information
app.get('/api/parking/levels', async (req, res) => {
  try {
    const levels = parkingState.availableSlotsPerLevel.map((available, index) => ({
      level: index,
      totalSlots: parkingState.parkingSlotsPerLevel,
      availableSlots: available,
      occupiedSlots: parkingState.parkingSlotsPerLevel - available,
      occupancyRate: ((parkingState.parkingSlotsPerLevel - available) / parkingState.parkingSlotsPerLevel * 100).toFixed(2)
    }));

    logger.logOperation('GET_LEVELS', parkingState.id, { levelsCount: levels.length });
    res.json({ success: true, data: levels });
  } catch (error) {
    logger.logError('GET_LEVELS', error);
    res.status(500).json({ success: false, error: 'Failed to retrieve level information' });
  }
});

// Get specific level information
app.get('/api/parking/levels/:levelNumber', async (req, res) => {
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

    logger.logOperation('GET_LEVEL', parkingState.id, { level: levelNumber });
    res.json({ success: true, data: levelInfo });
  } catch (error) {
    logger.logError('GET_LEVEL', error);
    res.status(500).json({ success: false, error: 'Failed to retrieve level information' });
  }
});

// Update available slots for a specific level
app.patch('/api/parking/levels/:levelNumber', async (req, res) => {
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

    logger.logOperation('UPDATE_LEVEL_SLOTS', parkingState.id, { 
      level: levelNumber,
      availableSlots
    });

    res.json({ success: true, data: parkingState });
  } catch (error) {
    logger.logError('UPDATE_LEVEL_SLOTS', error);
    res.status(500).json({ success: false, error: 'Failed to update level slots' });
  }
});

// Update parking configuration
app.put('/api/parking/config', async (req, res) => {
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

    logger.logOperation('UPDATE_CONFIG', parkingState.id, { 
      changes: Object.keys(req.body)
    });

    res.json({ success: true, data: parkingState });
  } catch (error) {
    logger.logError('UPDATE_CONFIG', error);
    res.status(500).json({ success: false, error: 'Failed to update configuration' });
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
    
    return newValue;
  });
  
  parkingState.lastUpdated = new Date().toISOString();
};

// Start parking simulation (update every 5 seconds)
setInterval(simulateParkingActivity, 5000);

app.use((err, req, res, next) => {
  logger.logError('UNHANDLED_API_ERROR', err);
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
if (useHttps) {
  const options = {
    key: fs.readFileSync(keyPath),
    cert: fs.readFileSync(certPath)
  };
  server = https.createServer(options, app);
  server.listen(PORT, () => {
    console.log(`🚗 ${parkingState.city} Parking API running on HTTPS port ${PORT}`);
    console.log(`📍 Location: ${parkingState.location}`);
    console.log(`🔒 Using HTTPS with self-signed certificate`);
    console.log(`🪟 Platform: ${process.platform}`);
    console.log(`📝 Windows Event Viewer: ${logger.isAvailable() ? 'Enabled' : 'Not available (using console logging)'}`);
    console.log(`🎲 Parking activity simulation: Enabled (updates every 5 seconds)`);
    
    // Log server start
    logger.logOperation('SERVER_START', parkingState.id, { 
      port: PORT,
      city: parkingState.city,
      protocol: 'HTTPS',
      platform: process.platform,
      environment: process.env.NODE_ENV || 'development'
    });
  });
} else {
  server = app.listen(PORT, () => {
    console.log(`🚗 ${parkingState.city} Parking API running on HTTP port ${PORT}`);
    console.log(`📍 Location: ${parkingState.location}`);
    console.log(`⚠️ Running without HTTPS (no certificate files found)`);
    console.log(`🪟 Platform: ${process.platform}`);
    console.log(`📝 Windows Event Viewer: ${logger.isAvailable() ? 'Enabled' : 'Not available (using console logging)'}`);
    console.log(`🎲 Parking activity simulation: Enabled (updates every 5 seconds)`);
    
    // Log server start
    logger.logOperation('SERVER_START', parkingState.id, { 
      port: PORT,
      city: parkingState.city,
      protocol: 'HTTP',
      platform: process.platform,
      environment: process.env.NODE_ENV || 'development'
    });
  });
}

// Graceful shutdown
process.on('SIGTERM', async () => {
  console.log('SIGTERM signal received: closing server');
  logger.logOperation('SERVER_SHUTDOWN', parkingState.id, { 
    city: parkingState.city,
    reason: 'SIGTERM' 
  });
  if (server) {
    server.close(() => {
      process.exit(0);
    });
  } else {
    process.exit(0);
  }
});

process.on('SIGINT', async () => {
  console.log('SIGINT signal received: closing server');
  logger.logOperation('SERVER_SHUTDOWN', parkingState.id, { 
    city: parkingState.city,
    reason: 'SIGINT' 
  });
  if (server) {
    server.close(() => {
      process.exit(0);
    });
  } else {
    process.exit(0);
  }
});
