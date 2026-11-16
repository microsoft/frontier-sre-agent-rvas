export interface ParkingAPI {
  id: string;
  city: string;
  apiUrl: string;
  enabled: boolean;
}

export interface ParkingInfo {
  id: string;
  name: string;
  city: string;
  location: string;
  numberOfLevels: number;
  parkingSlotsPerLevel: number;
  availableSlotsPerLevel: number[];
  workingHours: {
    open: string;
    close: string;
  };
  availableWC: number;
  availableElectricChargers: number;
  lastUpdated: string;
}

export interface ParkingMetrics {
  city: string;
  totalSlots: number;
  totalAvailable: number;
  totalOccupied: number;
  occupancyRate: number;
  numberOfLevels: number;
  availableWC: number;
  availableElectricChargers: number;
  workingHours: {
    open: string;
    close: string;
  };
  lastUpdated: string;
}

export interface LevelInfo {
  level: number;
  totalSlots: number;
  availableSlots: number;
  occupiedSlots: number;
  occupancyRate: string;
}

export type ChaosFaultType =
  | 'latency'
  | 'httpError'
  | 'dependencyFailure'
  | 'exception'
  | 'disconnect'
  | 'timeout'
  | 'badPayload'
  | 'httpsError'
  | 'highCpu'
  | 'highMemory';

export interface ChaosServiceConfig {
  enabled: boolean;
  faultType: ChaosFaultType;
  probability: number;
  delayMs: number;
  cpuBurnMs: number;
  memoryMb: number;
  maxMemoryHolds: number;
  statusCode: number;
  errorMessage: string;
  pathPattern: string;
  method: string;
}

export interface ChaosState {
  globalEnabled: boolean;
  updatedAt: string;
  services: Record<string, ChaosServiceConfig>;
}

export interface VMHealthEntry {
  healthy: boolean;
  lastChanged: string | null;
  lastLogSent: string | null;
}

export interface VMHealthState {
  updatedAt: string;
  vms: Record<string, VMHealthEntry>;
}
