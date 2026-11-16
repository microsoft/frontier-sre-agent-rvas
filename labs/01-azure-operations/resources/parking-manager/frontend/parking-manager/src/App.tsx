import React, { useEffect, useState } from 'react';
import './App.css';
import parkingService from './services/parkingService';
import { ChaosServiceConfig, ChaosState, ParkingMetrics, ParkingInfo, LevelInfo, VMHealthState } from './types';
import ParkingCard from './components/ParkingCard';
import ParkingDetails from './components/ParkingDetails';

interface ParkingData {
  apiUrl: string;
  city: string;
  metrics: ParkingMetrics | null;
  info: ParkingInfo | null;
  error: string | null;
  loading: boolean;
}

function App() {
  const [parkingData, setParkingData] = useState<ParkingData[]>([]);
  const [selectedParking, setSelectedParking] = useState<{ apiUrl: string; city: string } | null>(null);
  const [levels, setLevels] = useState<LevelInfo[]>([]);
  const [refreshing, setRefreshing] = useState(false);
  const [chaosState, setChaosState] = useState<ChaosState | null>(null);
  const [chaosDrafts, setChaosDrafts] = useState<Record<string, ChaosServiceConfig>>({});
  const [chaosError, setChaosError] = useState<string | null>(null);
  const [chaosSavingTarget, setChaosSavingTarget] = useState<string | null>(null);
  const [showChaosBackoffice, setShowChaosBackoffice] = useState(false);
  const [showChaosHelp, setShowChaosHelp] = useState(false);
  const [showVMHealth, setShowVMHealth] = useState(false);
  const [vmHealthState, setVMHealthState] = useState<VMHealthState | null>(null);
  const [vmHealthError, setVMHealthError] = useState<string | null>(null);
  const [vmHealthSaving, setVMHealthSaving] = useState<string | null>(null);

  const chaosFaultTypes = ['latency', 'httpError', 'dependencyFailure', 'exception', 'disconnect', 'timeout', 'badPayload', 'httpsError', 'highCpu', 'highMemory'];

  const loadChaosState = async () => {
    try {
      const state = await parkingService.getChaosState();
      setChaosState(state);
      setChaosDrafts(state.services);
      setChaosError(null);
    } catch (error) {
      setChaosError(error instanceof Error ? error.message : 'Failed to load chaos configuration');
    }
  };

  const loadVMHealthState = async () => {
    try {
      const state = await parkingService.getVMHealthState();
      setVMHealthState(state);
      setVMHealthError(null);
    } catch (error) {
      setVMHealthError(error instanceof Error ? error.message : 'Failed to load VM health state');
    }
  };

  const handleVMHealthToggle = async (vmName: string, healthy: boolean) => {
    try {
      setVMHealthSaving(vmName);
      await parkingService.setVMHealth(vmName, healthy);
      await loadVMHealthState();
    } catch (error) {
      setVMHealthError(error instanceof Error ? error.message : `Failed to update ${vmName} VM health`);
    } finally {
      setVMHealthSaving(null);
    }
  };

  const loadParkingData = async () => {
    const apis = await parkingService.getConfiguredAPIs();
    const dataPromises = apis.map(async (api) => {
      try {
        const [metrics, info] = await Promise.all([
          parkingService.getParkingMetrics(api.apiUrl),
          parkingService.getParkingInfo(api.apiUrl)
        ]);

        if (api.id === 'paris') {
          parkingService.probeDependency(api.apiUrl).catch((dependencyError) => {
            console.warn('Paris dependency probe failed:', dependencyError);
          });
        }

        return {
          apiUrl: api.apiUrl,
          city: api.city,
          metrics,
          info,
          error: null,
          loading: false
        };
      } catch (error) {
        return {
          apiUrl: api.apiUrl,
          city: api.city,
          metrics: null,
          info: null,
          error: error instanceof Error ? error.message : 'Unknown error',
          loading: false
        };
      }
    });

    const data = await Promise.all(dataPromises);
    setParkingData(data);
  };

  const loadLevels = async (apiUrl: string) => {
    try {
      const levelsData = await parkingService.getLevels(apiUrl);
      setLevels(levelsData);
    } catch (error) {
      console.error('Error loading levels:', error);
      alert('Failed to load level details');
    }
  };

  const handleViewDetails = async (apiUrl: string, city: string) => {
    setSelectedParking({ apiUrl, city });
    await loadLevels(apiUrl);
  };

  const handleUpdateLevel = async (levelNumber: number, availableSlots: number) => {
    if (!selectedParking) return;

    try {
      await parkingService.updateLevelSlots(selectedParking.apiUrl, levelNumber, availableSlots);
      await loadLevels(selectedParking.apiUrl);
      await loadParkingData(); // Refresh main data
    } catch (error) {
      console.error('Error updating level:', error);
      alert('Failed to update level availability');
    }
  };

  const handleRefresh = async () => {
    setRefreshing(true);
    await Promise.all([loadParkingData(), loadChaosState(), loadVMHealthState()]);
    setRefreshing(false);
  };

  const handleChaosGlobalToggle = async (enabled: boolean) => {
    try {
      setChaosSavingTarget('global');
      await parkingService.setChaosGlobal(enabled);
      await loadChaosState();
    } catch (error) {
      setChaosError(error instanceof Error ? error.message : 'Failed to update global chaos switch');
    } finally {
      setChaosSavingTarget(null);
    }
  };

  const handleChaosDraftChange = (serviceName: string, patch: Partial<ChaosServiceConfig>) => {
    setChaosDrafts((prev) => ({
      ...prev,
      [serviceName]: {
        ...prev[serviceName],
        ...patch
      }
    }));
  };

  const handleApplyServiceChaos = async (serviceName: string) => {
    try {
      const draft = chaosDrafts[serviceName];
      if (!draft) {
        return;
      }

      setChaosSavingTarget(serviceName);

      if (draft.enabled && !chaosState?.globalEnabled) {
        await parkingService.setChaosGlobal(true);
      }

      await parkingService.updateChaosService(serviceName, draft);
      await loadChaosState();
    } catch (error) {
      setChaosError(error instanceof Error ? error.message : `Failed to update ${serviceName} chaos config`);
    } finally {
      setChaosSavingTarget(null);
    }
  };

  useEffect(() => {
    loadParkingData();
    loadChaosState();
    loadVMHealthState();
    // Auto-refresh every 3 seconds
    const interval = setInterval(loadParkingData, 3000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="App">
      <header className="App-header">
        <h1>🚗 Parking Manager</h1>
        <p>Manage parking facilities across multiple cities</p>
        <div className="header-actions">
          <button
            className="refresh-btn"
            onClick={handleRefresh}
            disabled={refreshing}
          >
            {refreshing ? '🔄 Refreshing...' : '🔄 Refresh'}
          </button>
          <button
            className="icon-btn"
            onClick={() => { setShowChaosBackoffice((prev) => !prev); setShowVMHealth(false); }}
            aria-label={showChaosBackoffice ? 'Show parking dashboard' : 'Show chaos backoffice'}
            title={showChaosBackoffice ? 'Show parking dashboard' : 'Show chaos backoffice'}
          >
            {showChaosBackoffice ? '🏠' : '🧪'}
          </button>
          <button
            className="icon-btn"
            onClick={() => { setShowVMHealth((prev) => !prev); setShowChaosBackoffice(false); }}
            aria-label={showVMHealth ? 'Hide VM health panel' : 'Show VM health panel'}
            title={showVMHealth ? 'Hide VM health panel' : 'Show VM health panel'}
          >
            {showVMHealth ? '🏠' : '💊'}
          </button>
        </div>
      </header>

      <main className="App-main">
        {showVMHealth ? (
          <section className="vm-health-panel">
            <div className="vm-health-panel-header">
              <h2>💊 VM Health Control</h2>
              <p className="vm-health-subtitle">Simulate unhealthy VM events &mdash; sends a log entry to a custom Log Analytics table</p>
            </div>

            {vmHealthError && <p className="chaos-error">{vmHealthError}</p>}

            <div className="vm-health-grid">
              {vmHealthState && Object.entries(vmHealthState.vms).map(([vmName, vm]) => (
                <div className={`vm-health-card ${vm.healthy ? '' : 'vm-unhealthy'}`} key={vmName}>
                  <div className="vm-health-card-header">
                    <h3>{vmName.toUpperCase()}</h3>
                    <span className={`vm-health-badge ${vm.healthy ? 'badge-healthy' : 'badge-unhealthy'}`}>
                      {vm.healthy ? '✅ Healthy' : '❌ Unhealthy'}
                    </span>
                  </div>
                  <p className="vm-health-name">vm-parking-{vmName}</p>
                  {vm.lastChanged && (
                    <p className="vm-health-meta">Last changed: {new Date(vm.lastChanged).toLocaleString()}</p>
                  )}
                  {vm.lastLogSent && (
                    <p className="vm-health-meta">Last log sent: {new Date(vm.lastLogSent).toLocaleString()}</p>
                  )}
                  <div className="vm-health-actions">
                    <button
                      className="vm-health-btn vm-btn-unhealthy"
                      disabled={!vm.healthy || vmHealthSaving === vmName}
                      onClick={() => handleVMHealthToggle(vmName, false)}
                    >
                      {vmHealthSaving === vmName && !vm.healthy ? 'Sending...' : 'Mark Unhealthy'}
                    </button>
                    <button
                      className="vm-health-btn vm-btn-healthy"
                      disabled={vm.healthy || vmHealthSaving === vmName}
                      onClick={() => handleVMHealthToggle(vmName, true)}
                    >
                      {vmHealthSaving === vmName && vm.healthy ? 'Sending...' : 'Mark Healthy'}
                    </button>
                  </div>
                </div>
              ))}
              {!vmHealthState && <p>Loading VM health state...</p>}
            </div>
          </section>
        ) : showChaosBackoffice ? (
          <section className="chaos-panel">
            <div className="chaos-panel-header">
              <h2>{showChaosHelp ? '❓ Chaos Help' : '🧪 Chaos Backoffice'}</h2>
              <div className="chaos-header-actions">
                <button
                  className="chaos-help-btn"
                  onClick={() => setShowChaosHelp((prev) => !prev)}
                  aria-label={showChaosHelp ? 'Close chaos help' : 'Open chaos help'}
                  title={showChaosHelp ? 'Close chaos help' : 'Open chaos help'}
                >
                  {showChaosHelp ? '↩' : '?'}
                </button>
                {!showChaosHelp && (
                  <div className="chaos-global-toggle">
                    <label htmlFor="global-chaos">Global Chaos</label>
                    <input
                      id="global-chaos"
                      type="checkbox"
                      checked={!!chaosState?.globalEnabled}
                      disabled={chaosSavingTarget === 'global' || !chaosState}
                      onChange={(event) => handleChaosGlobalToggle(event.target.checked)}
                    />
                  </div>
                )}
              </div>
            </div>

            {chaosError && <p className="chaos-error">{chaosError}</p>}

            {!showChaosHelp && chaosState && !chaosState.globalEnabled && (
              <div className="chaos-warning">
                Global Chaos is OFF. Service faults are configured but will not be injected until Global Chaos is enabled.
              </div>
            )}

            {showChaosHelp ? (
              <div className="chaos-help-page">
                <div className="chaos-help-card">
                  <h3>Common fields</h3>
                  <ul>
                    <li><strong>Enabled</strong>: turns fault on/off for the selected service.</li>
                    <li><strong>Probability</strong>: from <strong>0</strong> to <strong>1</strong> (1 means every matching request).</li>
                    <li><strong>HTTP Method</strong>: choose one verb or <strong>*</strong> for all methods.</li>
                    <li><strong>Path Prefix</strong>: apply fault only when path starts with this value.</li>
                    <li><strong>Error Message</strong>: message returned for error-based faults.</li>
                  </ul>
                </div>

                <div className="chaos-help-card">
                  <h3>Fault types</h3>
                  <ul>
                    <li><strong>latency</strong>: delays response then continues normally. Required fields: <strong>delayMs</strong>. Common filters: <strong>probability</strong>, <strong>method</strong>, <strong>pathPattern</strong>.</li>
                    <li><strong>httpError</strong>: returns immediate HTTP error JSON. Required fields: <strong>statusCode</strong>. Optional: <strong>errorMessage</strong>.</li>
                    <li><strong>dependencyFailure</strong>: simulates external dependency outage (ideal for Paris <strong>/api/parking/dependency</strong>). Required fields: <strong>statusCode</strong>. Recommended config: <strong>method=GET</strong>, <strong>pathPattern=/api/parking/dependency</strong>, <strong>probability=1</strong>. Optional: <strong>errorMessage</strong>.</li>
                    <li><strong>httpsError</strong>: returns TLS-style simulated error response. Required fields: <strong>statusCode</strong> (recommended 525). Optional: <strong>errorMessage</strong>.</li>
                    <li><strong>exception</strong>: throws server exception handled by API middleware. Required fields: none. Optional: <strong>errorMessage</strong>.</li>
                    <li><strong>disconnect</strong>: forcefully closes socket to simulate dropped connection. Required fields: none.</li>
                    <li><strong>timeout</strong>: no response is sent, allowing upstream timeout behavior. Required fields: none.</li>
                    <li><strong>badPayload</strong>: returns malformed JSON to test client parsing failures. Required fields: none.</li>
                    <li><strong>highCpu</strong>: burns CPU in-process then continues. Required fields: <strong>cpuBurnMs</strong>.</li>
                    <li><strong>highMemory</strong>: allocates memory temporarily. Required fields: <strong>memoryMb</strong>, <strong>delayMs</strong>. Safety field: <strong>maxMemoryHolds</strong>.</li>
                  </ul>
                </div>

                <div className="chaos-help-card">
                  <h3>Safety and suggested values</h3>
                  <ul>
                    <li><strong>maxMemoryHolds</strong>: cap concurrent high-memory allocations per service.</li>
                    <li>Starter profile: <strong>probability=0.2</strong>, <strong>delayMs=1500</strong>, <strong>memoryMb=128</strong>.</li>
                    <li>Paris dependency test: use <strong>dependencyFailure</strong> + <strong>GET /api/parking/dependency</strong>; for slow downstream behavior use <strong>timeout</strong> with the same path.</li>
                    <li>Roll out one service at a time, then increase intensity gradually.</li>
                  </ul>
                </div>
              </div>
            ) : (
              <div className="chaos-grid">
                {Object.entries(chaosDrafts).map(([serviceName, config]) => (
                  <div className="chaos-card" key={serviceName}>
                    <h3>{serviceName.toUpperCase()}</h3>

                    <label>
                      <span>Enabled</span>
                      <input
                        type="checkbox"
                        checked={config.enabled}
                        onChange={(event) => handleChaosDraftChange(serviceName, { enabled: event.target.checked })}
                      />
                    </label>

                    <label>
                      <span>Fault Type</span>
                      <select
                        value={config.faultType}
                        onChange={(event) => handleChaosDraftChange(serviceName, { faultType: event.target.value as ChaosServiceConfig['faultType'] })}
                      >
                        {chaosFaultTypes.map((type) => (
                          <option key={type} value={type}>{type}</option>
                        ))}
                      </select>
                    </label>

                    <label>
                      <span>Probability (0-1)</span>
                      <input
                        type="number"
                        min={0}
                        max={1}
                        step={0.1}
                        value={config.probability}
                        onChange={(event) => handleChaosDraftChange(serviceName, { probability: Number(event.target.value) })}
                      />
                    </label>

                    <label>
                      <span>Delay (ms)</span>
                      <input
                        type="number"
                        min={0}
                        value={config.delayMs}
                        onChange={(event) => handleChaosDraftChange(serviceName, { delayMs: Number(event.target.value) })}
                      />
                    </label>

                    <label>
                      <span>CPU Burn (ms)</span>
                      <input
                        type="number"
                        min={100}
                        value={config.cpuBurnMs}
                        onChange={(event) => handleChaosDraftChange(serviceName, { cpuBurnMs: Number(event.target.value) })}
                      />
                    </label>

                    <label>
                      <span>Memory (MB)</span>
                      <input
                        type="number"
                        min={8}
                        max={512}
                        value={config.memoryMb}
                        onChange={(event) => handleChaosDraftChange(serviceName, { memoryMb: Number(event.target.value) })}
                      />
                    </label>

                    <label>
                      <span>Max Memory Holds</span>
                      <input
                        type="number"
                        min={1}
                        max={20}
                        value={config.maxMemoryHolds}
                        onChange={(event) => handleChaosDraftChange(serviceName, { maxMemoryHolds: Number(event.target.value) })}
                      />
                    </label>

                    <label>
                      <span>Status Code</span>
                      <input
                        type="number"
                        min={400}
                        max={599}
                        value={config.statusCode}
                        onChange={(event) => handleChaosDraftChange(serviceName, { statusCode: Number(event.target.value) })}
                      />
                    </label>

                    <label>
                      <span>HTTP Method</span>
                      <select
                        value={config.method}
                        onChange={(event) => handleChaosDraftChange(serviceName, { method: event.target.value })}
                      >
                        <option value="*">*</option>
                        <option value="GET">GET</option>
                        <option value="POST">POST</option>
                        <option value="PUT">PUT</option>
                        <option value="PATCH">PATCH</option>
                        <option value="DELETE">DELETE</option>
                      </select>
                    </label>

                    <label>
                      <span>Path Prefix</span>
                      <input
                        type="text"
                        value={config.pathPattern}
                        onChange={(event) => handleChaosDraftChange(serviceName, { pathPattern: event.target.value })}
                      />
                    </label>

                    <label>
                      <span>Error Message</span>
                      <input
                        type="text"
                        value={config.errorMessage}
                        onChange={(event) => handleChaosDraftChange(serviceName, { errorMessage: event.target.value })}
                      />
                    </label>

                    <button
                      className="refresh-btn"
                      disabled={chaosSavingTarget === serviceName}
                      onClick={() => handleApplyServiceChaos(serviceName)}
                    >
                      {chaosSavingTarget === serviceName ? 'Saving...' : 'Apply'}
                    </button>
                  </div>
                ))}
              </div>
            )}
          </section>
        ) : (
          <>
            {parkingData.length === 0 && (
              <div className="loading-state">
                <p>Loading parking data...</p>
              </div>
            )}

            <div className="parking-grid">
              {parkingData.map((data) => (
                <div key={data.city}>
                  {data.error ? (
                    <div className="error-card">
                      <h3>❌ {data.city}</h3>
                      <p>Failed to load data</p>
                      <small>{data.error}</small>
                    </div>
                  ) : data.metrics && data.info ? (
                    <ParkingCard
                      metrics={data.metrics}
                      parkingInfo={{ name: data.info.name, location: data.info.location }}
                      onViewDetails={() => handleViewDetails(data.apiUrl, data.city)}
                    />
                  ) : (
                    <div className="loading-card">
                      <p>Loading {data.city}...</p>
                    </div>
                  )}
                </div>
              ))}
            </div>

            {parkingData.every(d => d.error) && parkingData.length > 0 && (
              <div className="no-data-message">
                <h2>⚠️ No parking data available</h2>
                <p>Make sure the parking APIs are running and accessible.</p>
                <p>Check the console for more details.</p>
              </div>
            )}
          </>
        )}
      </main>

      {selectedParking && (
        <ParkingDetails
          city={selectedParking.city}
          levels={levels}
          onClose={() => setSelectedParking(null)}
          onUpdateLevel={handleUpdateLevel}
          onRefresh={() => loadLevels(selectedParking.apiUrl)}
        />
      )}

      <footer className="App-footer">
        <p>Azure SRE Demo - Parking Manager © 2026</p>
      </footer>
    </div>
  );
}

export default App;

