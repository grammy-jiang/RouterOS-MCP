export type Environment = 'lab' | 'staging' | 'prod';

export type DeviceStatus = 'online' | 'offline' | 'healthy' | 'degraded' | 'unreachable' | 'pending' | 'decommissioned';

export interface Device {
  id: string;
  name: string;
  management_ip: string;
  management_port: number;
  environment: Environment;
  status: DeviceStatus;
  tags?: Record<string, string>;
  capabilities?: Record<string, boolean>;
  last_seen?: string;
}

export interface DeviceCreateRequest {
  name: string;
  hostname: string;
  username: string;
  password: string;
  environment: Environment;
  port?: number;
}

export interface DeviceUpdateRequest {
  name?: string;
  hostname?: string;
  username?: string;
  password?: string;
  environment?: Environment;
  port?: number;
}

export interface DeviceListResponse {
  devices: Device[];
}

export interface DeviceResponse {
  message: string;
  device: Device;
}

export interface ConnectivityTestResponse {
  device_id: string;
  reachable: boolean;
  metadata?: Record<string, any>;
  message: string;
}
