/**
 * OpenTelemetry Metrics Tracker for Berlin Parking API
 * 
 * This module tracks various metrics in memory and exposes them
 * in OpenTelemetry format for external monitoring systems.
 */

class MetricsTracker {
  constructor() {
    // Server start time
    this.startTime = Date.now();
    this.lastRestartTimestamp = new Date().toISOString();

    // Request metrics
    this.totalRequests = 0;
    this.requestsByEndpoint = {};
    this.requestsByMethod = {};
    this.requestsPerMinute = [];
    
    // Response time tracking (store samples for percentile calculation)
    this.responseTimeSamples = [];
    this.maxResponseTimeSamples = 1000; // Keep last 1000 samples
    this.responseTimeByEndpoint = {};
    
    // Error tracking
    this.totalErrors = 0;
    this.errorsByType = {
      '4xx': 0,
      '5xx': 0
    };
    this.errorRate = 0;
    
    // Business metrics (parking occupancy)
    this.occupancyHistory = {
      last5min: [],
      last15min: [],
      last60min: []
    };
    this.totalCarsEntered = 0;
    this.totalCarsExited = 0;
    this.peakOccupancyLastHour = 0;
    
    // Infrastructure metrics (mocked)
    this.cpuUsage = 0;
    this.memoryUsage = 0;
    this.diskUsage = 0;
    
    // Start background tasks
    this._startBackgroundTasks();
  }

  /**
   * Track an incoming request
   */
  trackRequest(method, endpoint) {
    this.totalRequests++;
    
    // Track by method
    this.requestsByMethod[method] = (this.requestsByMethod[method] || 0) + 1;
    
    // Track by endpoint
    const normalizedEndpoint = this._normalizeEndpoint(endpoint);
    this.requestsByEndpoint[normalizedEndpoint] = (this.requestsByEndpoint[normalizedEndpoint] || 0) + 1;
    
    // Track requests per minute
    const currentMinute = Math.floor(Date.now() / 60000);
    const lastEntry = this.requestsPerMinute[this.requestsPerMinute.length - 1];
    
    if (!lastEntry || lastEntry.minute !== currentMinute) {
      this.requestsPerMinute.push({ minute: currentMinute, count: 1 });
      // Keep only last 60 minutes
      if (this.requestsPerMinute.length > 60) {
        this.requestsPerMinute.shift();
      }
    } else {
      lastEntry.count++;
    }
  }

  /**
   * Track response time for a request
   */
  trackResponseTime(endpoint, responseTimeMs) {
    // Store in global samples
    this.responseTimeSamples.push(responseTimeMs);
    if (this.responseTimeSamples.length > this.maxResponseTimeSamples) {
      this.responseTimeSamples.shift();
    }
    
    // Store by endpoint
    const normalizedEndpoint = this._normalizeEndpoint(endpoint);
    if (!this.responseTimeByEndpoint[normalizedEndpoint]) {
      this.responseTimeByEndpoint[normalizedEndpoint] = [];
    }
    this.responseTimeByEndpoint[normalizedEndpoint].push(responseTimeMs);
    if (this.responseTimeByEndpoint[normalizedEndpoint].length > 100) {
      this.responseTimeByEndpoint[normalizedEndpoint].shift();
    }
  }

  /**
   * Track an error
   */
  trackError(statusCode) {
    this.totalErrors++;
    
    if (statusCode >= 400 && statusCode < 500) {
      this.errorsByType['4xx']++;
    } else if (statusCode >= 500) {
      this.errorsByType['5xx']++;
    }
    
    // Calculate error rate
    this.errorRate = this.totalRequests > 0 
      ? (this.totalErrors / this.totalRequests * 100).toFixed(2)
      : 0;
  }

