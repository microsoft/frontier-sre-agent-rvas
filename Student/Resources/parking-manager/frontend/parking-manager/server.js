const express = require('express');
const path = require('path');
const { createProxyMiddleware } = require('http-proxy-middleware');

// Allow self-signed certificates (development only)
process.env.NODE_TLS_REJECT_UNAUTHORIZED = '0';

const app = express();
const PORT = process.env.PORT || 8080;

// Backend URLs from environment variables
const backendConfig = {
  lisbon: process.env.REACT_APP_LISBON_API_URL || 'http://10.0.1.4:3001',
  madrid: process.env.REACT_APP_MADRID_API_URL || 'https://10.0.1.5:3002',
  paris: process.env.REACT_APP_PARIS_API_URL || 'https://10.0.1.6:3003',
  berlin: process.env.REACT_APP_BERLIN_API_URL || 'http://localhost:3004',
  chaosControl: process.env.REACT_APP_CHAOS_CONTROL_URL || 'http://localhost:3090',
  vmHealthControl: process.env.REACT_APP_VM_HEALTH_CONTROL_URL || 'http://localhost:3095'
};

console.log('Frontend server with proxy running on port', PORT);
console.log('Backend Configuration:', backendConfig);

// Create proxy middleware with timeout handling
const createProxy = (target, city, rewritePath) => createProxyMiddleware({
  target,
  changeOrigin: true,
  secure: false, // Accept self-signed certificates
  logLevel: 'warn',
  pathRewrite: rewritePath || ((pathReq) => pathReq.replace(/^\/api\/(lisbon|madrid|paris|berlin)/, '/api')),
  
  // Timeout configuration (5 seconds for same Azure region)
  proxyTimeout: 5000, // Timeout for the proxy request to backend
  timeout: 5000,      // Timeout for incoming request
  
  // Error handling for timeouts and failures
  onError: (err, req, res) => {
    console.error(`[${city}] Proxy error:`, err.code || err.message);
    
    if (!res.headersSent) {
      if (err.code === 'ECONNABORTED' || err.code === 'ETIMEDOUT' || err.message.includes('timeout')) {
        res.status(504).json({
          success: false,
          error: `${city} API timeout - service may be unavailable`,
          code: 'TIMEOUT',
          city: city
        });
      } else if (err.code === 'ECONNREFUSED') {
        res.status(503).json({
          success: false,
          error: `${city} API unreachable - service may be down`,
          code: 'CONNECTION_REFUSED',
          city: city
        });
      } else {
        res.status(502).json({
          success: false,
          error: `${city} API error - ${err.message}`,
          code: 'PROXY_ERROR',
          city: city
        });
      }
    }
  },
  
  // Log proxy responses
  onProxyRes: (proxyRes, req, res) => {
    const city = req.path.split('/')[2]; // Extract city from path
    console.log(`[${city}] ${req.method} ${req.path} -> ${proxyRes.statusCode}`);
  }
});

// Proxy endpoints
app.use('/api/lisbon', createProxy(backendConfig.lisbon, 'Lisbon'));
app.use('/api/madrid', createProxy(backendConfig.madrid, 'Madrid'));
app.use('/api/paris', createProxy(backendConfig.paris, 'Paris'));
app.use('/api/berlin', createProxy(backendConfig.berlin, 'Berlin'));
app.use('/api/chaos-control', createProxy(
  backendConfig.chaosControl,
  'ChaosControl',
  (pathReq) => pathReq.replace(/^\/api\/chaos-control/, '/api/chaos')
));
app.use('/api/vm-health-control', createProxy(
  backendConfig.vmHealthControl,
  'VMHealthControl',
  (pathReq) => pathReq.replace(/^\/api\/vm-health-control/, '/api/vm-health')
));

// Disable CSP entirely (allow all sources)
app.use((req, res, next) => {
  res.removeHeader('Content-Security-Policy');
  res.removeHeader('X-Content-Security-Policy');
  res.setHeader('Content-Security-Policy', "default-src * 'unsafe-inline' 'unsafe-eval' data: blob:;");
  next();
});

// Serve static files from the build directory
app.use(express.static(path.join(__dirname, 'build')));

// Handle React routing - return index.html for all routes with debugging
app.get('*', (req, res) => {
  const buildPath = path.join(__dirname, 'build', 'index.html');
  res.sendFile(buildPath, (err) => {
    if (err && !res.headersSent) {
      console.error('Error sending index.html:', err);
      res.status(500).send('Error loading application');
    }
  });
});

// Diagnostic endpoint
app.get('/api/diagnostics', (req, res) => {
  const buildPath = path.join(__dirname, 'build');
  const fs = require('fs');
  res.json({
    buildExists: fs.existsSync(buildPath),
    filesInBuild: fs.existsSync(buildPath) ? fs.readdirSync(buildPath).slice(0, 20) : [],
    serverRunning: true,
    backendConfig,
    nodeVersion: process.version,
    env: process.env.NODE_ENV
  });
});

app.listen(PORT, () => {
  console.log(`Frontend server with proxy running on port ${PORT}`);
});
