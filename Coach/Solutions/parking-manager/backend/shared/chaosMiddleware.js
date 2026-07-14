const DEFAULT_CONTROL_URL = process.env.CHAOS_CONTROL_URL || 'http://localhost:3090';
const CACHE_TTL_MS = Number(process.env.CHAOS_CACHE_TTL_MS || 2000);
const DEFAULT_MAX_MEMORY_HOLDS = Number(process.env.CHAOS_HIGH_MEMORY_MAX_CONCURRENT || 2);
const memoryHolds = [];

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

const requestMatches = (req, config) => {
  const method = (config.method || '*').toUpperCase();
  if (method !== '*' && req.method.toUpperCase() !== method) {
    return false;
  }

  const pathPattern = config.pathPattern || '/api';
  return req.path.startsWith(pathPattern);
};

const buildCache = () => ({
  fetchedAt: 0,
  data: null,
  fetchInFlight: null
});

const loadState = async (controlUrl, cache) => {
  const now = Date.now();

  if (cache.data && now - cache.fetchedAt < CACHE_TTL_MS) {
    return cache.data;
  }

  if (cache.fetchInFlight) {
    return cache.fetchInFlight;
  }

  cache.fetchInFlight = fetch(`${controlUrl}/api/chaos/state`, {
    headers: { Accept: 'application/json' }
  })
    .then(async (response) => {
      if (!response.ok) {
        throw new Error(`Chaos state fetch failed: ${response.status}`);
      }
      const json = await response.json();
      cache.data = json.data;
      cache.fetchedAt = Date.now();
      return cache.data;
    })
    .catch(() => cache.data)
    .finally(() => {
      cache.fetchInFlight = null;
    });

  return cache.fetchInFlight;
};

const faultHandlers = {
  async latency(req, res, next, config) {
    const delayMs = Number(config.delayMs || 0);
    if (delayMs > 0) {
      await sleep(delayMs);
    }
    return next();
  },

  async httpError(req, res, next, config) {
    const statusCode = Number(config.statusCode || 500);
    const errorMessage = config.errorMessage || 'Chaos simulated HTTP error';
    return res.status(statusCode).json({
      success: false,
      chaos: true,
      error: errorMessage,
      statusCode
    });
  },

  async dependencyFailure(req, res, next, config) {
    const statusCode = Number(config.statusCode || 503);
    const errorMessage = config.errorMessage || 'External dependency failure (simulated)';
    const dependency = config.dependencyName || 'external-dependency';

    return res.status(statusCode).json({
      success: false,
      chaos: true,
      code: 'DEPENDENCY_FAILURE',
      dependency,
      error: errorMessage,
      statusCode
    });
  },

  async exception(req, res, next, config) {
    const errorMessage = config.errorMessage || 'Chaos simulated exception';
    const chaosError = new Error(errorMessage);
    chaosError.isChaosException = true;
    chaosError.chaosFaultType = 'exception';
    return next(chaosError);
  },

  async disconnect(req, res) {
    if (res.socket) {
      res.socket.destroy();
      return;
    }
    res.destroy();
  },

  async timeout() {
    return;
  },

  async badPayload(req, res) {
    res.status(200);
    res.setHeader('Content-Type', 'application/json');
    res.send('{"success": true, "data": ');
  },

  async httpsError(req, res, next, config) {
    const statusCode = Number(config.statusCode || 525);
    const errorMessage = config.errorMessage || 'SSL handshake failed (simulated)';
    return res.status(statusCode).json({
      success: false,
      chaos: true,
      error: errorMessage,
      statusCode
    });
  },

  async highCpu(req, res, next, config) {
    const burnMs = Number(config.cpuBurnMs || config.delayMs || 2000);
    const endTime = Date.now() + Math.max(100, burnMs);

    let work = 0;
    while (Date.now() < endTime) {
      work += Math.sqrt(Math.random() * 1000);
    }

    if (work < 0) {
      return next(new Error('Unexpected CPU simulation result'));
    }

    return next();
  },

  async highMemory(req, res, next, config, context) {
    const memoryMb = Math.max(8, Number(config.memoryMb || 128));
    const holdMs = Number(config.delayMs || 5000);
    const serviceName = context?.serviceName || 'unknown';
    const maxMemoryHolds = Math.max(
      1,
      Number(config.maxMemoryHolds || DEFAULT_MAX_MEMORY_HOLDS)
    );

    const serviceHolds = memoryHolds.filter((item) => item.serviceName === serviceName).length;
    if (serviceHolds >= maxMemoryHolds) {
      return res.status(429).json({
        success: false,
        chaos: true,
        error: 'High memory chaos limit reached for service',
        service: serviceName,
        maxMemoryHolds,
        activeHolds: serviceHolds
      });
    }

    const bytes = memoryMb * 1024 * 1024;

    try {
      const holdBuffer = Buffer.alloc(bytes, 1);
      const holdEntry = { serviceName, holdBuffer };
      memoryHolds.push(holdEntry);

      setTimeout(() => {
        const index = memoryHolds.indexOf(holdEntry);
        if (index >= 0) {
          memoryHolds.splice(index, 1);
        }
      }, Math.max(500, holdMs));

      return next();
    } catch (error) {
      return next(new Error(`High memory chaos failed: ${error.message}`));
    }
  }
};