  /**
   * Track parking occupancy for business metrics
   */
  trackOccupancy(occupancyRate) {
    const now = Date.now();
    const occupancyData = {
      timestamp: now,
      rate: occupancyRate
    };
    
    // Add to all time windows
    this.occupancyHistory.last5min.push(occupancyData);
    this.occupancyHistory.last15min.push(occupancyData);
    this.occupancyHistory.last60min.push(occupancyData);
    
    // Clean up old data
    const fiveMinAgo = now - (5 * 60 * 1000);
    const fifteenMinAgo = now - (15 * 60 * 1000);
    const sixtyMinAgo = now - (60 * 60 * 1000);
    
    this.occupancyHistory.last5min = this.occupancyHistory.last5min.filter(d => d.timestamp > fiveMinAgo);
    this.occupancyHistory.last15min = this.occupancyHistory.last15min.filter(d => d.timestamp > fifteenMinAgo);
    this.occupancyHistory.last60min = this.occupancyHistory.last60min.filter(d => d.timestamp > sixtyMinAgo);
    
    // Update peak occupancy
    if (this.occupancyHistory.last60min.length > 0) {
      this.peakOccupancyLastHour = Math.max(...this.occupancyHistory.last60min.map(d => d.rate));
    }
  }

  /**
   * Simulate car entry (for business metrics)
   */
  simulateCarEntry() {
    this.totalCarsEntered++;
  }

  /**
   * Simulate car exit (for business metrics)
   */
  simulateCarExit() {
    this.totalCarsExited++;
  }

  /**
   * Calculate percentile from samples
   */
  _calculatePercentile(samples, percentile) {
    if (samples.length === 0) return 0;
    
    const sorted = [...samples].sort((a, b) => a - b);
    const index = Math.ceil((percentile / 100) * sorted.length) - 1;
    return sorted[Math.max(0, index)];
  }

  /**
   * Calculate average
   */
  _calculateAverage(samples) {
    if (samples.length === 0) return 0;
    const sum = samples.reduce((a, b) => a + b, 0);
    return sum / samples.length;
  }

  /**
   * Calculate average occupancy for a time window
   */
  _calculateAverageOccupancy(timeWindow) {
    if (timeWindow.length === 0) return 0;
    const sum = timeWindow.reduce((a, b) => a + b.rate, 0);
    return sum / timeWindow.length;
  }

  /**
   * Normalize endpoint for tracking (remove dynamic params)
   */
  _normalizeEndpoint(endpoint) {
    return endpoint
      .replace(/\/\d+/g, '/:id')
      .replace(/\?.*$/, '');
  }

  /**
   * Get uptime in seconds
   */
  getUptimeSeconds() {
    return Math.floor((Date.now() - this.startTime) / 1000);
  }

  /**
   * Calculate availability percentage (mock - assume 99.9% for simulation)
   */
  getAvailabilityPercentage() {
    // In real scenario, this would track downtime
    // For simulation, we'll use a high value with slight random variation
    return 99.9 - (Math.random() * 0.1);
  }

  /**
   * Mock infrastructure metrics with realistic random values
   */
  _updateInfrastructureMetrics() {
    // CPU usage: realistic variation around 15-45%
    this.cpuUsage = 15 + (Math.random() * 30);
    
    // Memory usage: realistic variation around 40-70%
    this.memoryUsage = 40 + (Math.random() * 30);
    
    // Disk usage: slowly increasing around 35-55%
    this.diskUsage = 35 + (Math.random() * 20);
  }

  /**
   * Start background tasks (update infrastructure metrics)
   */
  _startBackgroundTasks() {
    // Update infrastructure metrics every 10 seconds
    setInterval(() => {
      this._updateInfrastructureMetrics();
    }, 10000);
  }

  /**
   * Get requests per minute (current)
   */
  getRequestsPerMinute() {
    const currentMinute = Math.floor(Date.now() / 60000);
    const currentEntry = this.requestsPerMinute.find(e => e.minute === currentMinute);
    return currentEntry ? currentEntry.count : 0;
  }

