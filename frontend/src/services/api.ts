import type {
  Device,
  DeviceCreateRequest,
  DeviceUpdateRequest,
  DeviceListResponse,
  DeviceResponse,
  ConnectivityTestResponse,
} from '../types/device';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

class ApiError extends Error {
  status: number;
  data?: unknown;

  constructor(message: string, status: number, data?: unknown) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.data = data;
  }
}

async function fetchApi<T>(
  endpoint: string,
  options?: RequestInit
): Promise<T> {
  const url = `${API_BASE_URL}${endpoint}`;
  
  try {
    const response = await fetch(url, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        ...options?.headers,
      },
      credentials: 'include', // Include cookies for authentication
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new ApiError(
        errorData.detail || `HTTP ${response.status}: ${response.statusText}`,
        response.status,
        errorData
      );
    }

    return await response.json();
  } catch (error) {
    if (error instanceof ApiError) {
      throw error;
    }
    throw new ApiError(
      error instanceof Error ? error.message : 'Network error',
      0
    );
  }
}

export const deviceApi = {
  async list(): Promise<Device[]> {
    const response = await fetchApi<DeviceListResponse>('/api/devices');
    return response.devices;
  },

  async create(data: DeviceCreateRequest): Promise<Device> {
    const response = await fetchApi<DeviceResponse>('/api/admin/devices', {
      method: 'POST',
      body: JSON.stringify(data),
    });
    return response.device;
  },

  async update(id: string, data: DeviceUpdateRequest): Promise<Device> {
    const response = await fetchApi<DeviceResponse>(`/api/admin/devices/${id}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
    return response.device;
  },

  async delete(id: string): Promise<void> {
    await fetchApi<{ message: string }>(`/api/admin/devices/${id}`, {
      method: 'DELETE',
    });
  },

  async testConnectivity(id: string): Promise<ConnectivityTestResponse> {
    return await fetchApi<ConnectivityTestResponse>(`/api/admin/devices/${id}/test`, {
      method: 'POST',
    });
  },
};

export { ApiError };
