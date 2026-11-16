/**
 * Syslog Logger for Linux systems
 * 
 * Logs parking operations to syslog using the POSIX syslog API
 * Falls back to console logging if syslog is not available
 */

let posix = null;
let isSyslogAvailable = false;
const { spawnSync } = require('child_process');

// Try to load posix module (only available on Linux/Unix with syslog)
try {
  posix = require('posix');
  isSyslogAvailable = true;
  console.log('[Syslog Logger] Syslog logging is available');
} catch (error) {
  console.log('[Syslog Logger] Syslog not available (posix module not installed or not on Linux)');
  console.log('[Syslog Logger] Falling back to console logging');
}

// Syslog severity levels (RFC 5424)
const SEVERITY = {
  EMERG: 0,    // Emergency: system is unusable
  ALERT: 1,    // Alert: action must be taken immediately
  CRIT: 2,     // Critical: critical conditions
  ERR: 3,      // Error: error conditions
  WARNING: 4,  // Warning: warning conditions
  NOTICE: 5,   // Notice: normal but significant condition
  INFO: 6,     // Informational: informational messages
  DEBUG: 7     // Debug: debug-level messages
};

// Syslog facilities (RFC 5424)
const FACILITY = {
  KERN: 0,     // kernel messages
  USER: 1,     // user-level messages
  MAIL: 2,     // mail system
  DAEMON: 3,   // system daemons
  AUTH: 4,     // security/authorization messages
  SYSLOG: 5,   // messages generated internally by syslogd
  LPR: 6,      // line printer subsystem
  NEWS: 7,     // network news subsystem
  UUCP: 8,     // UUCP subsystem
  CRON: 9,     // clock daemon
  AUTHPRIV: 10, // security/authorization messages (private)
  FTP: 11,     // FTP daemon
  LOCAL0: 16,  // local use 0
  LOCAL1: 17,  // local use 1
  LOCAL2: 18,  // local use 2
  LOCAL3: 19,  // local use 3
  LOCAL4: 20,  // local use 4
  LOCAL5: 21,  // local use 5
  LOCAL6: 22,  // local use 6
  LOCAL7: 23   // local use 7
};

class SyslogLogger {
  constructor(facility, tag) {
    this.facilityName = facility || 'local0';
    this.tag = tag || 'ParisParkingAPI';
    this.facility = FACILITY[this.facilityName.toUpperCase()] || FACILITY.LOCAL0;
    this.isInitialized = false;
    this.loggerBinaryAvailable = this._checkLoggerBinary();

    if (isSyslogAvailable && posix) {
      try {
        // Open syslog connection
        // Options: LOG_PID (include PID), LOG_CONS (write to console if syslog unavailable)
        posix.openlog(this.tag, { cons: true, pid: true }, this.facility);
        this.isInitialized = true;
        console.log(`[Syslog Logger] Initialized with facility: ${this.facilityName}, tag: ${this.tag}`);
      } catch (error) {
        console.error('[Syslog Logger] Failed to initialize syslog:', error.message);
        console.log('[Syslog Logger] Falling back to console logging');
      }
    }

    if (!this.isInitialized && this.loggerBinaryAvailable) {
      console.log(`[Syslog Logger] Using Linux logger command fallback with facility: ${this.facilityName}, tag: ${this.tag}`);
    }
  }

  _checkLoggerBinary() {
    try {
      const check = spawnSync('logger', ['--version'], { stdio: 'ignore' });
      return check.status === 0 || check.status === 1;
    } catch (_error) {
      return false;
    }
  }

  _severityToName(severity) {
    return Object.keys(SEVERITY).find(key => SEVERITY[key] === severity) || 'INFO';
  }

  _severityToPriority(severityName) {
    const normalized = (severityName || 'INFO').toLowerCase();
    switch (normalized) {
      case 'emerg':
      case 'alert':
      case 'crit':
      case 'err':
      case 'warning':
      case 'notice':
      case 'info':
      case 'debug':
        return normalized;
      default:
        return 'info';
    }
  }

  _logWithLoggerCommand(severityName, message, details, timestamp) {
    if (!this.loggerBinaryAvailable) {
      return false;
    }

    try {
      const priority = `${this.facilityName.toLowerCase()}.${this._severityToPriority(severityName)}`;
      const syslogMessage = JSON.stringify({
        message,
        details,
        timestamp
      });

      const result = spawnSync('logger', ['-t', this.tag, '-p', priority, syslogMessage], { stdio: 'ignore' });
      return result.status === 0;
    } catch (error) {
      console.error('[Syslog Logger] Error writing with logger command:', error.message);
      return false;
    }
  }

  /**
   * Log a message to syslog
   */
  _log(severity, message, details = {}) {
    const severityName = this._severityToName(severity);
    const logEntry = {
      timestamp: new Date().toISOString(),
      level: severityName,
      message,
      details,
      tag: this.tag
    };

    if (this.isInitialized && posix) {
      try {
        // Format message for syslog
        const syslogMessage = JSON.stringify({
          message,
          details,
          timestamp: logEntry.timestamp
        });
        
        posix.syslog(severity, syslogMessage);
        return;
      } catch (error) {
        console.error('[Syslog Logger] Error writing to syslog:', error.message);
      }
    }

    const commandLogged = this._logWithLoggerCommand(
      severityName,
      message,
      details,
      logEntry.timestamp
    );

    if (!commandLogged) {
      this._consoleLog(logEntry);
    }
  }

  /**
   * Log an informational message
   */
  logInfo(message, details = {}) {
    this._log(SEVERITY.INFO, message, details);
  }

  /**
   * Log a notice (normal but significant)
   */
  logNotice(message, details = {}) {
    this._log(SEVERITY.NOTICE, message, details);
  }

  /**
   * Log a warning
   */
  logWarning(message, details = {}) {
    this._log(SEVERITY.WARNING, message, details);
  }

  /**
   * Log an error
   */
  logError(message, error, details = {}) {
    const errorDetails = {
      ...details,
      error: error?.message || String(error),
      stack: error instanceof Error ? error.stack : undefined
    };
    this._log(SEVERITY.ERR, message, errorDetails);
  }

  /**
   * Log a critical error
   */
  logCritical(message, details = {}) {
    this._log(SEVERITY.CRIT, message, details);
  }

  /**
   * Log a parking operation
   */
  logOperation(operation, parkId, details = {}) {
    const message = `Parking Operation: ${operation}`;
    this.logInfo(message, { operation, parkId, ...details });
  }

  /**
   * Fallback to console logging
   */
  _consoleLog(logEntry) {
    const prefix = `[Syslog ${logEntry.level}]`;
    
    switch (logEntry.level) {
      case 'ERR':
      case 'CRIT':
      case 'ALERT':
      case 'EMERG':
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
   * Check if syslog is available
   */
  isAvailable() {
    return this.isInitialized || this.loggerBinaryAvailable;
  }

  /**
   * Close syslog connection
   */
  close() {
    if (this.isInitialized && posix) {
      try {
        posix.closelog();
        console.log('[Syslog Logger] Closed syslog connection');
      } catch (error) {
        console.error('[Syslog Logger] Error closing syslog:', error.message);
      }
    }
  }
}

module.exports = SyslogLogger;
