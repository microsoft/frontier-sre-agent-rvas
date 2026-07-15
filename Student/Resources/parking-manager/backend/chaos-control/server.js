require('dotenv').config();
const express = require('express');
const cors = require('cors');

const app = express();
const PORT = process.env.PORT || 3090;

app.use(cors());
app.use(express.json());

const defaultServiceState = () => ({
  enabled: false,
  faultType: 'latency',
  probability: 1,
  delayMs: 1500,
  cpuBurnMs: 2000,
  memoryMb: 128,
  maxMemoryHolds: 2,
  statusCode: 500,
  errorMessage: 'Chaos simulated error',
  pathPattern: '/api',
  method: '*'
});

const state = {
  globalEnabled: false,
  updatedAt: new Date().toISOString(),
  services: {
    lisbon: defaultServiceState(),
    madrid: defaultServiceState(),
    paris: defaultServiceState(),
    berlin: defaultServiceState()
  }
};

const normalizeServicePatch = (patch = {}) => ({
  enabled: typeof patch.enabled === 'boolean' ? patch.enabled : false,
  faultType: typeof patch.faultType === 'string' ? patch.faultType : 'latency',
  probability: Number.isFinite(Number(patch.probability)) ? Math.max(0, Math.min(1, Number(patch.probability))) : 1,
  delayMs: Number.isFinite(Number(patch.delayMs)) ? Math.max(0, Number(patch.delayMs)) : 1500,
  cpuBurnMs: Number.isFinite(Number(patch.cpuBurnMs)) ? Math.max(100, Math.min(30000, Number(patch.cpuBurnMs))) : 2000,
  memoryMb: Number.isFinite(Number(patch.memoryMb)) ? Math.max(8, Math.min(512, Number(patch.memoryMb))) : 128,
  maxMemoryHolds: Number.isFinite(Number(patch.maxMemoryHolds)) ? Math.max(1, Math.min(20, Number(patch.maxMemoryHolds))) : 2,
  statusCode: Number.isFinite(Number(patch.statusCode)) ? Math.max(400, Math.min(599, Number(patch.statusCode))) : 500,
  errorMessage: typeof patch.errorMessage === 'string' && patch.errorMessage.trim() ? patch.errorMessage.trim() : 'Chaos simulated error',
  pathPattern: typeof patch.pathPattern === 'string' && patch.pathPattern.trim() ? patch.pathPattern.trim() : '/api',
  method: typeof patch.method === 'string' && patch.method.trim() ? patch.method.trim().toUpperCase() : '*'
});

const touchState = () => {
  state.updatedAt = new Date().toISOString();
};

app.get('/health', (req, res) => {
  res.json({
    status: 'healthy',
    service: 'chaos-control',
    timestamp: new Date().toISOString()
  });
});

app.get('/api/chaos/state', (req, res) => {
  res.json({ success: true, data: state });
});

app.put('/api/chaos/state', (req, res) => {
  const payload = req.body || {};

  if (typeof payload.globalEnabled === 'boolean') {
    state.globalEnabled = payload.globalEnabled;
  }

  if (payload.services && typeof payload.services === 'object') {
    Object.keys(state.services).forEach((serviceName) => {
      if (payload.services[serviceName]) {
        state.services[serviceName] = normalizeServicePatch(payload.services[serviceName]);
      }
    });
  }

  touchState();
  res.json({ success: true, data: state });
});

app.patch('/api/chaos/global', (req, res) => {
  const { enabled } = req.body || {};

  if (typeof enabled !== 'boolean') {
    return res.status(400).json({ success: false, error: 'enabled must be a boolean' });
  }

  state.globalEnabled = enabled;
  touchState();
  return res.json({ success: true, data: state });
});

app.patch('/api/chaos/services/:serviceName', (req, res) => {
  const { serviceName } = req.params;

  if (!state.services[serviceName]) {
    return res.status(404).json({ success: false, error: `Unknown service: ${serviceName}` });
  }

  state.services[serviceName] = normalizeServicePatch({
    ...state.services[serviceName],
    ...req.body
  });

  touchState();
  return res.json({ success: true, data: state.services[serviceName] });
});

app.listen(PORT, () => {
  console.log(`🎛️  Chaos Control running on port ${PORT}`);
});
