require('dotenv').config();
const express = require('express');
const cors = require('cors');
const { DefaultAzureCredential } = require('@azure/identity');
const { LogsIngestionClient } = require('@azure/monitor-ingestion');

const app = express();
const PORT = process.env.PORT || 3095;

app.use(cors());
app.use(express.json());

// Logs Ingestion API configuration (managed identity)
const DCE_ENDPOINT = process.env.DCE_ENDPOINT || '';
const DCR_RULE_ID = process.env.DCR_RULE_ID || '';
const DCR_STREAM_NAME = process.env.DCR_STREAM_NAME || 'Custom-VMHealthStatus_CL';

// Lazily initialised client (only when DCE is configured)
let ingestionClient = null;

function getIngestionClient() {
  if (!ingestionClient && DCE_ENDPOINT) {
    const credential = new DefaultAzureCredential();
    ingestionClient = new LogsIngestionClient(DCE_ENDPOINT, credential);
  }
  return ingestionClient;
}

// In-memory state tracking
const state = {
  updatedAt: new Date().toISOString(),
  vms: {
    madrid: { healthy: true, lastChanged: null, lastLogSent: null },
    paris: { healthy: true, lastChanged: null, lastLogSent: null }
  }
};

// --- Log Analytics helper ---

async function sendToLogAnalytics(logData) {
  const client = getIngestionClient();
  if (!client || !DCR_RULE_ID) {
    console.log('[Log Analytics] Not configured — log would be sent:', JSON.stringify(logData));
    return { success: false, configured: false, message: 'Logs Ingestion API not configured' };
  }

  try {
    await client.upload(DCR_RULE_ID, DCR_STREAM_NAME, logData);
    console.log('[Log Analytics] Log sent successfully via Logs Ingestion API');
    return { success: true };
  } catch (error) {
    console.error('[Log Analytics] Error sending log:', error.message);
    return { success: false, error: error.message };
  }
}

// --- Routes ---

app.get('/health', (_req, res) => {
  res.json({
    status: 'healthy',
    service: 'vm-health-control',
    timestamp: new Date().toISOString()
  });
});

// Get current state of all VMs
app.get('/api/vm-health/state', (_req, res) => {
  res.json({ success: true, data: state });
});

// Set a specific VM healthy or unhealthy
app.patch('/api/vm-health/:vmName', async (req, res) => {
  const { vmName } = req.params;

  if (!state.vms[vmName]) {
    return res.status(404).json({
      success: false,
      error: `Unknown VM: ${vmName}. Valid values: ${Object.keys(state.vms).join(', ')}`
    });
  }

  const { healthy } = req.body;

  if (typeof healthy !== 'boolean') {
    return res.status(400).json({ success: false, error: 'healthy must be a boolean' });
  }

  const previousState = state.vms[vmName].healthy;
  state.vms[vmName].healthy = healthy;
  state.vms[vmName].lastChanged = new Date().toISOString();
  state.updatedAt = new Date().toISOString();

  // Build and send the log entry
  const logEntry = [{
    TimeGenerated: new Date().toISOString(),
    vmName: `vm-parking-${vmName}`,
    city: vmName.charAt(0).toUpperCase() + vmName.slice(1),
    healthState: healthy ? 'Healthy' : 'Unhealthy',
    previousState: previousState ? 'Healthy' : 'Unhealthy',
    severity: healthy ? 'Info' : 'Critical',
    source: 'vm-health-control',
    message: healthy
      ? `VM vm-parking-${vmName} has recovered and is now healthy.`
      : `VM vm-parking-${vmName} is reporting unhealthy status. Potential issues detected.`,
    resourceGroup: `rg-parking-${vmName}`,
    subscriptionId: process.env.AZURE_SUBSCRIPTION_ID || 'demo-subscription',
    resourceType: 'Microsoft.Compute/virtualMachines'
  }];

  const logResult = await sendToLogAnalytics(logEntry);
  state.vms[vmName].lastLogSent = logResult.success ? new Date().toISOString() : null;

  return res.json({
    success: true,
    data: {
      vm: vmName,
      healthy,
      previousState,
      logResult
    }
  });
});

app.listen(PORT, () => {
  console.log(`VM Health Control running on port ${PORT}`);
  console.log(`DCE endpoint: ${DCE_ENDPOINT || 'NOT configured (dry-run mode)'}`);
  console.log(`DCR rule ID: ${DCR_RULE_ID || '<not set>'}`);
  console.log(`Stream: ${DCR_STREAM_NAME}`);
});
