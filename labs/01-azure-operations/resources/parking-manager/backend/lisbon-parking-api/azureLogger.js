const crypto = require('crypto');
const axios = require('axios');

class AzureLogAnalytics {
  constructor(workspaceId, sharedKey, logType) {
    this.workspaceId = workspaceId;
    this.sharedKey = sharedKey;
    this.logType = logType;
  }

  /**
   * Build the authorization signature for Azure Log Analytics
   */
  buildSignature(date, contentLength, method, contentType, resource) {
    const xHeaders = `x-ms-date:${date}`;
    const stringToHash = `${method}\n${contentLength}\n${contentType}\n${xHeaders}\n${resource}`;
    const bytesToHash = Buffer.from(stringToHash, 'utf8');
    const keyBytes = Buffer.from(this.sharedKey, 'base64');
    const hmac = crypto.createHmac('sha256', keyBytes);
    hmac.update(bytesToHash);
    const calculatedHash = hmac.digest('base64');
    return `SharedKey ${this.workspaceId}:${calculatedHash}`;
  }

  /**
   * Send custom log to Azure Log Analytics
   */
  async sendLog(logData) {
    if (!this.workspaceId || !this.sharedKey || this.workspaceId === 'your-workspace-id') {
      console.log('[Azure Log Analytics] Not configured - Log would be sent:', logData);
      return { success: false, message: 'Azure Log Analytics not configured' };
    }

    const body = JSON.stringify(logData);
    const contentLength = Buffer.byteLength(body, 'utf8');
    const rfc1123date = new Date().toUTCString();
    const contentType = 'application/json';
    const method = 'POST';
    const resource = '/api/logs';

    const signature = this.buildSignature(
      rfc1123date,
      contentLength,
      method,
      contentType,
      resource
    );

    const uri = `https://${this.workspaceId}.ods.opinsights.azure.com${resource}?api-version=2016-04-01`;

    try {
      const response = await axios.post(uri, body, {
        headers: {
          'Content-Type': contentType,
          'Authorization': signature,
          'Log-Type': this.logType,
          'x-ms-date': rfc1123date,
          'time-generated-field': 'timestamp'
        }
      });

      console.log(`[Azure Log Analytics] Log sent successfully: ${response.status}`);
      return { success: true, status: response.status };
    } catch (error) {
      console.error('[Azure Log Analytics] Error sending log:', error.message);
      return { success: false, error: error.message };
    }
  }

  /**
   * Log parking operation
   */
  async logOperation(operation, parkId, details = {}) {
    const logEntry = {
      timestamp: new Date().toISOString(),
      operation,
      parkId,
      details,
      level: 'INFO'
    };

    await this.sendLog([logEntry]);
  }

  /**
   * Log error
   */
  async logError(operation, error, details = {}) {
    const logEntry = {
      timestamp: new Date().toISOString(),
      operation,
      error: error.message || error,
      details,
      level: 'ERROR'
    };

    await this.sendLog([logEntry]);
  }
}

module.exports = AzureLogAnalytics;
