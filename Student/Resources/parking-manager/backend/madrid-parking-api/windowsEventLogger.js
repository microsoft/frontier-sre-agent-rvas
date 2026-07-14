/**
 * Windows Event Viewer Logger
 * 
 * Logs parking operations to Windows Event Viewer
 * For non-Windows systems, falls back to console logging
 */

let EventLogger = null;
let isWindowsLoggingAvailable = false;
const { spawnSync } = require('child_process');
const isWindows = process.platform === 'win32';

// Try to load node-windows module (only available on Windows)
try {
  EventLogger = require('node-windows').EventLogger;
  isWindowsLoggingAvailable = true;
  console.log('[Event Logger] Windows Event Viewer logging is available');
} catch (error) {
  if (isWindows) {
    console.log(`[Event Logger] node-windows module unavailable on Windows: ${error.message}`);
    console.log('[Event Logger] Will attempt fallback logging via eventcreate.exe');
  } else {
    console.log('[Event Logger] Windows Event Viewer not available (not running on Windows)');
    console.log('[Event Logger] Falling back to console logging');
  }
}

class WindowsEventLogger {
  constructor(eventSource, eventLog) {
    this.eventSource = eventSource || 'MadridParkingAPI';
    this.eventLog = eventLog || 'Application';
    this.logger = null;
    this.hasEventCreate = false;
    this.preferredBackend = (process.env.EVENT_LOG_BACKEND || 'auto').toLowerCase();

    if (isWindows) {
      this.hasEventCreate = this._canUseEventCreate();
    }

    this.activeBackend = 'console';
    if (this.hasEventCreate) {
      this.activeBackend = 'eventcreate';
    }

    if (isWindowsLoggingAvailable && this.preferredBackend !== 'eventcreate' && this.preferredBackend !== 'console') {
      try {
        this.logger = new EventLogger(this.eventSource);
        this.activeBackend = 'node-windows';
        console.log(`[Event Logger] Initialized with source: ${this.eventSource}`);
      } catch (error) {
        console.error('[Event Logger] Failed to initialize Windows Event Logger:', error.message);
        console.log('[Event Logger] Falling back to console logging');
        this.logger = null;
      }
    }

    if (!this.logger && this.preferredBackend === 'node-windows') {
      console.error('[Event Logger] EVENT_LOG_BACKEND=node-windows but node-windows backend is unavailable');
    }

    if (!isWindows && (this.preferredBackend === 'node-windows' || this.preferredBackend === 'eventcreate')) {
      console.warn('[Event Logger] Requested Windows-only backend on non-Windows platform; falling back to console');
    }
  }

  /**
   * Log an informational event
   */
  logInfo(message, details = {}) {
    const logEntry = {
      timestamp: new Date().toISOString(),
      level: 'INFO',
      message,
      details,
      source: this.eventSource
    };

    this._writeLog(logEntry, 'info');
  }

  /**
   * Log a warning event
   */
  logWarning(message, details = {}) {
    const logEntry = {
      timestamp: new Date().toISOString(),
      level: 'WARNING',
      message,
      details,
      source: this.eventSource
    };

    this._writeLog(logEntry, 'warn');
  }

  /**
   * Log an error event
   */
  logError(message, error, details = {}) {
    const logEntry = {
      timestamp: new Date().toISOString(),
      level: 'ERROR',
      message,
      error: error.message || error,
      stack: error instanceof Error ? error.stack : undefined,
      details,
      source: this.eventSource
    };

    this._writeLog(logEntry, 'error');
  }

  /**
   * Log parking operation
   */
  logOperation(operation, parkId, details = {}) {
    const message = `Parking Operation: ${operation}`;
    this.logInfo(message, { operation, parkId, ...details });
  }

  _writeLog(logEntry, levelMethod) {
    if (this.preferredBackend === 'console') {
      this.activeBackend = 'console';
      this._consoleLog(logEntry);
      return;
    }

    if (this.preferredBackend === 'eventcreate') {
      if (this._writeViaEventCreate(logEntry)) {
        this.activeBackend = 'eventcreate';
        return;
      }

      this.activeBackend = 'console';
      this._consoleLog(logEntry);
      return;
    }

    if (this.preferredBackend === 'node-windows') {
      if (this.logger) {
        try {
          this.logger[levelMethod](JSON.stringify(logEntry, null, 2));
          this.activeBackend = 'node-windows';
          return;
        } catch (error) {
          console.error('[Event Logger] Error writing to Event Viewer via node-windows:', error.message);
        }
      }

      this.activeBackend = 'console';
      this._consoleLog(logEntry);
      return;
    }

    if (this.logger) {
      try {
        this.logger[levelMethod](JSON.stringify(logEntry, null, 2));
        this.activeBackend = 'node-windows';
        return;
      } catch (error) {
        console.error('[Event Logger] Error writing to Event Viewer via node-windows:', error.message);
      }
    }

    if (this._writeViaEventCreate(logEntry)) {
      this.activeBackend = 'eventcreate';
      return;
    }

    this.activeBackend = 'console';
    this._consoleLog(logEntry);
  }

  _writeViaEventCreate(logEntry) {
    if (!isWindows || !this.hasEventCreate) {
      return false;
    }

    const levelMap = {
      INFO: 'INFORMATION',
      WARNING: 'WARNING',
      ERROR: 'ERROR'
    };

    const eventIdMap = {
      INFO: '1000',
      WARNING: '1001',
      ERROR: '1002'
    };

    const entryType = levelMap[logEntry.level] || 'INFORMATION';
    const eventId = eventIdMap[logEntry.level] || '1000';
    const payload = JSON.stringify(logEntry);
    const maxMessageLength = 30000;
    const message = payload.length > maxMessageLength
      ? `${payload.slice(0, maxMessageLength)}...`
      : payload;

    const result = spawnSync(
      'eventcreate',
      [
        '/L', this.eventLog,
        '/SO', this.eventSource,
        '/T', entryType,
        '/ID', eventId,
        '/D', message
      ],
      { windowsHide: true, encoding: 'utf8' }
    );

    if (result.status === 0) {
      return true;
    }

    const errorOutput = (result.stderr || result.stdout || '').trim();
    console.error('[Event Logger] eventcreate fallback failed:', errorOutput || 'Unknown error');
    return false;
  }

  /**
   * Fallback to console logging
   */
  _consoleLog(logEntry) {
    const prefix = `[Event Viewer ${logEntry.level}]`;
    
    switch (logEntry.level) {
      case 'ERROR':
        console.error(prefix, JSON.stringify(logEntry, null, 2));
        break;
      case 'WARNING':
        console.warn(prefix, JSON.stringify(logEntry, null, 2));
        break;
      default:
        console.log(prefix, JSON.stringify(logEntry, null, 2));
    }
  }

  /**
   * Check if Windows Event Viewer logging is available
   */
  isAvailable() {
    return this.logger !== null || this.hasEventCreate;
  }

  getBackend() {
    return this.activeBackend;
  }

  _canUseEventCreate() {
    const check = spawnSync('where', ['eventcreate'], { windowsHide: true, encoding: 'utf8' });
    return check.status === 0;
  }
}

module.exports = WindowsEventLogger;