const createChaosMiddleware = (serviceName, options = {}) => {
  const controlUrl = options.controlUrl || DEFAULT_CONTROL_URL;
  const cache = buildCache();
  const onChaosInject = options.onChaosInject;

  return async (req, res, next) => {
    if (req.path === '/health') {
      return next();
    }

    const state = await loadState(controlUrl, cache);
    if (!state || !state.globalEnabled) {
      return next();
    }

    const serviceConfig = state.services && state.services[serviceName];
    if (!serviceConfig || !serviceConfig.enabled) {
      return next();
    }

    if (!requestMatches(req, serviceConfig)) {
      return next();
    }

    const probability = Number(serviceConfig.probability ?? 1);
    if (Math.random() > probability) {
      return next();
    }

    const faultType = serviceConfig.faultType || 'latency';
    const handler = faultHandlers[faultType];
    if (!handler) {
      return next();
    }

    const chaosDetails = {
      serviceName,
      faultType,
      method: req.method,
      path: req.path,
      probability,
      statusCode: serviceConfig.statusCode,
      errorMessage: serviceConfig.errorMessage,
      dependencyName: serviceConfig.dependencyName,
      delayMs: serviceConfig.delayMs,
      cpuBurnMs: serviceConfig.cpuBurnMs,
      memoryMb: serviceConfig.memoryMb,
      maxMemoryHolds: serviceConfig.maxMemoryHolds,
      timestamp: new Date().toISOString()
    };

    if (faultType === 'exception') {
      const previewError = new Error(serviceConfig.errorMessage || 'Chaos simulated exception');
      chaosDetails.exceptionStackTrace = previewError.stack;
    }

    res.locals.chaosInjected = chaosDetails;

    const emitChaosLog = async (details) => {
      console.error('[CHAOS_INJECTED]', JSON.stringify(details));

      if (typeof onChaosInject === 'function') {
        try {
          await Promise.resolve(onChaosInject(details, req));
        } catch (error) {
          console.error('[CHAOS] Failed to emit injection log:', error.message);
        }
      }
    };

    if (faultType === 'latency') {
      const injectedAt = Date.now();
      let emitted = false;

      const emitWithResponseTime = async () => {
        if (emitted) {
          return;
        }
        emitted = true;

        const responseTimeMs = Date.now() - injectedAt;
        await emitChaosLog({
          ...chaosDetails,
          responseTimeMs
        });
      };

      res.once('finish', () => {
        void emitWithResponseTime();
      });

      res.once('close', () => {
        void emitWithResponseTime();
      });
    } else {
      await emitChaosLog(chaosDetails);
    }

    return handler(req, res, next, serviceConfig, { serviceName });
  };
};

module.exports = createChaosMiddleware;