  /**
   * Export metrics in OpenTelemetry format
   */
  getOpenTelemetryMetrics(currentOccupancyRate) {
    const now = Date.now();
    const avgResponseTime = this._calculateAverage(this.responseTimeSamples);
    const p95ResponseTime = this._calculatePercentile(this.responseTimeSamples, 95);
    const p99ResponseTime = this._calculatePercentile(this.responseTimeSamples, 99);

    return {
      resourceMetrics: [{
        resource: {
          attributes: [
            { key: 'service.name', value: { stringValue: 'berlin-parking-api' }},
            { key: 'service.instance.id', value: { stringValue: 'berlin-parking-001' }},
            { key: 'service.version', value: { stringValue: '1.0.0' }},
            { key: 'deployment.environment', value: { stringValue: process.env.NODE_ENV || 'development' }}
          ]
        },
        scopeMetrics: [{
          scope: {
            name: 'berlin-parking-metrics',
            version: '1.0.0'
          },
          metrics: [
            // Response Time Metrics
            {
              name: 'http.server.duration',
              description: 'HTTP request duration',
              unit: 'ms',
              histogram: {
                dataPoints: [{
                  attributes: [],
                  count: this.responseTimeSamples.length.toString(),
                  sum: this.responseTimeSamples.reduce((a, b) => a + b, 0),
                  min: this.responseTimeSamples.length > 0 ? Math.min(...this.responseTimeSamples) : 0,
                  max: this.responseTimeSamples.length > 0 ? Math.max(...this.responseTimeSamples) : 0,
                  quantileValues: [
                    { quantile: 0.5, value: this._calculatePercentile(this.responseTimeSamples, 50) },
                    { quantile: 0.95, value: p95ResponseTime },
                    { quantile: 0.99, value: p99ResponseTime }
                  ]
                }]
              }
            },
            {
              name: 'http.server.duration.avg',
              description: 'Average HTTP request duration',
              unit: 'ms',
              gauge: {
                dataPoints: [{
                  asDouble: avgResponseTime,
                  timeUnixNano: now.toString()
                }]
              }
            },
            {
              name: 'http.server.duration.p95',
              description: '95th percentile HTTP request duration',
              unit: 'ms',
              gauge: {
                dataPoints: [{
                  asDouble: p95ResponseTime,
                  timeUnixNano: now.toString()
                }]
              }
            },
            {
              name: 'http.server.duration.p99',
              description: '99th percentile HTTP request duration',
              unit: 'ms',
              gauge: {
                dataPoints: [{
                  asDouble: p99ResponseTime,
                  timeUnixNano: now.toString()
                }]
              }
            },

            // Request Count/Throughput Metrics
            {
              name: 'http.server.request.count',
              description: 'Total HTTP requests',
              unit: '1',
              sum: {
                dataPoints: [{
                  asInt: this.totalRequests.toString(),
                  timeUnixNano: now.toString()
                }],
                aggregationTemporality: 'AGGREGATION_TEMPORALITY_CUMULATIVE',
                isMonotonic: true
              }
            },
            {
              name: 'http.server.requests_per_minute',
              description: 'HTTP requests per minute',
              unit: '1/min',
              gauge: {
                dataPoints: [{
                  asInt: this.getRequestsPerMinute().toString(),
                  timeUnixNano: now.toString()
                }]
              }
            },

            // Error Rate Metrics
            {
              name: 'http.server.error.count',
              description: 'Total HTTP errors',
              unit: '1',
              sum: {
                dataPoints: [{
                  asInt: this.totalErrors.toString(),
                  timeUnixNano: now.toString()
                }],
                aggregationTemporality: 'AGGREGATION_TEMPORALITY_CUMULATIVE',
                isMonotonic: true
              }
            },
            {
              name: 'http.server.error.rate',
              description: 'HTTP error rate percentage',
              unit: '%',
              gauge: {
                dataPoints: [{
                  asDouble: parseFloat(this.errorRate),
                  timeUnixNano: now.toString()
                }]
              }
            },
            {
              name: 'http.server.error.4xx',
              description: 'Total 4xx errors',
              unit: '1',
              sum: {
                dataPoints: [{
                  asInt: this.errorsByType['4xx'].toString(),
                  timeUnixNano: now.toString()
                }],
                aggregationTemporality: 'AGGREGATION_TEMPORALITY_CUMULATIVE',
                isMonotonic: true
              }
            },
            {
              name: 'http.server.error.5xx',
              description: 'Total 5xx errors',
              unit: '1',
              sum: {
                dataPoints: [{
                  asInt: this.errorsByType['5xx'].toString(),
                  timeUnixNano: now.toString()
                }],
                aggregationTemporality: 'AGGREGATION_TEMPORALITY_CUMULATIVE',
                isMonotonic: true
              }
            },

            // Availability/Uptime Metrics
            {
              name: 'system.uptime',
              description: 'System uptime',
              unit: 's',
              gauge: {
                dataPoints: [{
                  asInt: this.getUptimeSeconds().toString(),
                  timeUnixNano: now.toString()
                }]
              }
            },
            {
              name: 'system.availability',
              description: 'System availability percentage',
              unit: '%',
              gauge: {
                dataPoints: [{
                  asDouble: this.getAvailabilityPercentage(),
                  timeUnixNano: now.toString()
                }]
              }
            },
            {
              name: 'system.last_restart',
              description: 'Last restart timestamp',
              unit: 'timestamp',
              gauge: {
                dataPoints: [{
                  asString: this.lastRestartTimestamp,
                  timeUnixNano: now.toString()
                }]
              }
            },

            // Custom Business Metrics
            {
              name: 'parking.occupancy.current',
              description: 'Current parking occupancy rate',
              unit: '%',
              gauge: {
                dataPoints: [{
                  asDouble: currentOccupancyRate,
                  timeUnixNano: now.toString()
                }]
              }
            },
            {
              name: 'parking.occupancy.avg_5min',
              description: 'Average parking occupancy over last 5 minutes',
              unit: '%',
              gauge: {
                dataPoints: [{
                  asDouble: this._calculateAverageOccupancy(this.occupancyHistory.last5min),
                  timeUnixNano: now.toString()
                }]
              }
            },
            {
              name: 'parking.occupancy.avg_15min',
              description: 'Average parking occupancy over last 15 minutes',
              unit: '%',
              gauge: {
                dataPoints: [{
                  asDouble: this._calculateAverageOccupancy(this.occupancyHistory.last15min),
                  timeUnixNano: now.toString()
                }]
              }
            },
            {
              name: 'parking.occupancy.avg_60min',
              description: 'Average parking occupancy over last 60 minutes',
              unit: '%',
              gauge: {
                dataPoints: [{
                  asDouble: this._calculateAverageOccupancy(this.occupancyHistory.last60min),
                  timeUnixNano: now.toString()
                }]
              }
            },
            {
              name: 'parking.occupancy.peak_1hour',
              description: 'Peak parking occupancy in the last hour',
              unit: '%',
              gauge: {
                dataPoints: [{
                  asDouble: this.peakOccupancyLastHour,
                  timeUnixNano: now.toString()
                }]
              }
            },
            {
              name: 'parking.cars.entered',
              description: 'Total cars entered (simulated)',
              unit: '1',
              sum: {
                dataPoints: [{
                  asInt: this.totalCarsEntered.toString(),
                  timeUnixNano: now.toString()
                }],
                aggregationTemporality: 'AGGREGATION_TEMPORALITY_CUMULATIVE',
                isMonotonic: true
              }
            },
            {
              name: 'parking.cars.exited',
              description: 'Total cars exited (simulated)',
              unit: '1',
              sum: {
                dataPoints: [{
                  asInt: this.totalCarsExited.toString(),
                  timeUnixNano: now.toString()
                }],
                aggregationTemporality: 'AGGREGATION_TEMPORALITY_CUMULATIVE',
                isMonotonic: true
              }
            },

            // Infrastructure Metrics (mocked)
            {
              name: 'system.cpu.usage',
              description: 'CPU usage percentage (mocked)',
              unit: '%',
              gauge: {
                dataPoints: [{
                  asDouble: this.cpuUsage,
                  timeUnixNano: now.toString()
                }]
              }
            },
            {
              name: 'system.memory.usage',
              description: 'Memory usage percentage (mocked)',
              unit: '%',
              gauge: {
                dataPoints: [{
                  asDouble: this.memoryUsage,
                  timeUnixNano: now.toString()
                }]
              }
            },
            {
              name: 'system.disk.usage',
              description: 'Disk usage percentage (mocked)',
              unit: '%',
              gauge: {
                dataPoints: [{
                  asDouble: this.diskUsage,
                  timeUnixNano: now.toString()
                }]
              }
            }
          ]
        }]
      }]
    };
  }
}

module.exports = MetricsTracker;
