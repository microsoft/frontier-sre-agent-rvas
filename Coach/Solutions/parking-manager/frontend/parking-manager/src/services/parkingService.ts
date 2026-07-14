import { ChaosServiceConfig, ChaosState, ParkingAPI, ParkingInfo, ParkingMetrics, LevelInfo, VMHealthState } from '../types';

class ParkingService {
  private apis: ParkingAPI[] = [];
  private configLoaded = false;
  private initPromise: Promise<void> | null = null;

  async initialize(): Promise<void> {
    if (this.configLoaded) return;
    if (this.initPromise) return this.initPromise;

    this.initPromise = this._doInitialize();
    await this.initPromise;
    this.initPromise = null;
  }

  private async _doInitialize(): Promise<void> {
    this.apis = [
      {
        id: 'lisbon',
        city: 'Lisbon',
        apiUrl: '/api/lisbon',
        enabled: true
      },
      {
        id: 'madrid',
        city: 'Madrid',
        apiUrl: '/api/madrid',
        enabled: true
      },
      {
        id: 'paris',
        city: 'Paris',
        apiUrl: '/api/paris',
        enabled: true
      },
      {
        id: 'berlin',
        city: 'Berlin',
        apiUrl: '/api/berlin',
        enabled: true
      }
    ];

    this.configLoaded = true;
  }

  async getConfiguredAPIs(): Promise<ParkingAPI[]> {
    await this.initialize();
    return this.apis.filter(api => api.enabled);
  }

  async getParkingInfo(apiUrl: string): Promise<ParkingInfo> {
    await this.initialize();
    const response = await fetch(`${apiUrl}/parking`);
    if (!response.ok) {
      throw new Error(`Failed to fetch parking info from ${apiUrl}`);
    }
    const data = await response.json();
    return data.data;
  }

  async getParkingMetrics(apiUrl: string): Promise<ParkingMetrics> {
    await this.initialize();
    const response = await fetch(`${apiUrl}/parking/metrics`);
    if (!response.ok) {
      throw new Error(`Failed to fetch parking metrics from ${apiUrl}`);
    }
    const data = await response.json();
    return data.data;
  }

  async getLevels(apiUrl: string): Promise<LevelInfo[]> {
    await this.initialize();
    const response = await fetch(`${apiUrl}/parking/levels`);
    if (!response.ok) {
      throw new Error(`Failed to fetch levels from ${apiUrl}`);
    }
    const data = await response.json();
    return data.data;
  }

  async updateLevelSlots(apiUrl: string, levelNumber: number, availableSlots: number): Promise<ParkingInfo> {
    await this.initialize();
    const response = await fetch(`${apiUrl}/parking/levels/${levelNumber}`, {
      method: 'PATCH',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ availableSlots }),
    });
    if (!response.ok) {
      throw new Error(`Failed to update level slots in ${apiUrl}`);
    }
    const data = await response.json();
    return data.data;
  }

  async updateParkingConfig(apiUrl: string, config: Partial<Pick<ParkingInfo, 'workingHours' | 'availableWC' | 'availableElectricChargers'>>): Promise<ParkingInfo> {
    await this.initialize();
    const response = await fetch(`${apiUrl}/parking/config`, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(config),
    });
    if (!response.ok) {
      throw new Error(`Failed to update parking config in ${apiUrl}`);
    }
    const data = await response.json();
    return data.data;
  }

  async probeDependency(apiUrl: string): Promise<void> {
    await this.initialize();
    const response = await fetch(`${apiUrl}/parking/dependency`);
    if (!response.ok) {
      throw new Error(`Dependency probe failed for ${apiUrl} with status ${response.status}`);
    }
  }

  async getChaosState(): Promise<ChaosState> {
    const response = await fetch('/api/chaos-control/state');
    if (!response.ok) {
      throw new Error('Failed to fetch chaos state');
    }
    const data = await response.json();
    return data.data;
  }

  async setChaosGlobal(enabled: boolean): Promise<ChaosState> {
    const response = await fetch('/api/chaos-control/global', {
      method: 'PATCH',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ enabled })
    });

    if (!response.ok) {
      throw new Error('Failed to update global chaos switch');
    }

    const state = await this.getChaosState();
    return state;
  }

  async updateChaosService(serviceName: string, config: ChaosServiceConfig): Promise<ChaosServiceConfig> {
    const response = await fetch(`/api/chaos-control/services/${serviceName}`, {
      method: 'PATCH',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(config)
    });

    if (!response.ok) {
      throw new Error(`Failed to update chaos config for ${serviceName}`);
    }

    const data = await response.json();
    return data.data;
  }

  async getVMHealthState(): Promise<VMHealthState> {
    const response = await fetch('/api/vm-health-control/state');
    if (!response.ok) {
      throw new Error('Failed to fetch VM health state');
    }
    const data = await response.json();
    return data.data;
  }

  async setVMHealth(vmName: string, healthy: boolean): Promise<unknown> {
    const response = await fetch(`/api/vm-health-control/${vmName}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ healthy })
    });
    if (!response.ok) {
      throw new Error(`Failed to update VM health for ${vmName}`);
    }
    const data = await response.json();
    return data.data;
  }
}

const parkingService = new ParkingService();
export default parkingService;
